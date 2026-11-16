"""Pure reminder logic: no Home Assistant imports, so it is tested on its own."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import math
import re

_UNIT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400}
_SINGULAR = {"minutes": "minute", "hours": "hour", "days": "day"}
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")


def safe_name(name: str) -> str:
    """Return the slug the version 1 entities and helpers were built from."""
    return name.lower().replace(" ", "_")


def interval_to_timedelta(interval: int, unit: str) -> timedelta:
    """Turn an interval and unit into a timedelta."""
    if unit not in _UNIT_SECONDS:
        raise ValueError(f"unknown interval unit: {unit}")
    return timedelta(seconds=interval * _UNIT_SECONDS[unit])


def parse_time(text: str) -> time:
    """Parse "9", "9:00" or "14:00" into a time. Anything else is a ValueError."""
    match = _TIME_RE.match(text.strip())
    if not match:
        raise ValueError(f"not a time: {text!r}")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"not a time: {text!r}")
    return time(hour, minute)


def _count(number: int, unit: str) -> str:
    return f"{number} {_SINGULAR[unit] if number == 1 else unit}"


def format_elapsed(elapsed: timedelta, unit: str) -> str:
    """Whole units elapsed, in the reminder's own unit: "72 days", "1 day"."""
    seconds = max(elapsed.total_seconds(), 0)
    return _count(int(seconds // _UNIT_SECONDS[unit]), unit)


@dataclass
class Reminder:
    """One chore: what it is called, which tags mark it done, how often it is due."""

    entry_id: str
    name: str
    tag_ids: list[str] = field(default_factory=list)
    interval: int = 7
    unit: str = "days"
    last_done: datetime | None = None  # timezone-aware UTC
    last_done_by: str | None = None
    remind_after: int | None = None  # same unit as interval; heads-up before it is due
    slug: str = ""  # fixed at creation; see CONF_SLUG

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = safe_name(self.name)

    @property
    def period(self) -> timedelta:
        return interval_to_timedelta(self.interval, self.unit)

    @property
    def remind_at(self) -> datetime | None:
        """When the heads-up starts. None without a last done time or a remind_after."""
        if self.last_done is None or not self.remind_after:
            return None
        return self.last_done + interval_to_timedelta(self.remind_after, self.unit)

    def is_due_soon(self, now: datetime) -> bool:
        """Past the heads-up point but not yet overdue."""
        remind_at = self.remind_at
        return remind_at is not None and now >= remind_at and not self.is_overdue(now)

    def due_soon_line(self, now: datetime) -> str:
        """One heads-up line: "Litter Box 1: due in 2 days"."""
        left = (self.next_due or now) - now
        whole = math.ceil(max(left.total_seconds(), 0) / _UNIT_SECONDS[self.unit])
        return f"{self.name}: due in {_count(max(whole, 1), self.unit)}"

    @property
    def next_due(self) -> datetime | None:
        if self.last_done is None:
            return None
        return self.last_done + self.period

    def elapsed(self, now: datetime) -> timedelta | None:
        if self.last_done is None:
            return None
        return max(now - self.last_done, timedelta(0))

    def ratio(self, now: datetime) -> float:
        """Elapsed time as a fraction of the interval. 0 when never done."""
        elapsed = self.elapsed(now)
        if elapsed is None:
            return 0.0
        return elapsed / self.period

    def is_overdue(self, now: datetime) -> bool:
        """Never-done reminders are not overdue."""
        due = self.next_due
        return due is not None and now >= due

    def progress(self, now: datetime) -> int:
        return min(math.floor(self.ratio(now) * 100), 100)

    def days_since(self, now: datetime) -> float | None:
        elapsed = self.elapsed(now)
        if elapsed is None:
            return None
        return round(elapsed.total_seconds() / 86400, 1)

    def status(self, now: datetime) -> str:
        """overdue at the interval; warning from remind_after, or from halfway without one."""
        if self.is_overdue(now):
            return "overdue"
        if self.remind_after:
            return "warning" if self.is_due_soon(now) else "good"
        if self.ratio(now) >= 0.5:
            return "warning"
        return "good"

    def overview_line(self, now: datetime) -> str:
        """One line of the overdue overview: "Litter Box 1: 72 days (every 5 days)"."""
        elapsed = self.elapsed(now) or timedelta(0)
        return (
            f"{self.name}: {format_elapsed(elapsed, self.unit)} "
            f"(every {_count(self.interval, self.unit)})"
        )


_STATUS_RANK = {"good": 0, "warning": 1, "overdue": 2}


def worst_status(reminders: list[Reminder], now: datetime) -> str:
    """The most urgent status among some reminders. "good" when there are none."""
    return max(
        (r.status(now) for r in reminders), key=_STATUS_RANK.__getitem__, default="good"
    )


@dataclass
class Group:
    """Several reminders that one tag, QR code or button marks done together."""

    entry_id: str
    name: str
    member_ids: list[str] = field(default_factory=list)  # reminder entry ids
    tag_ids: list[str] = field(default_factory=list)

    def members(self, reminders: dict[str, Reminder]) -> list[Reminder]:
        """Members that still exist, in the order they were chosen."""
        return [reminders[i] for i in self.member_ids if i in reminders]
