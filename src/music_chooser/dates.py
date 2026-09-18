from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Bucket:
    key: str
    label: str
    start: date | None
    end: date | None

    def contains(self, release_date: date | None) -> bool:
        if release_date is None:
            return self.key == "anytime"
        if self.start is not None and release_date < self.start:
            return False
        if self.end is not None and release_date > self.end:
            return False
        return True


def local_today(timezone: ZoneInfo, now: datetime | None = None) -> date:
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    return current.astimezone(timezone).date()


def week_key(today: date) -> str:
    """Return the Monday date that identifies the current local week."""
    return (today - timedelta(days=today.weekday())).isoformat()


def buckets_for(today: date) -> list[Bucket]:
    monday = today - timedelta(days=today.weekday())
    previous_week_end = monday - timedelta(days=1)
    previous_week_start = previous_week_end - timedelta(days=6)

    first_of_month = today.replace(day=1)
    previous_month_end = first_of_month - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)

    previous_year = today.year - 1
    previous_year_start = date(previous_year, 1, 1)
    previous_year_end = date(previous_year, 12, 31)

    five_year_start = date(today.year - 5, 1, 1)
    five_year_end = date(today.year - 1, 12, 31)

    return [
        Bucket("last_week", "Previous calendar week", previous_week_start, previous_week_end),
        Bucket("last_month", "Previous calendar month", previous_month_start, previous_month_end),
        Bucket("last_year", "Previous calendar year", previous_year_start, previous_year_end),
        Bucket("last_5_years", "Previous five complete years", five_year_start, five_year_end),
        Bucket("anytime", "Anytime", None, None),
    ]
