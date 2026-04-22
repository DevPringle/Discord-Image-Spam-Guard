from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(dotenv_path: str | Path | None = None) -> None:
        path = Path(dotenv_path) if dotenv_path else Path('.env')
        if not path.exists():
            return
        for line in path.read_text(encoding='utf-8').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key, value = stripped.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'
load_dotenv(ENV_PATH)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _as_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _as_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    items: list[int] = []
    for raw in value.split(','):
        raw = raw.strip()
        if raw:
            items.append(int(raw))
    return items


def write_env_updates(updates: dict[str, str | int | None]) -> None:
    existing: dict[str, str] = {}
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            existing[key.strip()] = value

    for key, value in updates.items():
        existing[key] = '' if value is None else str(value)
        os.environ[key] = existing[key]

    ordered_keys = [
        'DISCORD_BOT_TOKEN',
        'DISCORD_GUILD_ID',
        'DASHBOARD_SECRET_KEY',
        'DASHBOARD_PASSWORD',
        'BOT_LOG_CHANNEL_ID',
        'DATABASE_PATH',
        'REFERENCE_IMAGE_DIR',
        'BOT_STATE_FILE',
        'BOT_PID_FILE',
        'MOD_LOG_RETENTION_DAYS',
        'DEFAULT_MATCH_THRESHOLD',
        'DEFAULT_EXACT_SHA_ENABLED',
        'DEFAULT_DELETE_ON_MATCH',
        'DEFAULT_NOTIFY_ON_MATCH',
        'DEFAULT_ACTION',
        'DEFAULT_TIMEOUT_MINUTES',
        'DEFAULT_ESCALATE_REPEAT_OFFENDERS',
        'DEFAULT_REPEAT_WINDOW_MINUTES',
        'DEFAULT_REPEAT_BAN_COUNT',
        'DEFAULT_IGNORE_BOTS',
        'DEFAULT_EXEMPT_ROLE_IDS',
        'DEFAULT_EXEMPT_CHANNEL_IDS',
        'DEFAULT_HONEYPOT_CHANNEL_ID',
        'DEFAULT_HONEYPOT_ACTION',
        'DEFAULT_HONEYPOT_DELETE_MESSAGE',
        'DEFAULT_HONEYPOT_EXEMPT_ROLE_IDS',
    ]
    for key in existing:
        if key not in ordered_keys:
            ordered_keys.append(key)

    output = [f'{key}={existing.get(key, "")}' for key in ordered_keys if key in existing]
    ENV_PATH.write_text('\n'.join(output) + '\n', encoding='utf-8')


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int | None
    dashboard_secret_key: str
    dashboard_password: str
    bot_log_channel_id: int | None
    database_path: Path
    reference_image_dir: Path
    bot_state_file: Path
    bot_pid_file: Path
    env_path: Path
    mod_log_retention_days: int
    default_match_threshold: int
    default_exact_sha_enabled: bool
    default_delete_on_match: bool
    default_notify_on_match: bool
    default_action: str
    default_timeout_minutes: int
    default_escalate_repeat_offenders: bool
    default_repeat_window_minutes: int
    default_repeat_ban_count: int
    default_ignore_bots: bool
    default_exempt_role_ids: list[int]
    default_exempt_channel_ids: list[int]
    default_honeypot_channel_id: int | None
    default_honeypot_action: str
    default_honeypot_delete_message: bool
    default_honeypot_exempt_role_ids: list[int]


SETTINGS = Settings(
    discord_bot_token=os.getenv('DISCORD_BOT_TOKEN', ''),
    discord_guild_id=int(os.getenv('DISCORD_GUILD_ID')) if os.getenv('DISCORD_GUILD_ID') else None,
    dashboard_secret_key=os.getenv('DASHBOARD_SECRET_KEY', 'change_me'),
    dashboard_password=os.getenv('DASHBOARD_PASSWORD', 'change_me'),
    bot_log_channel_id=int(os.getenv('BOT_LOG_CHANNEL_ID')) if os.getenv('BOT_LOG_CHANNEL_ID') else None,
    database_path=BASE_DIR / os.getenv('DATABASE_PATH', 'data/app.db'),
    reference_image_dir=BASE_DIR / os.getenv('REFERENCE_IMAGE_DIR', 'data/reference_images'),
    bot_state_file=BASE_DIR / os.getenv('BOT_STATE_FILE', 'data/bot_state.json'),
    bot_pid_file=BASE_DIR / os.getenv('BOT_PID_FILE', 'data/bot.pid'),
    env_path=ENV_PATH,
    mod_log_retention_days=_as_int(os.getenv('MOD_LOG_RETENTION_DAYS'), 30),
    default_match_threshold=_as_int(os.getenv('DEFAULT_MATCH_THRESHOLD'), 8),
    default_exact_sha_enabled=_as_bool(os.getenv('DEFAULT_EXACT_SHA_ENABLED'), True),
    default_delete_on_match=_as_bool(os.getenv('DEFAULT_DELETE_ON_MATCH'), True),
    default_notify_on_match=_as_bool(os.getenv('DEFAULT_NOTIFY_ON_MATCH'), True),
    default_action=os.getenv('DEFAULT_ACTION', 'timeout').strip().lower(),
    default_timeout_minutes=_as_int(os.getenv('DEFAULT_TIMEOUT_MINUTES'), 60),
    default_escalate_repeat_offenders=_as_bool(os.getenv('DEFAULT_ESCALATE_REPEAT_OFFENDERS'), True),
    default_repeat_window_minutes=_as_int(os.getenv('DEFAULT_REPEAT_WINDOW_MINUTES'), 120),
    default_repeat_ban_count=_as_int(os.getenv('DEFAULT_REPEAT_BAN_COUNT'), 3),
    default_ignore_bots=_as_bool(os.getenv('DEFAULT_IGNORE_BOTS'), True),
    default_exempt_role_ids=_as_int_list(os.getenv('DEFAULT_EXEMPT_ROLE_IDS')),
    default_exempt_channel_ids=_as_int_list(os.getenv('DEFAULT_EXEMPT_CHANNEL_IDS')),
    default_honeypot_channel_id=int(os.getenv('DEFAULT_HONEYPOT_CHANNEL_ID')) if os.getenv('DEFAULT_HONEYPOT_CHANNEL_ID') else None,
    default_honeypot_action=os.getenv('DEFAULT_HONEYPOT_ACTION', 'ban').strip().lower(),
    default_honeypot_delete_message=_as_bool(os.getenv('DEFAULT_HONEYPOT_DELETE_MESSAGE'), True),
    default_honeypot_exempt_role_ids=_as_int_list(os.getenv('DEFAULT_HONEYPOT_EXEMPT_ROLE_IDS')),
)

SETTINGS.database_path.parent.mkdir(parents=True, exist_ok=True)
SETTINGS.reference_image_dir.mkdir(parents=True, exist_ok=True)
SETTINGS.bot_state_file.parent.mkdir(parents=True, exist_ok=True)
SETTINGS.bot_pid_file.parent.mkdir(parents=True, exist_ok=True)
