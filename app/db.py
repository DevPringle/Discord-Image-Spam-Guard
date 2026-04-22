from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import SETTINGS


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    match_threshold INTEGER NOT NULL,
                    exact_sha_enabled INTEGER NOT NULL,
                    delete_on_match INTEGER NOT NULL,
                    notify_on_match INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    timeout_minutes INTEGER NOT NULL,
                    escalate_repeat_offenders INTEGER NOT NULL,
                    repeat_window_minutes INTEGER NOT NULL,
                    repeat_ban_count INTEGER NOT NULL,
                    ignore_bots INTEGER NOT NULL,
                    exempt_role_ids_json TEXT NOT NULL,
                    exempt_channel_ids_json TEXT NOT NULL,
                    honeypot_channel_id INTEGER,
                    honeypot_action TEXT NOT NULL DEFAULT 'ban',
                    honeypot_delete_message INTEGER NOT NULL DEFAULT 1,
                    honeypot_exempt_role_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reference_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    phash TEXT NOT NULL,
                    dhash TEXT NOT NULL,
                    whash TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_reference_images_sha256 ON reference_images(sha256);

                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    attachment_filename TEXT NOT NULL,
                    attachment_url TEXT NOT NULL,
                    matched_reference_id INTEGER,
                    matched_reference_label TEXT,
                    match_method TEXT NOT NULL,
                    match_score INTEGER NOT NULL,
                    action_taken TEXT NOT NULL,
                    action_reason TEXT NOT NULL,
                    deleted_message INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(matched_reference_id) REFERENCES reference_images(id)
                );

                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                (key,),
            ).fetchone()
        return row["setting_value"] if row else default

    def set_app_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (key, value, self.utcnow()),
            )

    def get_app_settings(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT setting_key, setting_value FROM app_settings").fetchall()
        return {row["setting_key"]: row["setting_value"] for row in rows}

    def app_is_configured(self) -> bool:
        values = self.get_app_settings()
        return bool(values.get("discord_bot_token") and values.get("discord_guild_id") and values.get("dashboard_password"))

    def get_effective_runtime_config(self) -> dict[str, Any]:
        values = self.get_app_settings()
        token = values.get("discord_bot_token") or SETTINGS.discord_bot_token
        guild_raw = values.get("discord_guild_id")
        guild_id = int(guild_raw) if guild_raw and guild_raw.isdigit() else SETTINGS.discord_guild_id
        password = values.get("dashboard_password") or SETTINGS.dashboard_password
        secret_key = values.get("dashboard_secret_key") or SETTINGS.dashboard_secret_key
        log_raw = values.get("bot_log_channel_id")
        bot_log_channel_id = int(log_raw) if log_raw and log_raw.isdigit() else SETTINGS.bot_log_channel_id
        setup_complete = values.get("setup_complete", "0") == "1" or self.app_is_configured()
        return {
            "discord_bot_token": token,
            "discord_guild_id": guild_id,
            "dashboard_password": password,
            "dashboard_secret_key": secret_key,
            "bot_log_channel_id": bot_log_channel_id,
            "setup_complete": setup_complete,
        }

    def complete_setup(self, payload: dict[str, str]) -> None:
        now = self.utcnow()
        with self.connect() as conn:
            for key, value in payload.items():
                conn.execute(
                    """
                    INSERT INTO app_settings (setting_key, setting_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET
                        setting_value = excluded.setting_value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, now),
                )
            conn.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_at)
                VALUES ('setup_complete', '1', ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = '1',
                    updated_at = excluded.updated_at
                """,
                (now,),
            )

    def ensure_guild_settings(self, guild_id: int) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT guild_id FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                return
            now = self.utcnow()
            conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, match_threshold, exact_sha_enabled, delete_on_match,
                    notify_on_match, action_type, timeout_minutes,
                    escalate_repeat_offenders, repeat_window_minutes,
                    repeat_ban_count, ignore_bots, exempt_role_ids_json,
                    exempt_channel_ids_json, honeypot_channel_id, honeypot_action,
                    honeypot_delete_message, honeypot_exempt_role_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    SETTINGS.default_match_threshold,
                    int(SETTINGS.default_exact_sha_enabled),
                    int(SETTINGS.default_delete_on_match),
                    int(SETTINGS.default_notify_on_match),
                    SETTINGS.default_action,
                    SETTINGS.default_timeout_minutes,
                    int(SETTINGS.default_escalate_repeat_offenders),
                    SETTINGS.default_repeat_window_minutes,
                    SETTINGS.default_repeat_ban_count,
                    int(SETTINGS.default_ignore_bots),
                    json.dumps(SETTINGS.default_exempt_role_ids),
                    json.dumps(SETTINGS.default_exempt_channel_ids),
                    SETTINGS.default_honeypot_channel_id,
                    SETTINGS.default_honeypot_action,
                    int(SETTINGS.default_honeypot_delete_message),
                    json.dumps(SETTINGS.default_honeypot_exempt_role_ids),
                    now,
                    now,
                ),
            )

    def get_guild_settings(self, guild_id: int | None) -> dict[str, Any] | None:
        if guild_id is None:
            return None
        self.ensure_guild_settings(guild_id)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        if row is None:
            return None
        row["exact_sha_enabled"] = bool(row["exact_sha_enabled"])
        row["delete_on_match"] = bool(row["delete_on_match"])
        row["notify_on_match"] = bool(row["notify_on_match"])
        row["escalate_repeat_offenders"] = bool(row["escalate_repeat_offenders"])
        row["ignore_bots"] = bool(row["ignore_bots"])
        row["honeypot_delete_message"] = bool(row.get("honeypot_delete_message", 1))
        row["exempt_role_ids"] = json.loads(row.pop("exempt_role_ids_json"))
        row["exempt_channel_ids"] = json.loads(row.pop("exempt_channel_ids_json"))
        row["honeypot_exempt_role_ids"] = json.loads(row.pop("honeypot_exempt_role_ids_json", '[]'))
        return row

    def update_guild_settings(self, guild_id: int, payload: dict[str, Any]) -> None:
        self.ensure_guild_settings(guild_id)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE guild_settings SET
                    match_threshold = ?,
                    exact_sha_enabled = ?,
                    delete_on_match = ?,
                    notify_on_match = ?,
                    action_type = ?,
                    timeout_minutes = ?,
                    escalate_repeat_offenders = ?,
                    repeat_window_minutes = ?,
                    repeat_ban_count = ?,
                    ignore_bots = ?,
                    exempt_role_ids_json = ?,
                    exempt_channel_ids_json = ?,
                    honeypot_channel_id = ?,
                    honeypot_action = ?,
                    honeypot_delete_message = ?,
                    honeypot_exempt_role_ids_json = ?,
                    updated_at = ?
                WHERE guild_id = ?
                """,
                (
                    payload["match_threshold"],
                    int(payload["exact_sha_enabled"]),
                    int(payload["delete_on_match"]),
                    int(payload["notify_on_match"]),
                    payload["action_type"],
                    payload["timeout_minutes"],
                    int(payload["escalate_repeat_offenders"]),
                    payload["repeat_window_minutes"],
                    payload["repeat_ban_count"],
                    int(payload["ignore_bots"]),
                    json.dumps(payload["exempt_role_ids"]),
                    json.dumps(payload["exempt_channel_ids"]),
                    payload.get("honeypot_channel_id"),
                    payload.get("honeypot_action", "ban"),
                    int(payload.get("honeypot_delete_message", True)),
                    json.dumps(payload.get("honeypot_exempt_role_ids", [])),
                    self.utcnow(),
                    guild_id,
                ),
            )

    def add_reference_image(self, payload: dict[str, Any]) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reference_images (
                    label, notes, file_path, sha256, phash, dhash, whash,
                    width, height, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["label"],
                    payload.get("notes", ""),
                    payload["file_path"],
                    payload["sha256"],
                    payload["phash"],
                    payload["dhash"],
                    payload["whash"],
                    payload["width"],
                    payload["height"],
                    int(payload.get("active", True)),
                    self.utcnow(),
                    self.utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def get_reference_images(self, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM reference_images"
        params: tuple[Any, ...] = ()
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY id DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        for row in rows:
            row["active"] = bool(row["active"])
        return rows

    def get_reference_image(self, image_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reference_images WHERE id = ?", (image_id,)).fetchone()
        if row:
            row["active"] = bool(row["active"])
        return row

    def update_reference_status(self, image_id: int, active: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE reference_images SET active = ?, updated_at = ? WHERE id = ?",
                (int(active), self.utcnow(), image_id),
            )

    def update_reference_metadata(self, image_id: int, label: str, notes: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE reference_images SET label = ?, notes = ?, updated_at = ? WHERE id = ?",
                (label, notes, self.utcnow(), image_id),
            )

    def delete_reference(self, image_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM reference_images WHERE id = ?", (image_id,))

    def insert_detection(self, payload: dict[str, Any]) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detections (
                    guild_id, channel_id, channel_name, message_id,
                    user_id, username, attachment_filename, attachment_url,
                    matched_reference_id, matched_reference_label,
                    match_method, match_score, action_taken, action_reason,
                    deleted_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["guild_id"],
                    payload["channel_id"],
                    payload["channel_name"],
                    payload["message_id"],
                    payload["user_id"],
                    payload["username"],
                    payload["attachment_filename"],
                    payload["attachment_url"],
                    payload.get("matched_reference_id"),
                    payload.get("matched_reference_label"),
                    payload["match_method"],
                    payload["match_score"],
                    payload["action_taken"],
                    payload["action_reason"],
                    int(payload["deleted_message"]),
                    self.utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def log_action(self, guild_id: int, user_id: int, username: str, action_type: str, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO action_log (guild_id, user_id, username, action_type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, username, action_type, reason, self.utcnow()),
            )

    def get_recent_actions(self, guild_id: int, user_id: int, window_minutes: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM action_log
                WHERE guild_id = ? AND user_id = ? AND created_at >= ?
                ORDER BY id DESC
                """,
                (guild_id, user_id, cutoff.isoformat()),
            ).fetchall()

    def get_recent_detections(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM detections ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_detection_stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            totals = conn.execute("SELECT COUNT(*) AS total_detections FROM detections").fetchone()
            refs = conn.execute("SELECT COUNT(*) AS total_reference_images FROM reference_images WHERE active = 1").fetchone()
            actions = conn.execute(
                "SELECT action_taken, COUNT(*) AS count FROM detections GROUP BY action_taken ORDER BY count DESC"
            ).fetchall()
            latest = conn.execute("SELECT created_at FROM detections ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "total_detections": totals["total_detections"],
            "total_reference_images": refs["total_reference_images"],
            "actions": actions,
            "latest_detection_at": latest["created_at"] if latest else None,
        }

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def log_audit(self, event_type: str, summary: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO admin_audit_log (event_type, summary, created_at) VALUES (?, ?, ?)",
                (event_type, summary, self.utcnow()),
            )


DB = Database(SETTINGS.database_path)
