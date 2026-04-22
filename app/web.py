from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from app.config import SETTINGS, write_env_updates
from app.db import DB
from app.image_matching import ImageMatcher
from app.policy import PolicyEngine
from app.services.reference_service import ReferenceImageService


def create_app() -> Flask:
    runtime_config = DB.get_effective_runtime_config()
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = runtime_config['dashboard_secret_key']
    app.config['SESSION_PERMANENT'] = True

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        runtime = DB.get_effective_runtime_config()
        return {
            'guild_id': runtime['discord_guild_id'],
            'runtime_config': runtime,
            'bot_status': get_bot_status(),
            'is_first_run': not runtime['setup_complete'],
        }

    def is_logged_in() -> bool:
        return bool(session.get('dashboard_auth'))

    def is_local_request() -> bool:
        remote = (request.remote_addr or '').strip()
        return remote in {'127.0.0.1', '::1', 'localhost'}

    @app.before_request
    def protect_routes() -> Any:
        runtime = DB.get_effective_runtime_config()
        open_paths = {
            'login',
            'static',
            'setup_wizard',
            'api_status',
            'api_live_summary',
            'api_live_detections',
            'api_bot_status',
            'local_start_bot_route',
        }
        if request.endpoint in open_paths or (request.endpoint and request.endpoint.startswith('static')):
            return None
        if not runtime['setup_complete'] and request.endpoint != 'setup_wizard':
            return redirect(url_for('setup_wizard'))
        if not is_logged_in():
            return redirect(url_for('login'))
        return None

    @app.route('/setup', methods=['GET', 'POST'])
    def setup_wizard():
        runtime = DB.get_effective_runtime_config()
        if runtime['setup_complete'] and is_logged_in():
            return redirect(url_for('index'))
        if request.method == 'POST':
            token = request.form.get('discord_bot_token', '').strip()
            guild_id = request.form.get('discord_guild_id', '').strip()
            password = request.form.get('dashboard_password', '').strip()
            secret_key = request.form.get('dashboard_secret_key', '').strip()
            bot_log_channel_id = request.form.get('bot_log_channel_id', '').strip()
            preset = request.form.get('preset', 'balanced').strip().lower()
            errors: list[str] = []
            if not token:
                errors.append('Bot token is required.')
            if not guild_id.isdigit():
                errors.append('Guild ID must be a number.')
            if not password:
                errors.append('Dashboard password is required.')
            if not secret_key:
                secret_key = os.urandom(24).hex()
            if errors:
                for error in errors:
                    flash(error, 'error')
                return render_template('setup.html', preset=preset)

            payload = {
                'discord_bot_token': token,
                'discord_guild_id': guild_id,
                'dashboard_password': password,
                'dashboard_secret_key': secret_key,
                'bot_log_channel_id': bot_log_channel_id,
            }
            DB.complete_setup(payload)
            write_env_updates({
                'DISCORD_BOT_TOKEN': token,
                'DISCORD_GUILD_ID': guild_id,
                'DASHBOARD_PASSWORD': password,
                'DASHBOARD_SECRET_KEY': secret_key,
                'BOT_LOG_CHANNEL_ID': bot_log_channel_id,
            })
            DB.ensure_guild_settings(int(guild_id))
            if preset in PolicyEngine.PRESETS:
                settings = DB.get_guild_settings(int(guild_id))
                if settings is not None:
                    merged = {**settings, **PolicyEngine.PRESETS[preset]}
                    DB.update_guild_settings(int(guild_id), merged)
            DB.log_audit('setup', f'Initial setup saved using preset: {preset}')
            session['dashboard_auth'] = True
            return redirect(url_for('index'))

        return render_template('setup.html', preset='balanced')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        runtime = DB.get_effective_runtime_config()
        if not runtime['setup_complete']:
            return redirect(url_for('setup_wizard'))
        if request.method == 'POST':
            password = request.form.get('password', '')
            if password == runtime['dashboard_password']:
                session['dashboard_auth'] = True
                session.permanent = True
                return redirect(url_for('index'))
            flash('Wrong password.', 'error')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/')
    def index():
        runtime = DB.get_effective_runtime_config()
        stats = DB.get_detection_stats()
        detections = DB.get_recent_detections(20)
        references = DB.get_reference_images(active_only=False)
        settings = DB.get_guild_settings(runtime['discord_guild_id']) if runtime['discord_guild_id'] else None
        return render_template('index.html', stats=stats, detections=detections, references=references, settings=settings)

    @app.route('/settings', methods=['GET', 'POST'])
    def settings_page():
        runtime = DB.get_effective_runtime_config()
        guild_id = runtime['discord_guild_id']
        if not guild_id:
            flash('Run setup first.', 'error')
            return redirect(url_for('setup_wizard'))

        if request.method == 'POST':
            new_guild_id_raw = request.form.get('discord_guild_id', '').strip() or str(guild_id)
            if not new_guild_id_raw.isdigit():
                flash('Server ID must be a number.', 'error')
                return redirect(url_for('settings_page'))
            new_guild_id = int(new_guild_id_raw)

            honeypot_channel_raw = request.form.get('honeypot_channel_id', '').strip()
            payload = {
                'match_threshold': int(request.form.get('match_threshold', 8)),
                'exact_sha_enabled': request.form.get('exact_sha_enabled') == 'on',
                'delete_on_match': request.form.get('delete_on_match') == 'on',
                'notify_on_match': request.form.get('notify_on_match') == 'on',
                'action_type': request.form.get('action_type', 'timeout').strip().lower(),
                'timeout_minutes': int(request.form.get('timeout_minutes', 60)),
                'escalate_repeat_offenders': request.form.get('escalate_repeat_offenders') == 'on',
                'repeat_window_minutes': int(request.form.get('repeat_window_minutes', 120)),
                'repeat_ban_count': int(request.form.get('repeat_ban_count', 3)),
                'ignore_bots': request.form.get('ignore_bots') == 'on',
                'exempt_role_ids': _parse_id_list(request.form.get('exempt_role_ids', '')),
                'exempt_channel_ids': _parse_id_list(request.form.get('exempt_channel_ids', '')),
                'honeypot_channel_id': int(honeypot_channel_raw) if honeypot_channel_raw.isdigit() else None,
                'honeypot_action': request.form.get('honeypot_action', 'ban').strip().lower(),
                'honeypot_delete_message': request.form.get('honeypot_delete_message') == 'on',
                'honeypot_exempt_role_ids': _parse_id_list(request.form.get('honeypot_exempt_role_ids', '')),
            }
            preset = request.form.get('preset', '').strip().lower()
            if preset in PolicyEngine.PRESETS:
                payload.update(PolicyEngine.PRESETS[preset])
            DB.ensure_guild_settings(new_guild_id)
            DB.update_guild_settings(new_guild_id, payload)

            env_updates: dict[str, str | int | None] = {}

            new_password = request.form.get('dashboard_password', '').strip()
            if new_password:
                DB.set_app_setting('dashboard_password', new_password)
                env_updates['DASHBOARD_PASSWORD'] = new_password

            new_log_channel = request.form.get('bot_log_channel_id', '').strip()
            DB.set_app_setting('bot_log_channel_id', new_log_channel)
            env_updates['BOT_LOG_CHANNEL_ID'] = new_log_channel

            new_token = request.form.get('discord_bot_token', '').strip()
            if new_token:
                DB.set_app_setting('discord_bot_token', new_token)
                env_updates['DISCORD_BOT_TOKEN'] = new_token

            if new_guild_id != guild_id:
                DB.set_app_setting('discord_guild_id', str(new_guild_id))
                env_updates['DISCORD_GUILD_ID'] = new_guild_id

            if env_updates:
                write_env_updates(env_updates)

            DB.log_audit('settings', 'Settings updated from dashboard')
            flash('Settings saved.', 'success')
            return redirect(url_for('settings_page'))

        settings = DB.get_guild_settings(guild_id)
        return render_template('settings.html', settings=settings, presets=PolicyEngine.PRESETS, runtime=runtime)

    @app.post('/bot/power')
    def bot_power_route():
        status = get_bot_status()
        if status.get('fresh'):
            ok, message = stop_bot_process()
        else:
            ok, message = start_bot_process()
        flash(message, 'success' if ok else 'error')
        return redirect(request.referrer or url_for('index'))

    @app.post('/bot/start')
    def start_bot_route():
        ok, message = start_bot_process()
        flash(message, 'success' if ok else 'error')
        return redirect(request.referrer or url_for('index'))

    @app.post('/bot/local-start')
    def local_start_bot_route():
        if not is_local_request():
            return jsonify({'ok': False, 'message': 'Forbidden'}), 403
        ok, message = start_bot_process()
        return jsonify({'ok': ok, 'message': message}), (200 if ok else 400)

    @app.post('/bot/stop')
    def stop_bot_route():
        ok, message = stop_bot_process()
        flash(message, 'success' if ok else 'error')
        return redirect(request.referrer or url_for('index'))

    @app.post('/bot/restart')
    def restart_bot_route():
        stop_bot_process()
        ok, message = start_bot_process()
        flash('Bot restarted.' if ok else message, 'success' if ok else 'error')
        return redirect(request.referrer or url_for('index'))

    @app.route('/references', methods=['GET', 'POST'])
    def references_page():
        if request.method == 'POST':
            uploads = request.files.getlist('images') or []
            single = request.files.get('image')
            if single and single.filename:
                uploads.append(single)
            if not uploads:
                flash('Choose one or more image files.', 'error')
                return redirect(url_for('references_page'))

            added = 0
            for upload in uploads:
                if not upload or not upload.filename:
                    continue
                label = Path(upload.filename).stem.replace('_', ' ').replace('-', ' ').strip() or 'Reference image'
                notes = ''
                try:
                    ReferenceImageService.save_and_register(upload.stream, upload.filename, label, notes)
                    added += 1
                except Exception as exc:
                    flash(f'Skipped {upload.filename}: {exc}', 'error')
            if added:
                DB.log_audit('reference_add', f'Added {added} reference image(s)')
                flash(f'Added {added} reference image(s).', 'success')
            return redirect(url_for('references_page'))

        references = DB.get_reference_images(active_only=False)
        return render_template('references.html', references=references)

    @app.post('/references/<int:image_id>/toggle')
    def toggle_reference(image_id: int):
        row = DB.get_reference_image(image_id)
        if row is None:
            flash('Reference image not found.', 'error')
            return redirect(url_for('references_page'))
        DB.update_reference_status(image_id, not bool(row['active']))
        DB.log_audit('reference_toggle', f'Toggled reference image {image_id}')
        flash('Reference image updated.', 'success')
        return redirect(url_for('references_page'))

    @app.post('/references/<int:image_id>/edit')
    def edit_reference(image_id: int):
        row = DB.get_reference_image(image_id)
        if row is None:
            flash('Reference image not found.', 'error')
            return redirect(url_for('references_page'))
        label = request.form.get('label', '').strip() or row['label']
        notes = request.form.get('notes', '').strip()
        DB.update_reference_metadata(image_id, label, notes)
        DB.log_audit('reference_edit', f'Edited reference image {image_id}')
        flash('Reference details saved.', 'success')
        return redirect(url_for('references_page'))

    @app.post('/references/<int:image_id>/delete')
    def delete_reference(image_id: int):
        row = DB.get_reference_image(image_id)
        if row is None:
            flash('Reference image not found.', 'error')
            return redirect(url_for('references_page'))
        path = Path(row['file_path'])
        DB.delete_reference(image_id)
        path.unlink(missing_ok=True)
        DB.log_audit('reference_delete', f'Deleted reference image {image_id}')
        flash('Reference image deleted.', 'success')
        return redirect(url_for('references_page'))

    @app.post('/test-image')
    def test_image():
        upload = request.files.get('image')
        if not upload or not upload.filename:
            flash('Choose an image file to test.', 'error')
            return redirect(url_for('references_page'))

        references = DB.get_reference_images(active_only=True)
        runtime = DB.get_effective_runtime_config()
        settings = DB.get_guild_settings(runtime['discord_guild_id']) if runtime['discord_guild_id'] else None
        if not references or settings is None:
            flash('Add reference images and finish setup first.', 'error')
            return redirect(url_for('references_page'))

        computed = ImageMatcher.compute_from_bytes(upload.read())
        result = ImageMatcher.compare(
            computed,
            references,
            threshold=int(settings['match_threshold']),
            exact_sha_enabled=bool(settings['exact_sha_enabled']),
        )
        if result.matched and result.reference:
            flash(f"Matched {result.reference['label']} using {result.method} at score {result.score}.", 'success')
        else:
            flash(f'No match. Closest method was {result.method} at score {result.score}.', 'error')
        return redirect(url_for('references_page'))

    @app.get('/references/<int:image_id>/file')
    def reference_file(image_id: int):
        row = DB.get_reference_image(image_id)
        if row is None:
            return 'Not found', 404
        path = Path(row['file_path'])
        if not path.exists():
            return 'Missing file', 404
        return send_file(path)

    @app.route('/audit')
    def audit_page():
        rows = DB.get_audit_log(100)
        return render_template('audit.html', rows=rows)

    @app.get('/api/status')
    def api_status():
        runtime = DB.get_effective_runtime_config()
        return jsonify({
            'setup_complete': runtime['setup_complete'],
            'bot_status': get_bot_status(),
            'guild_id': runtime['discord_guild_id'],
            'host_hint': get_host_hint(),
            'ready_for_bot': bool(runtime['discord_bot_token'] and runtime['discord_guild_id']),
        })

    @app.get('/api/live-summary')
    def api_live_summary():
        return jsonify(DB.get_detection_stats())

    @app.get('/api/live-detections')
    def api_live_detections():
        return jsonify(DB.get_recent_detections(12))

    @app.get('/api/bot-status')
    def api_bot_status():
        return jsonify(get_bot_status())

    return app


def _parse_id_list(raw: str) -> list[int]:
    values: list[int] = []
    for item in raw.split(','):
        item = item.strip()
        if item.isdigit():
            values.append(int(item))
    return values


def _read_bot_pid() -> int | None:
    if not SETTINGS.bot_pid_file.exists():
        return None
    try:
        return int(SETTINGS.bot_pid_file.read_text(encoding='utf-8').strip())
    except Exception:
        return None


def _write_bot_pid(pid: int | None) -> None:
    if pid is None:
        SETTINGS.bot_pid_file.unlink(missing_ok=True)
        return
    SETTINGS.bot_pid_file.write_text(str(pid), encoding='utf-8')


def _pid_running(pid: int) -> bool:
    try:
        if os.name == 'nt':
            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
            return str(pid) in result.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start_bot_process() -> tuple[bool, str]:
    runtime = DB.get_effective_runtime_config()
    if not runtime['discord_bot_token'] or not runtime['discord_guild_id']:
        return False, 'Finish setup before starting the bot.'

    pid = _read_bot_pid()
    if pid and _pid_running(pid):
        return True, 'Bot is already running.'

    cmd = [sys.executable, 'run_bot.py']
    kwargs: dict[str, Any] = {'cwd': str(SETTINGS.env_path.parent)}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
    else:
        kwargs['start_new_session'] = True
    proc = subprocess.Popen(cmd, **kwargs)
    _write_bot_pid(proc.pid)
    return True, 'Bot start requested.'


def stop_bot_process() -> tuple[bool, str]:
    pid = _read_bot_pid()
    if not pid:
        SETTINGS.bot_state_file.unlink(missing_ok=True)
        return True, 'Bot was not running.'

    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, text=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    _write_bot_pid(None)
    SETTINGS.bot_state_file.unlink(missing_ok=True)
    return True, 'Bot stop requested.'


def get_bot_status() -> dict[str, Any]:
    default = {'connected': False, 'detail': 'offline', 'updated_at': None, 'fresh': False}
    pid = _read_bot_pid()
    pid_alive = bool(pid and _pid_running(pid))

    if not SETTINGS.bot_state_file.exists():
        if pid_alive:
            return {'connected': True, 'detail': 'starting', 'updated_at': None, 'fresh': True}
        return default

    try:
        payload = json.loads(SETTINGS.bot_state_file.read_text(encoding='utf-8'))
        updated_at = payload.get('updated_at')
        fresh = False
        if updated_at:
            timestamp = datetime.fromisoformat(updated_at)
            fresh = (datetime.now(timezone.utc) - timestamp).total_seconds() <= 45

        if fresh and payload.get('connected', False):
            payload['fresh'] = True
            return payload

        if pid_alive:
            payload['fresh'] = True
            payload['connected'] = True
            if not payload.get('detail') or payload.get('detail') == 'offline':
                payload['detail'] = 'starting'
            return payload

        payload['fresh'] = False
        payload['connected'] = False
        payload['detail'] = 'offline'
        return payload
    except Exception:
        if pid_alive:
            return {'connected': True, 'detail': 'starting', 'updated_at': None, 'fresh': True}
        return default


def get_host_hint() -> str:
    return 'Use http://localhost:5000 on this PC or your local network IP if you opened it on 0.0.0.0.'