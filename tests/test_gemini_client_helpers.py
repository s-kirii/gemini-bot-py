from __future__ import annotations

from bot.gemini_client import _format_calendar_result, _safe_json_from_text


def test_safe_json_from_text_extracts_object() -> None:
    text = "結果です\n{\"action\":\"list\",\"args\":{\"query\":\"会議\"}}\nよろしく"
    parsed = _safe_json_from_text(text)

    assert parsed is not None
    assert parsed["action"] == "list"
    assert parsed["args"]["query"] == "会議"


def test_format_calendar_result_list() -> None:
    result = {
        "status": "ok",
        "events": [
            {
                "id": "abc123",
                "summary": "定例会",
                "start": "2026-02-12T10:00:00+09:00",
                "end": "2026-02-12T11:00:00+09:00",
            }
        ],
    }

    text = _format_calendar_result("list", result)

    assert "予定を見つけたよ" in text
    assert "定例会" in text
    assert "abc123" in text
