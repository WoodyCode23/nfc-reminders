"""Stored state survives restarts and is forgotten with its reminder."""
from datetime import UTC, datetime

from custom_components.nfc_reminders.const import STORAGE_KEY
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.store import ReminderStore

from .conftest import setup_entries, v2_entry

WHEN = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


async def test_store_round_trip_survives_restart(hass, hass_storage):
    store = ReminderStore(hass)
    await store.async_load()
    assert store.get("e1") is None
    await store.async_set("e1", last_done=WHEN, last_done_by="Ryan")

    again = ReminderStore(hass)
    await again.async_load()
    assert again.get("e1") == {
        "last_done": WHEN.isoformat(),
        "last_done_by": "Ryan",
        "imported": True,
    }


async def test_damaged_storage_reads_as_empty(hass, hass_storage):
    hass_storage[STORAGE_KEY] = {"version": 1, "key": STORAGE_KEY, "data": {"reminders": []}}
    store = ReminderStore(hass)
    await store.async_load()
    assert store.get("e1") is None


async def test_scan_survives_reload(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by="Ryan", when=WHEN)
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.last_done == WHEN and rem.last_done_by == "Ryan"


async def test_remove_entry_forgets_state(hass, hass_storage):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by="Ryan", when=WHEN)
    await hass.config_entries.async_remove(e.entry_id)
    await hass.async_block_till_done()

    assert e.entry_id not in get_manager(hass).reminders
    store = ReminderStore(hass)
    await store.async_load()
    assert store.get(e.entry_id) is None
