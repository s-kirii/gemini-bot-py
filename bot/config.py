from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


FAMILY_ID_PATTERN = re.compile(r"^FAMILY_ID(\d+)$")


@dataclass(frozen=True)
class AppConfig:
    discord_token: str
    discord_server_id: int
    gemini_api_key: str
    gemini_model: str
    system_prompt_path: Path
    history_path: Path
    max_history_items: int
    family_name_map: dict[str, str]


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Environment variable `{name}` is required.")
    return value


def _build_family_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, value in os.environ.items():
        match = FAMILY_ID_PATTERN.match(key)
        if not match or not value:
            continue

        suffix = match.group(1)
        name_key = f"FAMILY_NAME{suffix}"
        display_name = os.getenv(name_key)
        if display_name:
            mapping[value] = display_name
    return mapping


def load_config() -> AppConfig:
    load_dotenv()

    discord_token = _required("DISCORD_TOKEN")
    discord_server_id = int(_required("DISCORD_SERVER_ID"))
    gemini_api_key = _required("GEMINI_API_KEY")

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    system_prompt_path = Path(os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.txt"))
    history_path = Path(os.getenv("HISTORY_PATH", "data/history.json"))
    max_history_items = int(os.getenv("MAX_HISTORY_ITEMS", "10"))

    if max_history_items < 2:
        raise ConfigError("`MAX_HISTORY_ITEMS` must be at least 2.")

    return AppConfig(
        discord_token=discord_token,
        discord_server_id=discord_server_id,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        system_prompt_path=system_prompt_path,
        history_path=history_path,
        max_history_items=max_history_items,
        family_name_map=_build_family_map(),
    )
