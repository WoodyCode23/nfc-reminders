"""Entity states."""
from datetime import UTC, datetime, timedelta

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager

from .conftest import setup_entries, v2_entry

NOW = datetime(2026, 11, 15, 19, 0, tzinfo=UTC)  # 14:00 in New York


def state(hass, entity_id):
    return hass.states.get(entity_id).state


async def test_never_done_states(hass, freezer):
    freezer.move_to(NOW)
    e = v2_entry("Litter Box 1", ["tag-1", "master"])
    await setup_entries(hass, e)
    assert state(hass, "sensor.litter_box_1_last_scan") == "Never scanned"
    assert state(hass, "sensor.litter_box_1_days_since_scan") == "unknown"
    assert state(hass, "sensor.litter_box_1_progress") == "0"
    assert state(hass, "sensor.litter_box_1_next_due") == "unknown"
    assert state(hass, "sensor.litter_box_1_status") == "good"
    assert state(hass, "sensor.litter_box_1_last_done_by") == "Unknown"
    assert state(hass, "binary_sensor.litter_box_1_overdue") == "off"
    attrs = hass.states.get("sensor.litter_box_1_progress").attributes
    assert attrs["status"] == "good" and attrs["interval"] == 5
    assert attrs["interval_unit"] == "days"
    assert attrs["nfc_tag_id"] == "tag-1" and attrs["tag_ids"] == ["tag-1", "master"]


async def test_states_72_days_after(hass, freezer):
    freezer.move_to(NOW)
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    done = datetime(2026, 9, 4, 20, 40, 41, tzinfo=UTC)
    await get_manager(hass).async_mark_done([e.entry_id], by="Ryan", when=done)
    await hass.async_block_till_done()

    assert state(hass, "sensor.litter_box_1_last_scan") == "September 04, 2026 at 04:40 PM"
    assert state(hass, "sensor.litter_box_1_days_since_scan") == "71.9"
    assert state(hass, "sensor.litter_box_1_progress") == "100"
    assert hass.states.get("sensor.litter_box_1_progress").attributes["status"] == "overdue"
    assert state(hass, "sensor.litter_box_1_next_due") == "2026-09-09T20:40:41+00:00"
    assert state(hass, "sensor.litter_box_1_last_done_by") == "Ryan"
    assert state(hass, "binary_sensor.litter_box_1_overdue") == "on"
    assert state(hass, "sensor.litter_box_1_status") == "overdue"


async def test_status_is_warning_at_85_percent(hass, freezer):
    freezer.move_to(NOW)
    e = v2_entry("Litter Box 1", ["tag-1"], interval=100, unit="hours")
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done(
        [e.entry_id], by=None, when=NOW - timedelta(hours=85)
    )
    await hass.async_block_till_done()
    progress = hass.states.get("sensor.litter_box_1_progress")
    assert progress.state == "85" and progress.attributes["status"] == "warning"
    assert state(hass, "sensor.litter_box_1_status") == "warning"
    assert state(hass, "binary_sensor.litter_box_1_overdue") == "off"


async def test_overdue_turns_on_at_the_due_time(hass, freezer):
    freezer.move_to(NOW)
    e = v2_entry("Furnace Check", ["tag-1"], interval=10, unit="minutes")
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by=None)
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor.furnace_check_overdue") == "off"

    freezer.move_to(NOW + timedelta(minutes=9))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor.furnace_check_overdue") == "off"
    assert state(hass, "sensor.furnace_check_progress") == "90"

    freezer.move_to(NOW + timedelta(minutes=10))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor.furnace_check_overdue") == "on"
    assert hass.states.get("sensor.furnace_check_progress").attributes["status"] == "overdue"


async def test_button_marks_done(hass, freezer, hass_admin_user):
    freezer.move_to(NOW)
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    hass.states.async_set(
        "person.ryan", "home", {"user_id": hass_admin_user.id, "friendly_name": "Ryan"}
    )
    from homeassistant.core import Context

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.litter_box_1_mark_done"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.last_done == NOW and rem.last_done_by == "Ryan"


async def test_unique_ids_and_one_device_per_reminder(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    registry = er.async_get(hass)
    unique = {
        entry.entity_id: entry.unique_id
        for entry in er.async_entries_for_config_entry(registry, e.entry_id)
    }
    assert unique == {
        "sensor.litter_box_1_last_scan": "litter_box_1_last_scan_display",
        "sensor.litter_box_1_days_since_scan": "litter_box_1_days_since_scan",
        "sensor.litter_box_1_progress": "litter_box_1_progress",
        "sensor.litter_box_1_status": f"{e.entry_id}_status",
        "sensor.litter_box_1_next_due": f"{e.entry_id}_next_due",
        "sensor.litter_box_1_last_done_by": f"{e.entry_id}_last_done_by",
        "binary_sensor.litter_box_1_overdue": f"{e.entry_id}_overdue",
        "button.litter_box_1_mark_done": f"{e.entry_id}_mark_done",
        "image.litter_box_1_qr_code": f"{e.entry_id}_qr",
    }
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, e.entry_id)})
    assert device is not None and device.name == "Litter Box 1"


async def test_status_is_a_state_automations_can_trigger_on(hass, freezer):
    """good, warning, overdue as the clock moves, then back to good on a scan."""
    from homeassistant.core import callback
    from homeassistant.helpers.event import async_track_state_change_event

    freezer.move_to(NOW)
    e = v2_entry("Furnace Check", ["tag-1"], interval=10, unit="minutes")
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by=None)
    await hass.async_block_till_done()
    status = hass.states.get("sensor.furnace_check_status")
    assert status.state == "good"
    assert status.attributes["options"] == ["good", "warning", "overdue"]

    seen = []

    @callback
    def changed(event):
        seen.append(event.data["new_state"].state)

    async_track_state_change_event(hass, ["sensor.furnace_check_status"], changed)
    for minutes in (4, 5, 9, 10, 11):
        freezer.move_to(NOW + timedelta(minutes=minutes))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert seen == ["warning", "overdue", "good"]
