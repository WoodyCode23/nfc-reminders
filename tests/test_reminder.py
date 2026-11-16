"""Pure date logic."""
from datetime import UTC, datetime, time, timedelta

import pytest

from custom_components.nfc_reminders.reminder import (
    Reminder,
    format_elapsed,
    interval_to_timedelta,
    parse_time,
    safe_name,
)

NOW = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)


def r(days_ago=None, interval=5, unit="days"):
    last = None if days_ago is None else NOW - timedelta(days=days_ago)
    return Reminder("e1", "Litter Box 1", ["t1"], interval, unit, last)


def test_never_done_is_not_overdue():
    x = r()
    assert not x.is_overdue(NOW) and x.progress(NOW) == 0
    assert x.days_since(NOW) is None and x.next_due is None and x.status(NOW) == "good"


def test_overdue_exactly_at_due_time():
    assert r(days_ago=5).is_overdue(NOW) and r(days_ago=5).status(NOW) == "overdue"


def test_not_overdue_just_before():
    x = Reminder("e", "n", [], 5, "days", NOW - timedelta(days=5) + timedelta(seconds=1))
    assert not x.is_overdue(NOW) and x.progress(NOW) == 99 and x.status(NOW) == "warning"


def test_status_bands():
    assert r(days_ago=2).status(NOW) == "good"  # 40%
    assert r(days_ago=2.5).status(NOW) == "warning"  # 50%


def test_progress_caps_at_100():
    assert r(days_ago=72).progress(NOW) == 100


def test_days_since_one_decimal():
    assert r(days_ago=72.26).days_since(NOW) == 72.3


def test_last_done_in_the_future_counts_as_zero():
    x = Reminder("e", "n", [], 5, "days", NOW + timedelta(hours=1))
    assert x.progress(NOW) == 0 and x.days_since(NOW) == 0 and not x.is_overdue(NOW)


def test_units():
    assert interval_to_timedelta(90, "minutes") == timedelta(minutes=90)
    assert interval_to_timedelta(12, "hours") == timedelta(hours=12)
    with pytest.raises(ValueError):
        interval_to_timedelta(1, "weeks")


def test_format_elapsed():
    assert format_elapsed(timedelta(hours=5, minutes=59), "hours") == "5 hours"
    assert format_elapsed(timedelta(minutes=1), "minutes") == "1 minute"


def test_overview_line():
    assert r(days_ago=72.2).overview_line(NOW) == "Litter Box 1: 72 days (every 5 days)"
    assert r(days_ago=1.5, interval=1).overview_line(NOW) == "Litter Box 1: 1 day (every 1 day)"


def test_parse_time():
    assert parse_time("9") == time(9, 0)
    assert parse_time(" 9:00 ") == time(9, 0)
    assert parse_time("14:00") == time(14, 0)
    for bad in ("2pm", "25:00", "", "9:75", "9:5", "-1"):
        with pytest.raises(ValueError):
            parse_time(bad)


def test_safe_name():
    assert safe_name("Litter Box 1") == "litter_box_1"
