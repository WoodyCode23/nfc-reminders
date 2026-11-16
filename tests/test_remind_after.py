"""Remind after: a heads-up before a chore is due (every 5 days, remind after 3)."""
from datetime import UTC, datetime, timedelta

import pytest

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.notifications import build_overview
from custom_components.nfc_reminders.reminder import Reminder

from .conftest import setup_entries, v2_entry

NOW = datetime(2026, 11, 16, 19, 0, tzinfo=UTC)


def litter(days_ago, remind_after=3, name="Stairs Left"):
    last = None if days_ago is None else NOW - timedelta(days=days_ago)
    return Reminder(name, name, [], 5, "days", last, remind_after=remind_after)


@pytest.mark.parametrize(
    ("days_ago", "status", "soon"),
    [
        (None, "good", False),
        (2.9, "good", False),  # without remind_after this would already be warning
        (3, "warning", True),
        (4.9, "warning", True),
        (5, "overdue", False),  # overdue, not "due soon"
    ],
)
def test_status_follows_remind_after(days_ago, status, soon):
    r = litter(days_ago)
    assert r.status(NOW) == status and r.is_due_soon(NOW) is soon


def test_without_remind_after_nothing_changes():
    r = litter(2.5, remind_after=None)
    assert r.status(NOW) == "warning" and not r.is_due_soon(NOW) and r.remind_at is None


def test_due_soon_line_rounds_up():
    assert litter(3).due_soon_line(NOW) == "Stairs Left: due in 2 days"
    assert litter(3.5).due_soon_line(NOW) == "Stairs Left: due in 2 days"
    assert litter(4.5).due_soon_line(NOW) == "Stairs Left: due in 1 day"


def test_overview_due_soon_only():
    title, body = build_overview([litter(3.5), litter(1, name="Upstairs")], NOW)
    assert title == "1 thing due soon" and body == "Stairs Left: due in 2 days"


def test_overview_overdue_and_due_soon():
    title, body = build_overview(
        [
            litter(4.5, name="Upstairs"),
            litter(3.2, name="Basement"),
            litter(72, name="Stairs Left"),
            Reminder("f", "Furnace Filter", [], 30, "days", NOW - timedelta(days=10)),
        ],
        NOW,
    )
    assert title == "1 overdue, 2 due soon"
    assert body.splitlines() == [
        "Stairs Left: 72 days (every 5 days)",
        "Upstairs: due in 1 day",  # soonest first
        "Basement: due in 2 days",
    ]


def test_overview_still_none_when_nothing_is_due():
    assert build_overview([litter(1), litter(None)], NOW) is None


async def test_heads_up_overview_is_sent_at_the_set_time(hass, freezer):
    freezer.move_to("2026-11-16 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    notif = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Notifications",
        unique_id="notifications",
        data={"entry_type": "notifications"},
        options={"times": ["09:00"], "targets": ["service:family_phones"], "notify_on_scan": False},
    )
    box = v2_entry("Litter Box 1", ["tag-1"])
    box.add_to_hass(hass)
    hass.config_entries.async_update_entry(box, data={**box.data, "remind_after": 3})
    await setup_entries(hass, notif)
    await get_manager(hass).async_mark_done(
        [box.entry_id], by=None, when=dt_util.utcnow() - timedelta(days=3, hours=1)
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.litter_box_1_status").state == "warning"
    assert hass.states.get("binary_sensor.litter_box_1_overdue").state == "off"
    assert hass.states.get("sensor.litter_box_1_progress").attributes["remind_after"] == 3

    freezer.move_to("2026-11-16 09:00:00-05:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["title"] == "1 thing due soon"
    assert calls[0].data["message"] == "Litter Box 1: due in 2 days"


async def add_reminder(hass, **values):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reminder"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"reminder_name": "Stairs Left", "interval": 5, "interval_unit": "days", **values},
    )


async def test_new_reminder_with_remind_after(hass):
    result = await add_reminder(hass, remind_after=3)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "new_qr"}
    )
    await hass.async_block_till_done()
    assert result["data"]["remind_after"] == 3


async def test_new_reminder_without_remind_after(hass):
    result = await add_reminder(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "new_qr"}
    )
    await hass.async_block_till_done()
    assert result["data"]["remind_after"] is None


@pytest.mark.parametrize("remind_after", [5, 9])
async def test_remind_after_must_come_before_due(hass, remind_after):
    result = await add_reminder(hass, remind_after=remind_after)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"remind_after": "remind_after_too_late"}


async def test_settings_set_change_and_clear_remind_after(hass, freezer):
    freezer.move_to(NOW)
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done(
        [e.entry_id], by=None, when=NOW - timedelta(days=3, hours=1)
    )

    async def configure(**extra):
        result = await hass.config_entries.options.async_init(e.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"interval": 5, "interval_unit": "days", "tag_ids": ["tag-1"], **extra},
        )
        await hass.async_block_till_done()
        return result

    assert hass.states.get("sensor.litter_box_1_status").state == "warning"  # 62% > half
    await configure(remind_after=4)
    assert e.data["remind_after"] == 4
    assert hass.states.get("sensor.litter_box_1_status").state == "good"
    await configure(remind_after=3)
    assert hass.states.get("sensor.litter_box_1_status").state == "warning"

    result = await configure(remind_after=5)
    assert result["errors"] == {"remind_after": "remind_after_too_late"}
    assert e.data["remind_after"] == 3

    await configure()  # field left empty: no heads-up
    assert e.data["remind_after"] is None
    assert get_manager(hass).reminders[e.entry_id].remind_after is None
