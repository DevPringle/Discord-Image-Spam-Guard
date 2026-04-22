from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config import SETTINGS

try:
    import psutil
except ModuleNotFoundError:
    psutil = None

ROOT_DIR = SETTINGS.env_path.parent
RUN_BOT = ROOT_DIR / 'run_bot.py'
META_FILE = SETTINGS.bot_state_file.parent / 'bot_process.json'


def _meta_payload(pid: int) -> dict[str, str | int]:
    return {
        'pid': pid,
        'run_bot_path': str(RUN_BOT.resolve()),
        'project_root': str(ROOT_DIR.resolve()),
        'python_exe': sys.executable,
        'saved_at': int(time.time()),
    }


def _read_meta() -> dict[str, str | int] | None:
    if not META_FILE.exists():
        return None
    try:
        return json.loads(META_FILE.read_text(encoding='utf-8'))
    except Exception:
        return None


def _write_meta(pid: int) -> None:
    META_FILE.write_text(json.dumps(_meta_payload(pid), indent=2), encoding='utf-8')
    SETTINGS.bot_pid_file.write_text(str(pid), encoding='utf-8')


def _clear_meta() -> None:
    META_FILE.unlink(missing_ok=True)
    SETTINGS.bot_pid_file.unlink(missing_ok=True)


def _pid_from_meta() -> int | None:
    meta = _read_meta()
    if not meta:
        return None
    try:
        return int(meta.get('pid')) 
    except Exception:
        return None


def _pid_matches_project(pid: int) -> bool:
    if psutil is None:
        return True
    try:
        proc = psutil.Process(pid)
        cmdline = [part.lower() for part in proc.cmdline()]
        cmdline_text = ' '.join(cmdline)
        run_bot_path = str(RUN_BOT.resolve()).lower()
        root_path = str(ROOT_DIR.resolve()).lower()
        return 'run_bot.py' in cmdline_text and run_bot_path in cmdline_text and root_path in cmdline_text
    except Exception:
        return False


def is_running() -> bool:
    pid = _pid_from_meta()
    if not pid:
        return False
    if psutil is None:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            _clear_meta()
            return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            _clear_meta()
            return False
        if not _pid_matches_project(pid):
            return False
        return True
    except Exception:
        _clear_meta()
        return False


def start_bot() -> tuple[bool, str]:
    if is_running():
        return False, 'Bot is already online.'
    cmd = [sys.executable, str(RUN_BOT)]
    kwargs: dict[str, object] = {'cwd': str(ROOT_DIR)}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    proc = subprocess.Popen(cmd, **kwargs)
    _write_meta(proc.pid)
    return True, 'Bot started.'


def stop_bot() -> tuple[bool, str]:
    pid = _pid_from_meta()
    if not pid:
        SETTINGS.bot_state_file.unlink(missing_ok=True)
        return True, 'Bot was not running.'
    if not _pid_matches_project(pid):
        return False, 'Tracked bot process did not match this project.'

    try:
        if os.name == 'nt':
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    deadline = time.time() + 8
    while time.time() < deadline:
        if not is_running():
            _clear_meta()
            SETTINGS.bot_state_file.unlink(missing_ok=True)
            return True, 'Bot stopped.'
        time.sleep(0.4)

    try:
        if psutil is not None:
            psutil.Process(pid).kill()
        elif os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, text=True)
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass

    _clear_meta()
    SETTINGS.bot_state_file.unlink(missing_ok=True)
    return True, 'Bot stopped.'


def restart_bot() -> tuple[bool, str]:
    stop_ok, stop_msg = stop_bot()
    if not stop_ok:
        return False, stop_msg
    time.sleep(1.0)
    return start_bot()


def get_bot_status() -> dict[str, object]:
    default: dict[str, object] = {'connected': False, 'detail': 'offline', 'updated_at': None, 'fresh': False}
    if not SETTINGS.bot_state_file.exists():
        default['fresh'] = is_running()
        if default['fresh']:
            default['connected'] = True
            default['detail'] = 'online'
        return default
    try:
        payload = json.loads(SETTINGS.bot_state_file.read_text(encoding='utf-8'))
        updated_at = payload.get('updated_at')
        fresh = False
        if updated_at:
            from datetime import datetime, timezone
            timestamp = datetime.fromisoformat(updated_at)
            fresh = (datetime.now(timezone.utc) - timestamp).total_seconds() <= 45
        payload['fresh'] = fresh and bool(payload.get('connected', False)) and is_running()
        if not payload['fresh'] and is_running():
            payload['connected'] = True
            payload['detail'] = 'online'
            payload['fresh'] = True
        return payload
    except Exception:
        default['fresh'] = is_running()
        if default['fresh']:
            default['connected'] = True
            default['detail'] = 'online'
        return default
