from __future__ import annotations

import asyncio
from pathlib import Path

from bot.history_store import HistoryStore


def test_append_turn_keeps_latest_items(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = HistoryStore(tmp_path / "history.json")

        await store.append_turn("u1", "p1", "a1", max_items=4)
        await store.append_turn("u1", "p2", "a2", max_items=4)
        await store.append_turn("u1", "p3", "a3", max_items=4)

        history = await store.get("u1")

        assert len(history) == 4
        assert history[0]["parts"][0]["text"] == "p2"
        assert history[-1]["parts"][0]["text"] == "a3"

    asyncio.run(scenario())
