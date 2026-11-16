"""QR codes and the printable sheet."""
import re

from homeassistant.util import dt as dt_util

from custom_components.nfc_reminders.const import DOMAIN
from custom_components.nfc_reminders.qr import qr_svg, sheet_html, tag_url
from custom_components.nfc_reminders.reminder import Reminder

from .conftest import setup_entries, v2_entry


def test_tag_url():
    assert tag_url("abc") == "https://www.home-assistant.io/tag/abc"


def test_qr_svg_is_an_svg_document():
    svg = qr_svg("abc")
    assert isinstance(svg, bytes) and svg.startswith(b"<?xml") and b"<svg" in svg
    assert qr_svg("abc") == svg and qr_svg("abd") != svg
    root = re.search(rb"<svg[^>]*>", svg).group(0)
    assert b"viewBox" in root and b"width=" in root and b"height=" in root


def test_sheet_lists_every_reminder_once_and_escapes_names():
    html = sheet_html(
        [
            Reminder("1", "Litter Box 1", ["t1", "master"]),
            Reminder("2", "<b>Bold</b> & Co", ["t2"]),
            Reminder("3", "No Tag", []),
        ]
    )
    assert html.count(">Litter Box 1<") == 1
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; Co" in html and "<b>Bold" not in html
    assert html.count("<svg") == 2 and "No Tag" not in html
    assert "<?xml" not in html
    # Each code scales by viewBox; a fixed width/height gets cropped when CSS resizes it.
    for svg in re.findall(r"<svg[^>]*>", html):
        assert "viewBox" in svg and "width=" not in svg and "height=" not in svg


async def test_image_entity_serves_the_first_tags_qr(hass, hass_client):
    e = v2_entry("Litter Box 1", ["tag-1", "master"])
    await setup_entries(hass, e)
    state = hass.states.get("image.litter_box_1_qr_code")
    assert state is not None and state.state not in ("unknown", "unavailable")

    client = await hass_client()
    response = await client.get("/api/image_proxy/image.litter_box_1_qr_code")
    assert response.status == 200
    assert response.headers["Content-Type"].startswith("image/svg+xml")
    assert await response.read() == qr_svg("tag-1")


async def test_image_changes_when_the_first_tag_changes(hass, freezer):
    freezer.move_to("2026-11-15 19:00:00+00:00")
    e = v2_entry("Litter Box 1", ["tag-1"])
    await setup_entries(hass, e)
    first = hass.states.get("image.litter_box_1_qr_code").state

    freezer.move_to("2026-11-15 19:05:00+00:00")
    hass.config_entries.async_update_entry(e, data={**e.data, "tag_ids": ["tag-9", "tag-1"]})
    await hass.async_block_till_done()
    assert hass.states.get("image.litter_box_1_qr_code").state != first


async def test_sheet_needs_sign_in_or_a_signed_link(hass, hass_client_no_auth):
    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]), v2_entry("Bath & Body", ["tag-2"]))
    client = await hass_client_no_auth()
    assert (await client.get("/api/nfc_reminders/qr_sheet")).status == 401

    response = await hass.services.async_call(
        DOMAIN, "create_qr_sheet", {}, blocking=True, return_response=True
    )
    url = response["url"]
    assert url.startswith("/api/nfc_reminders/qr_sheet?authSig=")

    page = await client.get(url)
    assert page.status == 200
    text = await page.text()
    assert "Litter Box 1" in text and "Bath &amp; Body" in text and text.count("<svg") == 2

    # A tampered signature is refused.
    assert (await client.get(url.replace("authSig=", "authSig=x"))).status == 401


async def test_sheet_button_leaves_a_link_in_a_notification(hass):
    from homeassistant.components import persistent_notification

    await setup_entries(hass, v2_entry("Litter Box 1", ["tag-1"]))
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.create_printable_qr_sheet"}, blocking=True
    )
    await hass.async_block_till_done()
    notes = persistent_notification._async_get_or_create_notifications(hass)
    (note,) = [n for n in notes.values() if n["notification_id"] == "nfc_reminders_qr_sheet"]
    assert "/api/nfc_reminders/qr_sheet?authSig=" in note["message"]
