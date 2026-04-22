from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from app.config import SETTINGS
from app.db import DB
from app.image_matching import ImageMatcher
from app.policy import PolicyEngine
from app.services.action_service import ActionService

logger = logging.getLogger("spam_guard.bot")


class SpamGuardBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.runtime_config = DB.get_effective_runtime_config()

    async def setup_hook(self) -> None:
        self.tree.add_command(status_command)
        self.tree.add_command(sync_command)
        guild_id = self.runtime_config["discord_guild_id"]
        if guild_id:
            guild_obj = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()
        self.heartbeat.start()

    async def on_ready(self) -> None:
        logger.info("Bot ready as %s (%s)", self.user, self.user.id if self.user else "unknown")
        self.write_state(connected=True, detail="ready")

    async def close(self) -> None:
        self.write_state(connected=False, detail="stopped")
        await super().close()

    def write_state(self, connected: bool, detail: str) -> None:
        payload = {
            "connected": connected,
            "detail": detail,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "user": str(self.user) if self.user else "",
        }
        SETTINGS.bot_state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @tasks.loop(seconds=15)
    async def heartbeat(self) -> None:
        self.write_state(connected=not self.is_closed(), detail="heartbeat")

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        settings = DB.get_guild_settings(message.guild.id)
        if settings is None:
            return

        honeypot = PolicyEngine.honeypot_decision(message, settings)
        if honeypot.triggered:
            deleted_message = False
            if honeypot.delete_message:
                try:
                    await message.delete()
                    deleted_message = True
                except Exception as exc:
                    logger.warning("Failed to delete honeypot message %s: %s", message.id, exc)

            action_taken = await ActionService.apply_action(
                message,
                action_type=honeypot.action_type,
                timeout_minutes=int(settings.get("timeout_minutes", 60)),
                reason=honeypot.reason,
            )

            first_attachment = message.attachments[0] if message.attachments else None
            DB.insert_detection(
                {
                    "guild_id": message.guild.id,
                    "channel_id": message.channel.id,
                    "channel_name": getattr(message.channel, "name", str(message.channel.id)),
                    "message_id": message.id,
                    "user_id": message.author.id,
                    "username": str(message.author),
                    "attachment_filename": first_attachment.filename if first_attachment else "",
                    "attachment_url": first_attachment.url if first_attachment else "",
                    "matched_reference_id": None,
                    "matched_reference_label": "Honeypot channel",
                    "match_method": "honeypot",
                    "match_score": 100,
                    "action_taken": action_taken,
                    "action_reason": honeypot.reason,
                    "deleted_message": deleted_message,
                }
            )

            if bool(settings["notify_on_match"]):
                await self.notify_honeypot_log(message, action_taken, deleted_message)
            return

        if not message.attachments:
            return

        decision = PolicyEngine.should_scan(message, settings)
        if not decision.allowed_to_scan:
            return

        references = DB.get_reference_images(active_only=True)
        if not references:
            return

        for attachment in message.attachments:
            content_type = attachment.content_type or ""
            if not content_type.startswith("image/"):
                continue
            try:
                data = await attachment.read()
                computed = ImageMatcher.compute_from_bytes(data)
                result = ImageMatcher.compare(
                    computed,
                    references,
                    threshold=int(settings["match_threshold"]),
                    exact_sha_enabled=bool(settings["exact_sha_enabled"]),
                )
                if not result.matched or result.reference is None:
                    continue

                recent_actions = DB.get_recent_actions(message.guild.id, message.author.id, int(settings["repeat_window_minutes"]))
                action_type, timeout_minutes = PolicyEngine.resolve_action(settings, recent_actions)

                deleted_message = False
                if bool(settings["delete_on_match"]):
                    try:
                        await message.delete()
                        deleted_message = True
                    except Exception as exc:
                        logger.warning("Failed to delete message %s: %s", message.id, exc)

                reason = f"Matched {result.reference['label']} using {result.method} at score {result.score}."
                action_taken = await ActionService.apply_action(
                    message,
                    action_type=action_type,
                    timeout_minutes=timeout_minutes,
                    reason=reason,
                )

                DB.insert_detection(
                    {
                        "guild_id": message.guild.id,
                        "channel_id": message.channel.id,
                        "channel_name": getattr(message.channel, "name", str(message.channel.id)),
                        "message_id": message.id,
                        "user_id": message.author.id,
                        "username": str(message.author),
                        "attachment_filename": attachment.filename,
                        "attachment_url": attachment.url,
                        "matched_reference_id": result.reference["id"],
                        "matched_reference_label": result.reference["label"],
                        "match_method": result.method,
                        "match_score": result.score,
                        "action_taken": action_taken,
                        "action_reason": f"{decision.reason} | {reason}",
                        "deleted_message": deleted_message,
                    }
                )

                if bool(settings["notify_on_match"]):
                    await self.notify_mod_log(message, attachment, result, action_taken, deleted_message)
                return
            except Exception as exc:
                logger.exception("Error processing attachment on message %s: %s", message.id, exc)

    async def notify_honeypot_log(self, message: discord.Message, action_taken: str, deleted_message: bool) -> None:
        channel_id = self.runtime_config["bot_log_channel_id"]
        channel = self.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.abc.Messageable):
            return

        embed = discord.Embed(title="Honeypot channel trigger", color=0x8B1E1E)
        embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"<#{message.channel.id}>", inline=True)
        embed.add_field(name="Action", value=action_taken, inline=True)
        embed.add_field(name="Deleted", value="yes" if deleted_message else "no", inline=True)
        embed.add_field(name="Why", value="Posted in the configured honeypot channel.", inline=False)
        embed.set_footer(text=f"message id: {message.id}")
        await channel.send(embed=embed)

    async def notify_mod_log(self, message: discord.Message, attachment: discord.Attachment, result: Any, action_taken: str, deleted_message: bool) -> None:
        channel_id = self.runtime_config["bot_log_channel_id"]
        channel = self.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.abc.Messageable):
            return

        embed = discord.Embed(title="Spam image match", color=0xB03030)
        embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"<#{message.channel.id}>", inline=True)
        embed.add_field(name="Reference", value=result.reference["label"], inline=True)
        embed.add_field(name="Method", value=f"{result.method} ({result.score})", inline=True)
        embed.add_field(name="Action", value=action_taken, inline=True)
        embed.add_field(name="Deleted", value="yes" if deleted_message else "no", inline=True)
        embed.add_field(name="Attachment", value=attachment.filename, inline=False)
        embed.add_field(name="Why", value=f"Matched with {result.method} score {result.score} against {result.reference['label']}", inline=False)
        embed.set_footer(text=f"message id: {message.id}")
        await channel.send(embed=embed)


@app_commands.command(name="spamguard_status", description="Show whether Image Spam Guard is online.")
async def status_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("Image Spam Guard is online.", ephemeral=True)


@app_commands.command(name="spamguard_sync", description="Sync application commands.")
async def sync_command(interaction: discord.Interaction) -> None:
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permission for that.", ephemeral=True)
        return

    runtime_config = DB.get_effective_runtime_config()
    guild_id = runtime_config["discord_guild_id"]
    if guild_id:
        guild_obj = discord.Object(id=guild_id)
        await interaction.client.tree.sync(guild=guild_obj)
    else:
        await interaction.client.tree.sync()

    await interaction.response.send_message("Commands synced.", ephemeral=True)


def create_bot() -> SpamGuardBot:
    return SpamGuardBot()
