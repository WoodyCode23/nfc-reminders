"""Emojis in notifications: a status dot by default, or the reminder's own emoji."""
from datetime import UTC, datetime, timedelta

from homeassistant.core import Context
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.notifications import build_overview
from custom_components.nfc_reminders.reminder import Reminder

from .conftest import group_entry, setup_entries, v2_entry

NOW = datetime(2026, 11, 16, 19, 0, tzinfo=UTC)
CAT, TOOTH, RED, YELLOW, CHECK = "\U0001F431", "\U0001FAA5", "\U0001F534", "\U0001F7E1", "✅"


def rem(name, days_ago, emoji="", remind_after=None, interval=5):
    return Reminder(name, name, [], interval, "days", NOW - timedelta(days=days_ago), remind_after=remind_after, emoji=emoji)


def notif(notify_on_scan=True):
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Notifications",
        unique_id="notifications",
        data={"entry_type": "notifications"},
        options={"times": ["09:00"], "targets": ["service:family_phones"], "notify_on_scan": notify_on_scan},
    )


def test_overview_uses_own_emoji_or_a_status_dot():
    title, body = build_overview(
        [
            rem("Stairs Left", 72, CAT),
            rem("Furnace Filter", 40, interval=30),
            rem("Brush Teeth", 4, TOOTH, remind_after=3),
            rem("Plants", 3.5, remind_after=3),
        ],
        NOW,
    )
    assert title == f"{RED} 2 overdue, {YELLOW} 2 due soon"
    assert body.splitlines() == [
        f"{CAT} Stairs Left: 72 days (every 5 days)",
        f"{RED} Furnace Filter: 40 days (every 30 days)",
        f"{TOOTH} Brush Teeth: due in 1 day",
        f"{YELLOW} Plants: due in 2 days",
    ]


def test_label():
    assert rem("Stairs Left", 1, CAT).label == f"{CAT} Stairs Left"
    assert rem("Stairs Left", 1).label == "Stairs Left"


async def test_emoji_is_set_changed_and_cleared_in_settings(hass):
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)

    async def configure(**extra):
        result = await hass.config_entries.options.async_init(e.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"reminder_name": "Litter Box 1", "interval": 5, "interval_unit": "days", "tag_ids": ["tag-1"], **extra},
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY

    await configure(emoji=f" {CAT} ")
    assert e.data["emoji"] == CAT and get_manager(hass).reminders[e.entry_id].emoji == CAT
    await configure(emoji="x" * 40)
    assert len(e.data["emoji"]) == 8  # kept short so it cannot swamp the message
    await configure()  # left empty
    assert e.data["emoji"] == "" and get_manager(hass).reminders[e.entry_id].label == "Litter Box 1"


async def test_new_reminder_with_an_emoji(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "reminder"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"reminder_name": "Brush Teeth", "interval": 1, "interval_unit": "days", "emoji": TOOTH},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "new_qr"})
    await hass.async_block_till_done()
    assert result["data"]["emoji"] == TOOTH


async def test_scan_message_shows_emoji_who_and_time(hass, freezer):
    freezer.move_to("2026-11-16 14:05:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    e = v2_entry("Stairs Left", ["tag-1"])
    e.add_to_hass(hass)
    hass.config_entries.async_update_entry(e, data={**e.data, "emoji": CAT})
    await setup_entries(hass, notif())
    hass.bus.async_fire("tag_scanned", {"tag_id": "tag-1"})
    await hass.async_block_till_done()
    assert calls[0].data["title"] == f"{CHECK} Stairs Left done"
    assert calls[0].data["message"] == f"{CAT} Stairs Left\nMarked done by someone at 2:05 PM"


async def test_group_button_announces_the_group_by_name(hass, freezer, hass_admin_user):
    freezer.move_to("2026-11-16 09:30:00-05:00")
    calls = async_mock_service(hass, "notify", "family_phones")
    boxes = [v2_entry(f"Litter Box {n}", [f"tag-{n}"]) for n in (1, 2)]
    await setup_entries(hass, notif(), *boxes, group_entry("All Litter Boxes", boxes, ["g"]))
    hass.states.async_set("person.ryan", "home", {"user_id": hass_admin_user.id, "friendly_name": "Ryan"})
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.all_litter_boxes_mark_done"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert calls[0].data["title"] == f"{CHECK} All Litter Boxes done"
    assert calls[0].data["message"] == "Litter Box 1, Litter Box 2\nMarked done by Ryan at 9:30 AM"


async def test_a_tag_shared_without_a_group_is_counted_not_named(hass):
    calls = async_mock_service(hass, "notify", "family_phones")
    boxes = [v2_entry(f"Litter Box {n}", [f"tag-{n}", "shared"]) for n in (1, 2, 3)]
    await setup_entries(hass, notif(), *boxes)
    hass.bus.async_fire("tag_scanned", {"tag_id": "shared"})
    await hass.async_block_till_done()
    assert calls[0].data["title"] == f"{CHECK} 3 things done"
