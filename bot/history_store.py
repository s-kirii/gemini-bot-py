from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def get(self, user_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            data = self._read()
            history = data.get(user_id, [])
            if not isinstance(history, list):
                return []
            return history

    async def append_turn(
        self,
        user_id: str,
        user_prompt: str,
        model_response: str,
        max_items: int,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            data = self._read()
            history = data.get(user_id, [])
            if not isinstance(history, list):
                history = []

            history.append({"role": "user", "parts": [{"text": user_prompt}]})
            history.append({"role": "model", "parts": [{"text": model_response}]})
            history = history[-max_items:]

            data[user_id] = history
            self._write(data)
            return history

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}

        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(self._path)
