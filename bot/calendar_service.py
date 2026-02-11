from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarOperationError(RuntimeError):
    pass


class GoogleCalendarService:
    def __init__(
        self,
        calendar_id: str,
        service_account_file: str,
        calendar_timezone: str = "Asia/Tokyo",
    ) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=SCOPES,
        )
        self._calendar_id = calendar_id
        self._calendar_timezone = calendar_timezone
        self._service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        max_results = max(1, min(max_results, 20))
        try:
            response = (
                self._service.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    q=query,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as exc:
            raise CalendarOperationError(f"Google Calendar list error: {exc}") from exc

        items = response.get("items", [])
        events = [self._event_summary(event) for event in items]
        return {
            "status": "ok",
            "operation": "list",
            "count": len(events),
            "events": events,
        }

    def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        self._validate_datetime_range(start, end)

        tz_name = timezone_name or self._calendar_timezone
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": tz_name},
            "end": {"dateTime": end, "timeZone": tz_name},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        try:
            created = (
                self._service.events()
                .insert(calendarId=self._calendar_id, body=body)
                .execute()
            )
        except HttpError as exc:
            raise CalendarOperationError(f"Google Calendar create error: {exc}") from exc

        return {
            "status": "ok",
            "operation": "create",
            "event": self._event_summary(created),
        }

    def update_event(
        self,
        event_id: str | None = None,
        query: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        resolved_event_id = self._resolve_event_id(
            event_id=event_id,
            query=query,
            time_min=time_min,
            time_max=time_max,
        )
        if start and end:
            self._validate_datetime_range(start, end)

        patch: dict[str, Any] = {}
        tz_name = timezone_name or self._calendar_timezone

        if summary is not None:
            patch["summary"] = summary
        if description is not None:
            patch["description"] = description
        if location is not None:
            patch["location"] = location
        if start is not None:
            patch["start"] = {"dateTime": start, "timeZone": tz_name}
        if end is not None:
            patch["end"] = {"dateTime": end, "timeZone": tz_name}

        if not patch:
            raise CalendarOperationError("更新内容が指定されていません。")

        try:
            updated = (
                self._service.events()
                .patch(
                    calendarId=self._calendar_id,
                    eventId=resolved_event_id,
                    body=patch,
                )
                .execute()
            )
        except HttpError as exc:
            raise CalendarOperationError(f"Google Calendar update error: {exc}") from exc

        return {
            "status": "ok",
            "operation": "update",
            "event": self._event_summary(updated),
        }

    def delete_event(
        self,
        event_id: str | None = None,
        query: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> dict[str, Any]:
        resolved_event_id = self._resolve_event_id(
            event_id=event_id,
            query=query,
            time_min=time_min,
            time_max=time_max,
        )

        try:
            self._service.events().delete(
                calendarId=self._calendar_id,
                eventId=resolved_event_id,
            ).execute()
        except HttpError as exc:
            raise CalendarOperationError(f"Google Calendar delete error: {exc}") from exc

        return {
            "status": "ok",
            "operation": "delete",
            "event_id": resolved_event_id,
        }

    def _resolve_event_id(
        self,
        event_id: str | None,
        query: str | None,
        time_min: str | None,
        time_max: str | None,
    ) -> str:
        if event_id:
            return event_id

        if not query:
            raise CalendarOperationError("event_id か query のどちらかが必要です。")

        search_start = time_min or _rfc3339_utc(datetime.now(timezone.utc) - timedelta(days=30))
        search_end = time_max or _rfc3339_utc(datetime.now(timezone.utc) + timedelta(days=365))

        listed = self.list_events(
            time_min=search_start,
            time_max=search_end,
            query=query,
            max_results=5,
        )
        events = listed.get("events", [])

        if not events:
            raise CalendarOperationError("該当する予定が見つかりませんでした。")

        if len(events) > 1:
            names = [f"{e.get('summary', '(無題)')} ({e.get('start', '')})" for e in events]
            joined = " / ".join(names)
            raise CalendarOperationError(
                "候補が複数あるため特定できません。event_id を指定してください。"
                f" 候補: {joined}"
            )

        only = events[0]
        resolved = only.get("id")
        if not resolved:
            raise CalendarOperationError("予定IDの取得に失敗しました。")

        return resolved

    def _validate_datetime_range(self, start: str, end: str) -> None:
        start_dt = _parse_iso_datetime(start)
        end_dt = _parse_iso_datetime(end)
        if end_dt <= start_dt:
            raise CalendarOperationError("終了日時は開始日時より後にしてください。")

    @staticmethod
    def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event.get("id"),
            "summary": event.get("summary", "(無題)"),
            "start": event.get("start", {}).get("dateTime")
            or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime")
            or event.get("end", {}).get("date"),
            "html_link": event.get("htmlLink"),
        }


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CalendarOperationError(
            f"日時形式が不正です。ISO8601/RFC3339形式で指定してください: {value}"
        ) from exc


def _rfc3339_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
