"""The overdue overview, the scan message and the Notifications entry."""
from datetime import UTC, datetime, timedelta
import logging

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.notifications import (
    build_overview,
    build_scan_message,
)
from custom_components.nfc_reminders.reminder import Reminder

from .conftest import setup_entries, v2_entry

NOW = datetime(2026, 11, 15, 19, 0, tzinfo=UTC)


def rem(name, days_ago, interval):
    last = None if days_ago is None else NOW - timedelta(days=days_ago)
    return Reminder(name, name, [], interval, "days", last)


def notif_entry(targets=(), times=("09:00", "14:00"), notify_on_scan=False):
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Notifications",
        unique_id="notifications",
        data={"entry_type": "notifications"},
        options={
            "times": list(times),
            "targets": list(targets),
            "notify_on_scan": notify_on_scan,
        },
    )


async def at_local(hass, freezer, text):
    """Move the clock to a New York wall time and let timers fire."""
    freezer.move_to(f"{text}-05:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def test_overview_none_when_nothing_overdue():
    assert build_overview([rem("A", 1, 5)], NOW) is None
    assert build_overview([], NOW) is None


def test_overview_skips_never_done():
    assert build_overview([rem("A", None, 5)], NOW) is None
    title, body = build_overview([rem("A", None, 5), rem("B", 9, 5)], NOW)
    assert title == "🔴 1 thing overdue" and body == "🔴 B: 9 days (every 5 days)"


def test_overview_title_and_order():
    # 253 days on a 20 day interval (12.65x) is less overdue than 72 on 5 (14.4x).
    title, body = build_overview(
        [rem("Master Bathroom", 253, 20), rem("OK", 1, 5), rem("Litter Box 1", 72, 5)], NOW
    )
    assert title == "🔴 2 things overdue"
    assert body.splitlines() == [
        "🔴 Litter Box 1: 72 days (every 5 days)",
        "🔴 Master Bathroom: 253 days (every 20 days)",
    ]


def test_scan_message():
    when = datetime(2026, 11, 15, 19, 5, tzinfo=UTC)  # 2:05 PM in New York
    cat = "\U0001F431"
    one = Reminder("a", "Stairs Left", [], 5, "days", emoji=cat)
    two = Reminder("b", "Furnace Filter", [], 30, "days")
    assert build_scan_message([one], "Ryan", when) == (
        "✅ Stairs Left done",
        f"{cat} Stairs Left\nMarked done by Ryan at 2:05 PM",
    )
    assert build_scan_message([one, two], None, when) == (
        "✅ 2 things done",
        f"{cat} Stairs Left, Furnace Filter\nMarked done by someone at 2:05 PM",
    )
    # A group's tag or button announces itself by the group's name.
    assert build_scan_message([one, two], "Marisa", when, "All Chores")[0] == "✅ All Chores done"


async def test_notifications_entry_auto_created_once(hass):
    a = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, a)

    def found():
        return [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.data["entry_type"] == "notifications"
        ]

    assert len(found()) == 1
    entry = found()[0]
    assert entry.title == "Notifications" and entry.unique_id == "notifications"
    assert entry.options == {
        "times": ["09:00", "14:00"],
        "targets": [],
        "notify_on_scan": False,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data={}
    )
    assert result["type"] == "abort" and result["reason"] == "already_configured"
    assert len(found()) == 1


async def test_overview_sent_at_configured_times(hass, freezer):
    freezer.move_to("2026-11-15 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    box = v2_entry("Litter Box 1", ["tag-1"])
    bath = v2_entry("Master Bathroom", ["tag-2"], 20)
    never = v2_entry("Ryans Teeth", ["tag-3"], 1)
    await setup_entries(hass, notif_entry(["service:family_phones"]), box, bath, never)
    manager = get_manager(hass)
    await manager.async_mark_done(
        [box.entry_id], by=None, when=datetime(2026, 9, 4, 20, 40, 41, tzinfo=UTC)
    )
    await manager.async_mark_done(
        [bath.entry_id], by=None, when=datetime(2026, 3, 7, 15, 53, 17, tzinfo=UTC)
    )

    await at_local(hass, freezer, "2026-11-15 08:59:00")
    assert len(calls) == 0
    await at_local(hass, freezer, "2026-11-15 09:00:00")
    assert len(calls) == 1
    assert calls[0].data["title"] == "🔴 2 things overdue"
    assert calls[0].data["message"].splitlines() == [
        "🔴 Litter Box 1: 71 days (every 5 days)",
        "🔴 Master Bathroom: 252 days (every 20 days)",
    ]
    await at_local(hass, freezer, "2026-11-15 09:01:00")
    assert len(calls) == 1
    await at_local(hass, freezer, "2026-11-15 14:00:00")
    assert len(calls) == 2


async def test_no_overview_when_nothing_overdue(hass, freezer):
    freezer.move_to("2026-11-15 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif_entry(["service:family_phones"]), box)
    await get_manager(hass).async_mark_done([box.entry_id], by=None)
    await at_local(hass, freezer, "2026-11-15 09:00:00")
    assert len(calls) == 0


async def test_dead_target_does_not_block_others(hass, freezer, caplog):
    freezer.move_to("2026-11-15 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(
        hass, notif_entry(["service:gone", "service:family_phones"]), box
    )
    await get_manager(hass).async_mark_done(
        [box.entry_id], by=None, when=datetime(2026, 9, 4, tzinfo=UTC)
    )
    await at_local(hass, freezer, "2026-11-15 09:00:00")
    assert len(calls) == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "gone" in r.getMessage()]
    assert warnings
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_entity_target_uses_send_message(hass, freezer):
    freezer.move_to("2026-11-15 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "send_message")
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif_entry(["entity:notify.iphone"]), box)
    await get_manager(hass).async_mark_done(
        [box.entry_id], by=None, when=datetime(2026, 9, 4, tzinfo=UTC)
    )
    await at_local(hass, freezer, "2026-11-15 09:00:00")
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "notify.iphone"
    assert calls[0].data["title"] == "🔴 1 thing overdue"


async def test_scan_notification_off_by_default(hass):
    calls = async_mock_service(hass, "notify", "family_phones")
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif_entry(["service:family_phones"]), box)
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert get_manager(hass).reminders[box.entry_id].last_done is not None
    assert len(calls) == 0


async def test_scan_notification_is_one_message_for_a_master_tag(hass):
    calls = async_mock_service(hass, "notify", "family_phones")
    boxes = [v2_entry(f"Litter Box {n}", [f"tag-{n}", "master"]) for n in (1, 2)]
    await setup_entries(
        hass, notif_entry(["service:family_phones"], notify_on_scan=True), *boxes
    )
    hass.bus.async_fire("tag_scanned", {"tag_id": "master"})
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["title"] == "✅ 2 things done"
    assert calls[0].data["message"].startswith("Litter Box 1, Litter Box 2\nMarked done by someone at ")


async def test_failed_scan_message_does_not_lose_the_scan(hass):
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif_entry(["service:gone"], notify_on_scan=True), box)
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert get_manager(hass).reminders[box.entry_id].last_done is not None


async def test_changing_times_reschedules(hass, freezer):
    freezer.move_to("2026-11-15 08:58:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    notif = notif_entry(["service:family_phones"])
    box = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif, box)
    await get_manager(hass).async_mark_done(
        [box.entry_id], by=None, when=datetime(2026, 9, 4, tzinfo=UTC)
    )
    hass.config_entries.async_update_entry(
        notif, options={**notif.options, "times": ["10:30"]}
    )
    await hass.async_block_till_done()

    await at_local(hass, freezer, "2026-11-15 09:00:00")
    assert len(calls) == 0
    await at_local(hass, freezer, "2026-11-15 10:30:00")
    assert len(calls) == 1


async def test_repair_issue_tracks_empty_targets(hass):
    notif = notif_entry([])
    await setup_entries(hass, notif, v2_entry("Litter Box 1", ["tag-1"]))
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, "no_notify_targets") is not None

    hass.config_entries.async_update_entry(
        notif, options={**notif.options, "targets": ["service:family_phones"]}
    )
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, "no_notify_targets") is None

    hass.config_entries.async_update_entry(notif, options={**notif.options, "targets": []})
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, "no_notify_targets") is not None
