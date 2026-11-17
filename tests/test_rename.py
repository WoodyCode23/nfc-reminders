"""Renaming a reminder or group keeps its entities, history and stored dates."""
from datetime import UTC, datetime

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager

from .conftest import group_entry, setup_entries, v1_entry, v2_entry

WHEN = datetime(2026, 9, 4, 20, 40, 41, tzinfo=UTC)


async def rename(hass, entry, name, key="reminder_name"):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    values = {"interval": 5, "interval_unit": "days", "tag_ids": list(entry.data["tag_ids"])}
    if key == "group_name":
        values = {"members": list(entry.data["members"]), "tag_ids": list(entry.data["tag_ids"])}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**values, key: name}
    )
    await hass.async_block_till_done()
    return result


def unique_ids(hass, entry):
    registry = er.async_get(hass)
    return {
        e.entity_id: e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_rename_keeps_entities_and_dates(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])  # made before slugs existed, like Ryan's
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done([e.entry_id], by="Ryan", when=WHEN)
    before = unique_ids(hass, e)

    result = await rename(hass, e, "Stairs Left")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert e.title == "Stairs Left" and e.data["reminder_name"] == "Stairs Left"
    assert e.data["slug"] == "litter_box_1"

    assert unique_ids(hass, e) == before  # same entity ids, same unique ids: history continues
    progress = hass.states.get("sensor.litter_box_1_progress")
    assert progress.name == "Stairs Left Progress"
    rem = get_manager(hass).reminders[e.entry_id]
    assert rem.name == "Stairs Left" and rem.last_done == WHEN and rem.last_done_by == "Ryan"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, e.entry_id)})
    assert device.name == "Stairs Left"

    # Renaming again keeps the first slug.
    await rename(hass, e, "Stairs (left)")
    assert e.data["slug"] == "litter_box_1" and unique_ids(hass, e) == before


async def test_messages_use_the_new_name(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    calls = async_mock_service(hass, "notify", "family_phones")
    notif = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Notifications",
        unique_id="notifications",
        data={"entry_type": "notifications"},
        options={"times": ["09:00"], "targets": ["service:family_phones"], "notify_on_scan": True},
    )
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, notif, e)
    await rename(hass, e, "Stairs Left")
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert calls[-1].data["title"] == "✅ Stairs Left done"
    assert calls[-1].data["message"].startswith("Stairs Left\nMarked done by someone at ")


async def test_migrated_entry_gets_its_slug(hass):
    e = v1_entry("Litter Box 1", "tag-1", 5)
    await setup_entries(hass, e)
    assert e.data["slug"] == "litter_box_1"


async def test_rename_cannot_take_another_name_or_the_old_slug(hass):
    a = v2_entry("Litter Box 1", ["tag-1"])
    b = v2_entry("Litter Box 2", ["tag-2"])
    await setup_entries(hass, a, b)

    result = await rename(hass, b, "litter box 1")
    assert result["errors"] == {"reminder_name": "name_exists"}
    result = await rename(hass, b, "  ")
    assert result["errors"] == {"reminder_name": "name_required"}
    assert b.data["reminder_name"] == "Litter Box 2"

    # Renamed, "Litter Box 1" still owns litter_box_1_* unique ids, so nobody may take it.
    await rename(hass, a, "Stairs Left")
    result = await rename(hass, b, "Litter Box 1")
    assert result["errors"] == {"reminder_name": "name_exists"}

    # Renaming to its own current name, or a new spelling of it, is fine.
    result = await rename(hass, a, "stairs left")
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_new_reminder_cannot_take_a_renamed_reminders_old_name(hass):
    a = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, a)
    await rename(hass, a, "Stairs Left")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reminder"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"reminder_name": "Litter Box 1", "interval": 5, "interval_unit": "days"},
    )
    assert result["errors"] == {"base": "name_exists"}


async def test_group_rename(hass):
    two = [v2_entry(f"Litter Box {n}", [f"tag-{n}"]) for n in (1, 2)]
    g = group_entry("All Litter Boxes", two, ["g"])
    await setup_entries(hass, *two, g)
    before = unique_ids(hass, g)
    result = await rename(hass, g, "Every Litter Box", key="group_name")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert g.title == "Every Litter Box" and unique_ids(hass, g) == before
    assert hass.states.get("sensor.all_litter_boxes_status").name == "Every Litter Box Status"
