from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from .calendar_service import CalendarOperationError, GoogleCalendarService


CALENDAR_PLANNER_SYSTEM_PROMPT = """
あなたはDiscord Botのカレンダー操作プランナーです。
ユーザーの依頼を読み、Googleカレンダー操作が必要なら action を決めて JSON だけを返してください。

出力形式:
{
  "action": "none|list|create|update|delete",
  "args": { ... }
}

ルール:
- カレンダー操作でない依頼は action="none"
- list/create/update/delete の args は必要最小限を入れる
- 日時は可能な限り ISO8601/RFC3339（例: 2026-02-12T10:00:00+09:00）を使う
- update/delete で event_id が不明な場合は query を使う
- JSON以外の文字は出力しない
""".strip()


@dataclass(frozen=True)
class CalendarAction:
    action: str
    args: dict[str, Any]


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        session: aiohttp.ClientSession,
        calendar_service: GoogleCalendarService | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._session = session
        self._calendar_service = calendar_service

    async def generate_response(self, prompt: str, history: list[dict[str, Any]]) -> str:
        if self._calendar_service:
            action = await self._plan_calendar_action(prompt, history)
            if action.action != "none":
                result = await self._execute_calendar_action(action)
                return _format_calendar_result(action.action, result)

        return await self._generate_general_response(prompt, history)

    async def _generate_general_response(
        self,
        prompt: str,
        history: list[dict[str, Any]],
    ) -> str:
        payload = {
            "system_instruction": {"parts": [{"text": self._system_prompt}]},
            "contents": [*history, {"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
        data = await self._call_generate_content(payload)
        return _extract_text(data)

    async def _plan_calendar_action(
        self,
        prompt: str,
        history: list[dict[str, Any]],
    ) -> CalendarAction:
        recent_history = history[-4:]
        planning_prompt = (
            "以下の会話文脈と最新メッセージを読んで、"
            "カレンダー操作が必要か判定してください。ユーザーからの日付指定はISO8601(RFC3339)形式に変換してください。\n\n"
            f"最新メッセージ:\n{prompt}"
        )

        payload = {
            "system_instruction": {"parts": [{"text": CALENDAR_PLANNER_SYSTEM_PROMPT}]},
            "contents": [*recent_history, {"role": "user", "parts": [{"text": planning_prompt}]}],
            "generation_config": {"temperature": 0.1},
        }
        data = await self._call_generate_content(payload)

        text = _extract_text(data)
        parsed = _safe_json_from_text(text)
        if not parsed:
            return CalendarAction(action="none", args={})

        action = str(parsed.get("action", "none")).lower().strip()
        args = parsed.get("args", {})
        if action not in {"none", "list", "create", "update", "delete"}:
            return CalendarAction(action="none", args={})
        if not isinstance(args, dict):
            args = {}

        return CalendarAction(action=action, args=args)

    async def _execute_calendar_action(self, action: CalendarAction) -> dict[str, Any]:
        if not self._calendar_service:
            return {
                "status": "error",
                "message": "Google Calendar設定が見つからないため実行できません。",
            }

        try:
            if action.action == "list":
                return await asyncio.to_thread(
                    self._calendar_service.list_events,
                    action.args.get("time_min"),
                    action.args.get("time_max"),
                    action.args.get("query"),
                    int(action.args.get("max_results", 10)),
                )

            if action.action == "create":
                return await asyncio.to_thread(
                    self._calendar_service.create_event,
                    summary=str(action.args.get("summary", "")).strip(),
                    start=str(action.args.get("start", "")).strip(),
                    end=str(action.args.get("end", "")).strip(),
                    description=_opt_str(action.args.get("description")),
                    location=_opt_str(action.args.get("location")),
                    timezone_name=_opt_str(action.args.get("timezone")),
                )

            if action.action == "update":
                return await asyncio.to_thread(
                    self._calendar_service.update_event,
                    event_id=_opt_str(action.args.get("event_id")),
                    query=_opt_str(action.args.get("query")),
                    time_min=_opt_str(action.args.get("time_min")),
                    time_max=_opt_str(action.args.get("time_max")),
                    summary=_opt_str(action.args.get("summary")),
                    start=_opt_str(action.args.get("start")),
                    end=_opt_str(action.args.get("end")),
                    description=_opt_str(action.args.get("description")),
                    location=_opt_str(action.args.get("location")),
                    timezone_name=_opt_str(action.args.get("timezone")),
                )

            if action.action == "delete":
                return await asyncio.to_thread(
                    self._calendar_service.delete_event,
                    event_id=_opt_str(action.args.get("event_id")),
                    query=_opt_str(action.args.get("query")),
                    time_min=_opt_str(action.args.get("time_min")),
                    time_max=_opt_str(action.args.get("time_max")),
                )

            return {"status": "error", "message": "未対応のカレンダー操作です。"}
        except (CalendarOperationError, ValueError) as exc:
            return {"status": "error", "message": str(exc)}

    async def _call_generate_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )

        async with self._session.post(url, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Gemini API error {response.status}: {body}")
            return await response.json()


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_json_from_text(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if not raw:
        return None

    # Planner may occasionally wrap JSON with extra lines; extract first JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    candidate = raw[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not candidates:
        raise RuntimeError("Gemini API returned no candidates.")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    combined = "\n".join(text.strip() for text in texts if text and text.strip())
    if not combined:
        raise RuntimeError("Gemini API returned empty text.")

    return combined


def _format_calendar_result(action: str, result: dict[str, Any]) -> str:
    if result.get("status") != "ok":
        return f"オカメパニック: {result.get('message', 'カレンダー操作に失敗しました。')}"

    if action == "list":
        events = result.get("events", [])
        if not events:
            return "カレンダーに該当する予定は見つからなかったよ。"
        lines = ["予定を見つけたよ。"]
        for idx, event in enumerate(events, start=1):
            lines.append(
                f"{idx}. {event.get('summary', '(無題)')} | {event.get('start', '-')} - {event.get('end', '-')} | id={event.get('id', '-')}"
            )
        return "\n".join(lines)

    if action == "create":
        event = result.get("event", {})
        return (
            "予定を登録したよ。\n"
            f"- 件名: {event.get('summary', '(無題)')}\n"
            f"- 開始: {event.get('start', '-')}\n"
            f"- 終了: {event.get('end', '-')}\n"
            f"- ID: {event.get('id', '-')}"
        )

    if action == "update":
        event = result.get("event", {})
        return (
            "予定を更新したよ。\n"
            f"- 件名: {event.get('summary', '(無題)')}\n"
            f"- 開始: {event.get('start', '-')}\n"
            f"- 終了: {event.get('end', '-')}\n"
            f"- ID: {event.get('id', '-')}"
        )

    if action == "delete":
        return f"予定を削除したよ。ID: {result.get('event_id', '-')}"

    return "カレンダー処理が完了したよ。"
