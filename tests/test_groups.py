"""Groups: one tag, QR code or button marks several reminders done."""
from datetime import UTC, datetime, timedelta

import pytest

from homeassistant.core import Context
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.manager import get_manager
from custom_components.nfc_reminders.qr import qr_svg

from .conftest import group_entry, setup_entries, v2_entry

NOW = datetime(2026, 11, 15, 19, 0, tzinfo=UTC)
GROUP_TAG = "5a815f20-84b4-42af-9448-52099d20158c"


def boxes(n=4):
    return [v2_entry(f"Litter Box {i}", [f"tag-{i}"]) for i in range(1, n + 1)]


def state(hass, entity_id):
    return hass.states.get(entity_id).state


async def scan(hass, tag_id):
    hass.bus.async_fire("tag_scanned", {"tag_id": tag_id})
    await hass.async_block_till_done()


# ---------- setting one up ----------


async def open_group_form(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "group"}
    )


async def test_add_a_group_with_a_known_tag(hass):
    four = boxes()
    furnace = v2_entry("Furnace Filter", ["tag-f"], 30)
    await setup_entries(hass, *four, furnace)
    hass.states.async_set(
        "tag.all_litter_boxes_scan",
        "unknown",
        {"tag_id": GROUP_TAG, "friendly_name": "All Litter Boxes Scan"},
    )

    result = await open_group_form(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "group"
    offered = [o["value"] for o in result["data_schema"].schema["members"].config["options"]]
    assert set(offered) == {e.entry_id for e in [*four, furnace]}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"group_name": "All Litter Boxes", "members": [e.entry_id for e in four]},
    )
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "tag"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "existing"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tag_id": GROUP_TAG}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "All Litter Boxes"
    assert result["data"] == {
        "entry_type": "group",
        "group_name": "All Litter Boxes",
        "members": [e.entry_id for e in four],
        "tag_ids": [GROUP_TAG],
    }
    for entity_id in (
        "sensor.all_litter_boxes_status",
        "binary_sensor.all_litter_boxes_overdue",
        "button.all_litter_boxes_mark_done",
        "image.all_litter_boxes_qr_code",
    ):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_group_can_get_a_new_qr_only_tag(hass):
    four = boxes(2)
    await setup_entries(hass, *four)
    result = await open_group_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"group_name": "Both Boxes", "members": [e.entry_id for e in four]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "new_qr"}
    )
    await hass.async_block_till_done()
    (tag_id,) = result["data"]["tag_ids"]
    assert len(tag_id) == 36


async def test_group_needs_reminders_to_exist(hass):
    result = await open_group_form(hass)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_reminders"


@pytest.mark.parametrize(
    ("name", "members", "error"),
    [
        ("litter box 1", "all", "name_exists"),  # same entity ids as the reminder
        ("  ", "all", "name_required"),
        ("All Boxes", "none", "members_required"),
    ],
)
async def test_group_form_errors(hass, name, members, error):
    two = boxes(2)
    await setup_entries(hass, *two)
    chosen = {"all": [e.entry_id for e in two], "none": []}[members]
    result = await open_group_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"group_name": name, "members": chosen}
    )
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": error}


async def test_group_form_refuses_a_reminder_that_does_not_exist(hass):
    from homeassistant.data_entry_flow import InvalidData

    await setup_entries(hass, *boxes(1))
    result = await open_group_form(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"group_name": "X", "members": ["not-a-reminder"]}
        )


async def test_reminder_name_cannot_reuse_a_group_name(hass):
    two = boxes(2)
    await setup_entries(hass, *two, group_entry("All Boxes", two, ["g"]))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reminder"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"reminder_name": "all boxes", "interval": 5, "interval_unit": "days"},
    )
    assert result["errors"] == {"base": "name_exists"}


# ---------- what it does ----------


async def test_scanning_the_group_tag_marks_every_member_and_nothing_else(hass, freezer):
    freezer.move_to(NOW)
    four = boxes()
    furnace = v2_entry("Furnace Filter", ["tag-f"], 30)
    await setup_entries(hass, *four, furnace, group_entry("All Litter Boxes", four, [GROUP_TAG]))
    await scan(hass, GROUP_TAG)
    reminders = get_manager(hass).reminders
    assert all(reminders[e.entry_id].last_done == NOW for e in four)
    assert reminders[furnace.entry_id].last_done is None


async def test_a_members_own_tag_still_marks_only_that_member(hass):
    four = boxes()
    await setup_entries(hass, *four, group_entry("All Litter Boxes", four, [GROUP_TAG]))
    await scan(hass, "tag-2")
    reminders = get_manager(hass).reminders
    assert [reminders[e.entry_id].last_done is not None for e in four] == [
        False,
        True,
        False,
        False,
    ]


async def test_one_scan_message_for_the_whole_group(hass):
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
    two = boxes(2)
    await setup_entries(hass, notif, *two, group_entry("Both Boxes", two, ["g"]))
    await scan(hass, "g")
    assert len(calls) == 1
    assert calls[0].data["message"] == "Someone marked Litter Box 1, Litter Box 2 done"


async def test_a_reminder_in_two_groups_is_marked_once(hass):
    two = boxes(2)
    await setup_entries(
        hass, *two, group_entry("A", two, ["shared"]), group_entry("B", two[:1], ["shared"])
    )
    assert get_manager(hass).entry_ids_for_tag("shared") == [e.entry_id for e in two]


async def test_tapping_the_group_button_marks_every_member_with_who(
    hass, freezer, hass_admin_user
):
    freezer.move_to(NOW)
    four = boxes()
    await setup_entries(hass, *four, group_entry("All Litter Boxes", four, [GROUP_TAG]))
    hass.states.async_set(
        "person.marisa", "home", {"user_id": hass_admin_user.id, "friendly_name": "Marisa"}
    )
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.all_litter_boxes_mark_done"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    for e in four:
        rem = get_manager(hass).reminders[e.entry_id]
        assert rem.last_done == NOW and rem.last_done_by == "Marisa"
    assert state(hass, "sensor.litter_box_3_last_done_by") == "Marisa"


async def test_mark_done_action_accepts_a_group(hass):
    two = boxes(2)
    other = v2_entry("Furnace Filter", ["tag-f"], 30)
    await setup_entries(hass, *two, other, group_entry("Both Boxes", two, ["g"]))
    await hass.services.async_call(
        DOMAIN, "mark_done", {"entity_id": "sensor.both_boxes_status"}, blocking=True
    )
    reminders = get_manager(hass).reminders
    assert all(reminders[e.entry_id].last_done is not None for e in two)
    assert reminders[other.entry_id].last_done is None


async def test_group_status_is_the_most_urgent_member(hass, freezer):
    freezer.move_to(NOW)
    four = boxes()
    await setup_entries(hass, *four, group_entry("All Litter Boxes", four, [GROUP_TAG]))
    manager = get_manager(hass)

    assert state(hass, "sensor.all_litter_boxes_status") == "good"  # none ever done
    assert state(hass, "binary_sensor.all_litter_boxes_overdue") == "off"

    await manager.async_mark_done([e.entry_id for e in four], by=None)
    await manager.async_mark_done([four[1].entry_id], by=None, when=NOW - timedelta(days=3))
    await hass.async_block_till_done()
    assert state(hass, "sensor.all_litter_boxes_status") == "warning"

    await manager.async_mark_done([four[2].entry_id], by=None, when=NOW - timedelta(days=9))
    await hass.async_block_till_done()
    status = hass.states.get("sensor.all_litter_boxes_status")
    assert status.state == "overdue"
    assert status.attributes["members"] == [f"Litter Box {i}" for i in range(1, 5)]
    assert status.attributes["overdue"] == ["Litter Box 3"]
    overdue = hass.states.get("binary_sensor.all_litter_boxes_overdue")
    assert overdue.state == "on" and overdue.attributes["overdue"] == ["Litter Box 3"]

    await scan(hass, GROUP_TAG)
    assert state(hass, "sensor.all_litter_boxes_status") == "good"
    assert state(hass, "binary_sensor.all_litter_boxes_overdue") == "off"


async def test_group_set_up_before_its_reminders_still_shows_them(hass, freezer):
    freezer.move_to(NOW)
    two = boxes(2)
    group = group_entry("Both Boxes", two, ["g"])
    # The group's entry comes first, so its entities exist before the reminders do.
    await setup_entries(hass, group, *two)
    assert hass.states.get("sensor.both_boxes_status").attributes["members"] == [
        "Litter Box 1",
        "Litter Box 2",
    ]


async def test_deleting_a_member_leaves_the_group_working(hass):
    two = boxes(2)
    await setup_entries(hass, *two, group_entry("Both Boxes", two, ["g"]))
    await hass.config_entries.async_remove(two[0].entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.both_boxes_status").attributes["members"] == ["Litter Box 2"]
    await scan(hass, "g")
    assert get_manager(hass).reminders[two[1].entry_id].last_done is not None


async def test_deleting_a_group_keeps_its_reminders_and_their_dates(hass):
    two = boxes(2)
    group = group_entry("Both Boxes", two, ["g"])
    await setup_entries(hass, *two, group)
    await scan(hass, "g")
    await hass.config_entries.async_remove(group.entry_id)
    await hass.async_block_till_done()

    manager = get_manager(hass)
    assert group.entry_id not in manager.groups
    assert all(manager.reminders[e.entry_id].last_done is not None for e in two)
    assert hass.states.get("sensor.both_boxes_status") is None
    await scan(hass, "g")  # the group's tag now does nothing, without errors


async def test_group_settings_change_members_and_tags(hass):
    four = boxes()
    group = group_entry("Some Boxes", four[:2], ["old"])
    await setup_entries(hass, *four, group)

    result = await hass.config_entries.options.async_init(group.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"members": [four[2].entry_id, four[3].entry_id], "tag_ids": ["new", " new "]},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert group.data["members"] == [four[2].entry_id, four[3].entry_id]
    assert group.data["tag_ids"] == ["new"]

    await scan(hass, "old")
    await scan(hass, "new")
    reminders = get_manager(hass).reminders
    assert [reminders[e.entry_id].last_done is not None for e in four] == [
        False,
        False,
        True,
        True,
    ]


@pytest.mark.parametrize(
    ("members", "tags", "error"),
    [("none", ["g"], "members_required"), ("all", [], "tag_required")],
)
async def test_group_settings_errors(hass, members, tags, error):
    two = boxes(2)
    group = group_entry("Both Boxes", two, ["g"])
    await setup_entries(hass, *two, group)
    result = await hass.config_entries.options.async_init(group.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"members": [] if members == "none" else [e.entry_id for e in two], "tag_ids": tags},
    )
    assert result["errors"] == {"base": error}
    assert group.data["tag_ids"] == ["g"]


async def test_group_entities_and_qr(hass, hass_client):
    two = boxes(2)
    group = group_entry("Both Boxes", two, ["g-tag", "second"])
    await setup_entries(hass, *two, group)
    registry = er.async_get(hass)
    unique = {
        entry.entity_id: entry.unique_id
        for entry in er.async_entries_for_config_entry(registry, group.entry_id)
    }
    assert unique == {
        "sensor.both_boxes_status": f"{group.entry_id}_status",
        "binary_sensor.both_boxes_overdue": f"{group.entry_id}_overdue",
        "button.both_boxes_mark_done": f"{group.entry_id}_mark_done",
        "image.both_boxes_qr_code": f"{group.entry_id}_qr",
    }
    client = await hass_client()
    response = await client.get("/api/image_proxy/image.both_boxes_qr_code")
    assert response.status == 200 and await response.read() == qr_svg("g-tag")


async def test_qr_sheet_lists_groups_first_and_labels_them(hass, hass_client_no_auth):
    two = boxes(2)
    await setup_entries(hass, *two, group_entry("Zebra Group", two, ["g"]))
    response = await hass.services.async_call(
        DOMAIN, "create_qr_sheet", {}, blocking=True, return_response=True
    )
    client = await hass_client_no_auth()
    text = await (await client.get(response["url"])).text()
    assert text.count("<svg") == 3
    assert text.index("Zebra Group") < text.index("Litter Box 1")
    assert text.count('class="kind">Group<') == 1
