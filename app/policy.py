from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HoneypotDecision:
    triggered: bool
    action_type: str
    delete_message: bool
    reason: str


@dataclass
class PolicyDecision:
    allowed_to_scan: bool
    skip_reason: str
    action_type: str
    timeout_minutes: int
    delete_on_match: bool
    notify_on_match: bool
    reason: str


class PolicyEngine:
    PRESETS: dict[str, dict[str, Any]] = {
        "safe": {
            "match_threshold": 6,
            "delete_on_match": True,
            "notify_on_match": True,
            "action_type": "timeout",
            "timeout_minutes": 60,
            "escalate_repeat_offenders": True,
            "repeat_window_minutes": 120,
            "repeat_ban_count": 4,
        },
        "balanced": {
            "match_threshold": 8,
            "delete_on_match": True,
            "notify_on_match": True,
            "action_type": "timeout",
            "timeout_minutes": 180,
            "escalate_repeat_offenders": True,
            "repeat_window_minutes": 180,
            "repeat_ban_count": 3,
        },
        "aggressive": {
            "match_threshold": 10,
            "delete_on_match": True,
            "notify_on_match": True,
            "action_type": "kick",
            "timeout_minutes": 720,
            "escalate_repeat_offenders": True,
            "repeat_window_minutes": 240,
            "repeat_ban_count": 2,
        },
    }

    @staticmethod
    def member_is_exempt(member: Any, settings: dict[str, Any], key: str = 'exempt_role_ids') -> bool:
        exempt_role_ids = set(settings.get(key, []))
        if not exempt_role_ids:
            return False
        for role in getattr(member, "roles", []):
            if int(role.id) in exempt_role_ids:
                return True
        return False

    @staticmethod
    def honeypot_decision(message: Any, settings: dict[str, Any]) -> HoneypotDecision:
        honeypot_channel_id = settings.get('honeypot_channel_id')
        if not honeypot_channel_id:
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Honeypot disabled')

        if message.guild is None:
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'DM message')

        if int(message.channel.id) != int(honeypot_channel_id):
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Not honeypot channel')

        if settings.get('ignore_bots') and getattr(message.author, 'bot', False):
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Bots are ignored')

        if PolicyEngine.member_is_exempt(message.author, settings):
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Member has an exempt role')

        if PolicyEngine.member_is_exempt(message.author, settings, 'honeypot_exempt_role_ids'):
            return HoneypotDecision(False, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Member has a honeypot exempt role')

        return HoneypotDecision(True, settings.get('honeypot_action', 'ban'), bool(settings.get('honeypot_delete_message', True)), 'Posted in honeypot channel')

    @staticmethod
    def should_scan(message: Any, settings: dict[str, Any]) -> PolicyDecision:
        if message.guild is None:
            return PolicyDecision(False, "dm", settings["action_type"], settings["timeout_minutes"], settings["delete_on_match"], settings["notify_on_match"], "DM message")

        if int(message.channel.id) in set(settings["exempt_channel_ids"]):
            return PolicyDecision(False, "channel_exempt", settings["action_type"], settings["timeout_minutes"], settings["delete_on_match"], settings["notify_on_match"], "Channel is exempt")

        if settings["ignore_bots"] and getattr(message.author, "bot", False):
            return PolicyDecision(False, "author_is_bot", settings["action_type"], settings["timeout_minutes"], settings["delete_on_match"], settings["notify_on_match"], "Bots are ignored")

        if PolicyEngine.member_is_exempt(message.author, settings):
            return PolicyDecision(False, "role_exempt", settings["action_type"], settings["timeout_minutes"], settings["delete_on_match"], settings["notify_on_match"], "Member has an exempt role")

        return PolicyDecision(True, "", settings["action_type"], settings["timeout_minutes"], settings["delete_on_match"], settings["notify_on_match"], "Matched known spam image")

    @staticmethod
    def resolve_action(settings: dict[str, Any], recent_actions: list[dict[str, Any]]) -> tuple[str, int]:
        action = settings["action_type"]
        timeout_minutes = int(settings["timeout_minutes"])

        if settings["escalate_repeat_offenders"]:
            offense_count = len(recent_actions)
            if offense_count + 1 >= int(settings["repeat_ban_count"]):
                return "ban", timeout_minutes
            if offense_count >= 1 and action in {"delete", "none"}:
                return "timeout", timeout_minutes

        return action, timeout_minutes
