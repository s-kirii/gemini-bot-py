from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar"]

ISO_EXAMPLE = "2026-02-12T19:00:00+09:00"


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

    @property
    def calendar_timezone(self) -> str:
        return self._calendar_timezone

    def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        max_results = max(1, min(max_results, 20))
        normalized_min = (
            normalize_datetime_text(time_min, self._calendar_timezone) if time_min else None
        )
        normalized_max = (
            normalize_datetime_text(time_max, self._calendar_timezone) if time_max else None
        )

        try:
            response = (
                self._service.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=normalized_min,
                    timeMax=normalized_max,
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
        tz_name = timezone_name or self._calendar_timezone
        normalized_start = normalize_datetime_text(start, tz_name)
        normalized_end = normalize_datetime_text(end, tz_name)
        self._validate_datetime_range(normalized_start, normalized_end)

        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": normalized_start, "timeZone": tz_name},
            "end": {"dateTime": normalized_end, "timeZone": tz_name},
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
        normalized_min = (
            normalize_datetime_text(time_min, self._calendar_timezone) if time_min else None
        )
        normalized_max = (
            normalize_datetime_text(time_max, self._calendar_timezone) if time_max else None
        )

        resolved_event_id = self._resolve_event_id(
            event_id=event_id,
            query=query,
            time_min=normalized_min,
            time_max=normalized_max,
        )

        tz_name = timezone_name or self._calendar_timezone
        normalized_start = normalize_datetime_text(start, tz_name) if start else None
        normalized_end = normalize_datetime_text(end, tz_name) if end else None

        if normalized_start and normalized_end:
            self._validate_datetime_range(normalized_start, normalized_end)

        patch: dict[str, Any] = {}

        if summary is not None:
            patch["summary"] = summary
        if description is not None:
            patch["description"] = description
        if location is not None:
            patch["location"] = location
        if normalized_start is not None:
            patch["start"] = {"dateTime": normalized_start, "timeZone": tz_name}
        if normalized_end is not None:
            patch["end"] = {"dateTime": normalized_end, "timeZone": tz_name}

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
        normalized_min = (
            normalize_datetime_text(time_min, self._calendar_timezone) if time_min else None
        )
        normalized_max = (
            normalize_datetime_text(time_max, self._calendar_timezone) if time_max else None
        )

        resolved_event_id = self._resolve_event_id(
            event_id=event_id,
            query=query,
            time_min=normalized_min,
            time_max=normalized_max,
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


def normalize_datetime_text(
    value: str,
    timezone_name: str,
    now: datetime | None = None,
) -> str:
    text = value.strip()
    if not text:
        raise CalendarOperationError("日時が空です。")

    tz = _load_timezone(timezone_name)

    iso = _try_parse_iso(text, tz)
    if iso is not None:
        return iso

    absolute = _parse_absolute_datetime(text, tz)
    if absolute is not None:
        return absolute.isoformat()

    base_now = now.astimezone(tz) if now else datetime.now(tz)

    relative = _parse_relative_datetime(text, base_now)
    if relative is not None:
        return relative.isoformat()

    time_only = _parse_time_only(text, base_now)
    if time_only is not None:
        return time_only.isoformat()

    raise CalendarOperationError(
        "日時形式が不正です。ISO8601/RFC3339形式、または自然文（例: 明日19時）で指定してください。"
        f" 例: {ISO_EXAMPLE}"
    )


def _load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception as exc:  # pragma: no cover
        raise CalendarOperationError(f"タイムゾーンが不正です: {timezone_name}") from exc


def _try_parse_iso(text: str, tz: ZoneInfo) -> str | None:
    try:
        dt = _parse_iso_datetime(text)
    except CalendarOperationError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.isoformat()


def _parse_absolute_datetime(text: str, tz: ZoneInfo) -> datetime | None:
    ymd = re.match(
        r"^(?P<y>\d{4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})(?:[ T](?P<h>\d{1,2})(?::(?P<min>\d{1,2}))?)?$",
        text,
    )
    if ymd:
        year = int(ymd.group("y"))
        month = int(ymd.group("m"))
        day = int(ymd.group("d"))
        hour = int(ymd.group("h") or 0)
        minute = int(ymd.group("min") or 0)
        return datetime(year, month, day, hour, minute, tzinfo=tz)

    md = re.match(
        r"^(?P<m>\d{1,2})[/-](?P<d>\d{1,2})(?:[ T](?P<h>\d{1,2})(?::(?P<min>\d{1,2}))?)?$",
        text,
    )
    if md:
        now = datetime.now(tz)
        year = now.year
        month = int(md.group("m"))
        day = int(md.group("d"))
        hour = int(md.group("h") or 0)
        minute = int(md.group("min") or 0)
        dt = datetime(year, month, day, hour, minute, tzinfo=tz)
        if dt < now - timedelta(days=180):
            dt = dt.replace(year=year + 1)
        return dt

    return None


def _parse_relative_datetime(text: str, now: datetime) -> datetime | None:
    rel = re.match(
        r"^(?P<day>今日|明日|明後日)(?:\s*(?:の)?\s*(?P<h>\d{1,2})(?:(?::(?P<min1>\d{1,2}))|(?:時(?P<min2>\d{1,2})?分?))?)?$",
        text,
    )
    if not rel:
        return None

    offset = {"今日": 0, "明日": 1, "明後日": 2}[rel.group("day")]
    target = (now + timedelta(days=offset)).date()

    hour = int(rel.group("h") or 0)
    minute = int(rel.group("min1") or rel.group("min2") or 0)
    return datetime(
        target.year,
        target.month,
        target.day,
        hour,
        minute,
        tzinfo=now.tzinfo,
    )


def _parse_time_only(text: str, now: datetime) -> datetime | None:
    time_only = re.match(
        r"^(?P<h>\d{1,2})(?:(?::(?P<min1>\d{1,2}))|(?:時(?P<min2>\d{1,2})?分?))?$",
        text,
    )
    if not time_only:
        return None

    hour = int(time_only.group("h"))
    minute = int(time_only.group("min1") or time_only.group("min2") or 0)

    return datetime(
        now.year,
        now.month,
        now.day,
        hour,
        minute,
        tzinfo=now.tzinfo,
    )


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
