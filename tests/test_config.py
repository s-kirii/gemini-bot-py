from __future__ import annotations

from bot.config import _build_family_map


def test_build_family_map(monkeypatch) -> None:
    monkeypatch.setenv("FAMILY_ID01", "111")
    monkeypatch.setenv("FAMILY_NAME01", "Alice")
    monkeypatch.setenv("FAMILY_ID02", "222")
    monkeypatch.setenv("FAMILY_NAME02", "Bob")

    mapping = _build_family_map()

    assert mapping == {"111": "Alice", "222": "Bob"}
