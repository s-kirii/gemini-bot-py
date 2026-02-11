from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .config import AppConfig
from .gemini_client import GeminiClient
from .history_store import HistoryStore


logger = logging.getLogger(__name__)


class GeminiDiscordBot(commands.Bot):
    def __init__(
        self,
        config: AppConfig,
        history_store: HistoryStore,
        gemini_client: GeminiClient,
    ) -> None:
        intents = discord.Intents.none()
        intents.guilds = True

        super().__init__(command_prefix="/", intents=intents)
        self._config = config
        self._history_store = history_store
        self._gemini_client = gemini_client

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self._config.discord_server_id)

        @self.tree.command(
            name="ask",
            description="Geminiに質問します",
            guild=guild,
        )
        @app_commands.describe(message="質問内容")
        async def ask_command(interaction: discord.Interaction, message: str) -> None:
            await self._handle_ask(interaction, message)

        await self.tree.sync(guild=guild)

    async def _handle_ask(self, interaction: discord.Interaction, message: str) -> None:
        if interaction.guild_id != self._config.discord_server_id:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "このBotはこのサーバーでは使用できません。", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "このBotはこのサーバーでは使用できません。", ephemeral=True
                )
            return

        await interaction.response.defer(thinking=True)

        try:
            user_id = str(interaction.user.id)
            display_name = self._resolve_display_name(interaction.user)
            full_prompt = f"送信者: {display_name}\n内容: {message}"

            history = await self._history_store.get(user_id)
            ai_response = await self._gemini_client.generate_response(full_prompt, history)
            final_response = _fit_discord_message(f"> {message}\n{ai_response}")

            await self._history_store.append_turn(
                user_id=user_id,
                user_prompt=full_prompt,
                model_response=ai_response,
                max_items=self._config.max_history_items,
            )

            await interaction.edit_original_response(content=final_response)
        except Exception as exc:
            logger.exception("Failed to handle /ask command")
            error_message = _fit_discord_message(f"オカメパニック: {exc}")
            await interaction.edit_original_response(content=error_message)

    def _resolve_display_name(self, user: discord.abc.User) -> str:
        mapped_name = self._config.family_name_map.get(str(user.id))
        if mapped_name:
            return mapped_name

        return getattr(user, "global_name", None) or user.name


def _fit_discord_message(content: str) -> str:
    limit = 2000
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "..."
