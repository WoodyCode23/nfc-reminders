"""Adding a reminder and editing settings."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager

from .conftest import setup_entries, v2_entry

COMPONENT = Path(__file__).parent.parent / "custom_components" / "nfc_reminders"
EM_DASH = chr(0x2014)


async def start(hass, name="Litter Box 1", interval=5, unit="days"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"reminder_name": name, "interval": interval, "interval_unit": unit},
    )


async def choose(hass, result, step):
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "tag"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


def notifications_entry(hass):
    return next(
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data["entry_type"] == "notifications"
    )


async def test_scan_a_tag_now(hass):
    result = await choose(hass, await start(hass), "scan")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "scan"

    # Submitting before any scan keeps the form open and keeps listening.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "no_scan"}

    hass.bus.async_fire("tag_scanned", {"tag_id": "scanned-tag"})
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Litter Box 1"
    assert result["data"] == {
        "entry_type": "reminder",
        "reminder_name": "Litter Box 1",
        "interval": 5,
        "interval_unit": "days",
        "tag_ids": ["scanned-tag"],
    }
    assert hass.states.get("sensor.litter_box_1_progress") is not None


async def test_closing_the_scan_step_stops_listening(hass):
    result = await choose(hass, await start(hass), "scan")
    listeners = hass.bus.async_listeners().get("tag_scanned", 0)
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()
    assert hass.bus.async_listeners().get("tag_scanned", 0) == listeners - 1


async def test_pick_a_known_tag(hass):
    hass.states.async_set(
        "tag.furnace_filter", "unknown", {"tag_id": "known-1", "friendly_name": "Furnace Filter"}
    )
    result = await choose(hass, await start(hass, "Furnace Filter", 30), "existing")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "existing"
    options = result["data_schema"].schema["tag_id"].config["options"]
    assert {"value": "known-1", "label": "Furnace Filter"} in options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tag_id": "known-1"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["tag_ids"] == ["known-1"] and result["data"]["interval"] == 30


async def test_typed_tag_id_is_accepted(hass):
    result = await choose(hass, await start(hass), "existing")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tag_id": " typed-by-hand "}
    )
    await hass.async_block_till_done()
    assert result["data"]["tag_ids"] == ["typed-by-hand"]


async def test_new_qr_tag(hass):
    result = await choose(hass, await start(hass), "new_qr")
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (tag_id,) = result["data"]["tag_ids"]
    assert len(tag_id) == 36 and tag_id.count("-") == 4


@pytest.mark.parametrize("name", ["litter box 1", "Litter Box 1", "LITTER BOX 1 "])
async def test_names_that_collide_are_rejected(hass, name):
    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]))
    result = await start(hass, name)
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "name_exists"}


async def test_reminder_options_take_effect(hass, freezer):
    """Version 1 saved the interval where nothing read it."""
    freezer.move_to("2026-11-15 19:00:00+00:00")
    e = v2_entry("Litter Box 1", ["tag-1"], interval=5)
    await setup_entries(hass, e)
    await get_manager(hass).async_mark_done(
        [e.entry_id], by=None, when=dt_util.utcnow() - timedelta(days=5)
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.litter_box_1_progress").state == "100"

    result = await hass.config_entries.options.async_init(e.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"interval": 10, "interval_unit": "days", "tag_ids": ["tag-1", "master", "tag-1"]},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert e.data["interval"] == 10 and e.data["tag_ids"] == ["tag-1", "master"]
    assert e.options == {}

    progress = hass.states.get("sensor.litter_box_1_progress")
    assert progress.state == "50" and progress.attributes["interval"] == 10
    # The scan date survived the reload, and the new master tag works.
    hass.bus.async_fire("tag_scanned", {"tag_id": "master"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.litter_box_1_progress").state == "0"


async def test_reminder_options_need_a_tag(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    result = await hass.config_entries.options.async_init(e.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"interval": 5, "interval_unit": "days", "tag_ids": []}
    )
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "tag_required"}
    assert e.data["tag_ids"] == ["tag-1"]


async def test_notification_options(hass):
    async_mock_service(hass, "notify", "family_phones")
    async_mock_service(hass, "notify", "send_message")
    hass.states.async_set("notify.iphone", "unknown", {"friendly_name": "iPhone"})
    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]))
    entry = notifications_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    values = [o["value"] for o in result["data_schema"].schema["targets"].config["options"]]
    assert values == ["service:family_phones", "entity:notify.iphone"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "times": "14:00, 9, 9:00",
            "targets": ["service:family_phones", "entity:notify.iphone"],
            "notify_on_scan": True,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "times": ["09:00", "14:00"],
        "targets": ["service:family_phones", "entity:notify.iphone"],
        "notify_on_scan": True,
    }
    assert get_manager(hass).notify_settings == entry.options


@pytest.mark.parametrize("times", ["2pm", "25:00", "9, later", "", " , "])
async def test_bad_times_are_rejected_and_nothing_is_saved(hass, times):
    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]))
    entry = notifications_entry(hass)
    before = dict(entry.options)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"times": times, "targets": [], "notify_on_scan": False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"times": "invalid_time"}
    assert entry.options == before


async def test_a_target_that_went_missing_can_still_be_removed(hass):
    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]))
    entry = notifications_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "targets": ["service:old_phone"]}
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    values = [o["value"] for o in result["data_schema"].schema["targets"].config["options"]]
    assert "service:old_phone" in values
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"times": "09:00", "targets": [], "notify_on_scan": False}
    )
    await hass.async_block_till_done()
    assert entry.options["targets"] == []


def test_strings_match_translations_and_have_no_long_dash():
    strings = (COMPONENT / "strings.json").read_text(encoding="utf-8")
    english = (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
    assert json.loads(strings) == json.loads(english)
    assert EM_DASH not in strings and EM_DASH not in english


def test_no_long_dash_in_code_or_readme():
    files = list(COMPONENT.glob("*.py")) + [COMPONENT.parent.parent / "README.md"]
    assert not [f.name for f in files if EM_DASH in f.read_text(encoding="utf-8")]
