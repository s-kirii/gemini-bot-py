from __future__ import annotations

import asyncio
import logging

import aiohttp

from bot.config import ConfigError, load_config
from bot.discord_bot import GeminiDiscordBot
from bot.gemini_client import GeminiClient
from bot.history_store import HistoryStore


logging.basicConfig(level=logging.INFO)


async def async_main() -> None:
    config = load_config()

    if not config.system_prompt_path.exists():
        raise ConfigError(
            f"System prompt file not found: {config.system_prompt_path}. "
            "Copy system_prompt.txt.sample to system_prompt.txt and edit it."
        )

    system_prompt = config.system_prompt_path.read_text(encoding="utf-8")
    if not system_prompt.strip():
        raise ConfigError(f"System prompt file is empty: {config.system_prompt_path}")

    history_store = HistoryStore(config.history_path)

    async with aiohttp.ClientSession() as session:
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
            system_prompt=system_prompt,
            session=session,
        )
        bot = GeminiDiscordBot(config, history_store, gemini_client)
        await bot.start(config.discord_token)


def main() -> None:
    try:
        asyncio.run(async_main())
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc


if __name__ == "__main__":
    main()
