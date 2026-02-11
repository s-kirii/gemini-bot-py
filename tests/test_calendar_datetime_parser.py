from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot.calendar_service import normalize_datetime_text


def test_normalize_relative_datetime() -> None:
    base = datetime(2026, 2, 11, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    value = normalize_datetime_text("明日19時", "Asia/Tokyo", now=base)

    assert value == "2026-02-12T19:00:00+09:00"


def test_normalize_absolute_datetime() -> None:
    value = normalize_datetime_text("2026-02-20 19:30", "Asia/Tokyo")

    assert value == "2026-02-20T19:30:00+09:00"
