"""Tag scans, master tags, who did it, and the mark_done service."""
from datetime import UTC, datetime
import logging

import pytest

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.who import (
    async_resolve_device,
    async_resolve_user,
)

from .conftest import setup_entries, v2_entry


async def scan(hass, tag_id=None, device_id=None):
    data = {}
    if tag_id is not None:
        data["tag_id"] = tag_id
    if device_id is not None:
        data["device_id"] = device_id
    hass.bus.async_fire("tag_scanned", data)
    await hass.async_block_till_done()


def no_errors(caplog):
    return not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def phone(hass, *, person=True):
    """A mobile app phone, its Home Assistant user, and (optionally) a person."""
    user = await hass.auth.async_create_user("ryan-login")
    app = MockConfigEntry(domain="mobile_app", data={"user_id": user.id})
    app.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=app.entry_id,
        identifiers={("mobile_app", "phone-1")},
        name="Ryans iPhone",
    )
    if person:
        hass.states.async_set(
            "person.ryan", "home", {"user_id": user.id, "friendly_name": "Ryan"}
        )
    return user, device


async def test_scan_marks_matching_reminder(hass, freezer):
    freezer.move_to("2026-11-15 14:00:00+00:00")
    a = v2_entry("Litter Box 1", ["tag-1"])
    b = v2_entry("Litter Box 2", ["tag-2"])
    await setup_entries(hass, a, b)
    await scan(hass, "tag-1")
    reminders = get_manager(hass).reminders
    assert reminders[a.entry_id].last_done == datetime(2026, 11, 15, 14, 0, tzinfo=UTC)
    assert reminders[b.entry_id].last_done is None
    assert hass.states.get("sensor.litter_box_1_progress").state == "0"
    assert hass.states.get("sensor.litter_box_1_last_scan").state != "Never scanned"


async def test_master_tag_marks_all_that_list_it(hass):
    boxes = [v2_entry(f"Litter Box {n}", [f"tag-{n}", "master"]) for n in range(1, 5)]
    other = v2_entry("Furnace Filter", ["tag-f"], 30)
    await setup_entries(hass, *boxes, other)
    await scan(hass, "master")
    reminders = get_manager(hass).reminders
    assert all(reminders[e.entry_id].last_done is not None for e in boxes)
    assert reminders[other.entry_id].last_done is None


async def test_unknown_tag_is_ignored(hass, caplog):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await scan(hass, "some-other-tag")
    assert get_manager(hass).reminders[e.entry_id].last_done is None
    assert no_errors(caplog)


async def test_event_without_tag_id_is_ignored(hass, caplog):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await scan(hass)
    assert get_manager(hass).reminders[e.entry_id].last_done is None
    assert no_errors(caplog)


async def test_listener_removed_when_last_entry_unloads(hass, caplog):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    manager = get_manager(hass)
    assert not manager._unsubs
    await scan(hass, "tag-1")
    assert no_errors(caplog)

    # Setting the entry up again listens again, and nothing was lost or marked.
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert manager.reminders[e.entry_id].last_done is None
    await scan(hass, "tag-1")
    assert manager.reminders[e.entry_id].last_done is not None


async def test_scan_records_the_person_behind_the_phone(hass):
    _user, device = await phone(hass)
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    await scan(hass, "tag-1", device.id)
    assert get_manager(hass).reminders[e.entry_id].last_done_by == "Ryan"
    assert hass.states.get("sensor.litter_box_1_last_done_by").state == "Ryan"


async def test_who_resolves_person_from_mobile_app_device(hass):
    user, device = await phone(hass)
    assert await async_resolve_device(hass, device.id) == "Ryan"
    assert await async_resolve_user(hass, user.id) == "Ryan"


async def test_who_falls_back_to_user_name_then_device_name_then_none(hass):
    user, device = await phone(hass, person=False)
    assert await async_resolve_device(hass, device.id) == "ryan-login"

    plain = MockConfigEntry(domain="other")
    plain.add_to_hass(hass)
    reader = dr.async_get(hass).async_get_or_create(
        config_entry_id=plain.entry_id,
        identifiers={("other", "reader")},
        name="Hallway reader",
    )
    assert await async_resolve_device(hass, reader.id) == "Hallway reader"
    assert await async_resolve_device(hass, "no-such-device") is None
    assert await async_resolve_device(hass, None) is None
    assert await async_resolve_user(hass, "no-such-user") is None
    assert await async_resolve_user(hass, None) is None


async def test_mark_done_service(hass):
    a = v2_entry("Litter Box 1", ["tag-1"])
    b = v2_entry("Litter Box 2", ["tag-2"])
    await setup_entries(hass, a, b)
    when = datetime(2026, 11, 10, 8, 30, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN,
        "mark_done",
        {"entity_id": "sensor.litter_box_1_progress", "when": when.isoformat()},
        blocking=True,
    )
    reminders = get_manager(hass).reminders
    assert reminders[a.entry_id].last_done == when
    assert reminders[b.entry_id].last_done is None

    before = dt_util.utcnow()
    await hass.services.async_call(
        DOMAIN,
        "mark_done",
        {"entity_id": ["sensor.litter_box_2_progress", "button.litter_box_2_mark_done"]},
        blocking=True,
    )
    assert reminders[b.entry_id].last_done >= before


async def test_mark_done_service_rejects_other_entities(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    hass.states.async_set("light.kitchen", "on")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "mark_done", {"entity_id": "light.kitchen"}, blocking=True
        )
    assert get_manager(hass).reminders[e.entry_id].last_done is None
