from __future__ import annotations

from datetime import timedelta
from typing import Any

import discord

from app.db import DB


class ActionService:
    @staticmethod
    async def apply_action(message: discord.Message, action_type: str, timeout_minutes: int, reason: str) -> str:
        guild = message.guild
        member = message.author
        if guild is None or not isinstance(member, discord.Member):
            return "none"

        applied = action_type
        try:
            if action_type == "timeout":
                await member.timeout(timedelta(minutes=timeout_minutes), reason=reason)
            elif action_type == "kick":
                await guild.kick(member, reason=reason)
            elif action_type == "ban":
                await guild.ban(member, reason=reason, delete_message_seconds=0)
            elif action_type in {"delete", "none"}:
                applied = action_type
            else:
                applied = "none"
        except Exception as exc:
            applied = f"failed:{action_type}"
            reason = f"{reason} | action error: {exc}"

        DB.log_action(guild.id, member.id, str(member), applied, reason)
        return applied
