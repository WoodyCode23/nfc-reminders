"""Version 1 to 2 migration and the one-time carry-over from the old helpers."""
from datetime import UTC, datetime

import pytest

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager

from .conftest import RYAN_HOME, setup_entries, v1_entry

DATE_HELPER = "input_datetime.litter_box_1_last_scan"
BY_HELPER = "input_text.litter_box_1_last_cleaned_by"


async def test_v1_entry_migrates(hass):
    e = v1_entry("Litter Box 1", "tag-1", 5, options={"interval": 9, "interval_unit": "days"})
    await setup_entries(hass, e)
    assert e.version == 2 and e.data["tag_ids"] == ["tag-1"] and "nfc_tag_id" not in e.data
    assert e.data["entry_type"] == "reminder" and e.options == {}
    assert e.data["interval"] == 5  # the never-applied options value is discarded


async def test_helper_date_is_imported_as_local_time(hass):
    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    hass.states.async_set(BY_HELPER, "Ryan")
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.last_done == datetime(2026, 9, 4, 20, 40, 41, tzinfo=UTC)
    assert rem.last_done_by == "Ryan"


@pytest.mark.parametrize("state", ["unknown", "unavailable", "garbage", "", None])
async def test_bad_or_missing_helper_means_never_done(hass, state):
    if state is not None:
        hass.states.async_set(DATE_HELPER, state)
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.last_done is None
    assert hass.states.get("sensor.litter_box_1_last_scan").state == "Never scanned"


@pytest.mark.parametrize("by", ["Unknown", "unknown", "unavailable", ""])
async def test_cleaned_by_unknown_is_ignored(hass, by):
    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    hass.states.async_set(BY_HELPER, by)
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    assert get_manager(hass).reminders[e.entry_id].last_done_by is None


async def test_import_never_overwrites_a_stored_scan(hass):
    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    done_at = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    await get_manager(hass).async_mark_done([e.entry_id], by="Marisa", when=done_at)

    hass.states.async_set(DATE_HELPER, "2020-01-01 00:00:00")
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()

    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.last_done == done_at and rem.last_done_by == "Marisa"


async def test_never_done_is_recorded_so_a_later_helper_is_not_imported(hass):
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    assert get_manager(hass).reminders[e.entry_id].last_done is None


async def test_helpers_are_never_written(hass):
    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    hass.states.async_set(BY_HELPER, "Ryan")
    before = (hass.states.get(DATE_HELPER), hass.states.get(BY_HELPER))
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by="Marisa")
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert (hass.states.get(DATE_HELPER), hass.states.get(BY_HELPER)) == before


async def test_helper_missing_during_startup_is_retried_once_started(hass):
    hass.set_state(CoreState.starting)
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    assert get_manager(hass).reminders[e.entry_id].last_done is None

    hass.states.async_set(DATE_HELPER, "2026-09-04 16:40:41")
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert get_manager(hass).reminders[e.entry_id].last_done == datetime(
        2026, 9, 4, 20, 40, 41, tzinfo=UTC
    )


async def test_ryans_nine_entries_carry_over(hass):
    entries = []
    for index, (name, interval, helper) in enumerate(RYAN_HOME):
        slug = name.lower().replace(" ", "_")
        if helper is not None:
            hass.states.async_set(f"input_datetime.{slug}_last_scan", helper)
            hass.states.async_set(f"input_text.{slug}_last_cleaned_by", "Unknown")
        entries.append(v1_entry(name, f"tag-{index}", interval))
    await setup_entries(hass, *entries)

    manager = get_manager(hass)
    assert len(manager.reminders) == 9
    registry = er.async_get(hass)
    for entry, (name, interval, helper) in zip(entries, RYAN_HOME, strict=True):
        rem = manager.reminders[entry.entry_id]
        slug = name.lower().replace(" ", "_")
        assert rem.interval == interval and rem.unit == "days"
        if helper is None:
            assert rem.last_done is None
        else:
            local = dt_util.parse_datetime(helper).replace(
                tzinfo=dt_util.get_default_time_zone()
            )
            assert rem.last_done == dt_util.as_utc(local)
        # Entity ids and unique ids are the version 1 ones, so history continues.
        for suffix, unique in (
            ("last_scan", "last_scan_display"),
            ("days_since_scan", "days_since_scan"),
            ("progress", "progress"),
        ):
            entity_id = f"sensor.{slug}_{suffix}"
            assert hass.states.get(entity_id) is not None, entity_id
            assert registry.async_get(entity_id).unique_id == f"{slug}_{unique}"

    # One Notifications entry was created on its own, and only one.
    kinds = [e.data["entry_type"] for e in hass.config_entries.async_entries(DOMAIN)]
    assert kinds.count("notifications") == 1 and kinds.count("reminder") == 9
