"""QR codes: the tag link, the picture, and the printable sheet."""
from __future__ import annotations

from datetime import timedelta
from html import escape
import io

from aiohttp import web
import segno

from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, QR_SHEET_URL, TAG_URL_PREFIX
from .reminder import Reminder

SHEET_LINK_VALID = timedelta(hours=1)
SHEET_NOTIFICATION_ID = "nfc_reminders_qr_sheet"


def tag_url(tag_id: str) -> str:
    """The same link Home Assistant writes to an NFC tag."""
    return TAG_URL_PREFIX + tag_id


def _svg(tag_id: str, *, xmldecl: bool) -> bytes:
    out = io.BytesIO()
    segno.make(tag_url(tag_id), error="m").save(
        out, kind="svg", scale=8, border=2, xmldecl=xmldecl
    )
    return out.getvalue()


def qr_svg(tag_id: str) -> bytes:
    """A standalone SVG document."""
    return _svg(tag_id, xmldecl=True)


def sheet_html(reminders: list[Reminder]) -> str:
    """One page with every reminder's QR code and its name underneath."""
    cards = []
    for reminder in sorted(reminders, key=lambda r: r.name.lower()):
        if not reminder.tag_ids:
            continue
        svg = _svg(reminder.tag_ids[0], xmldecl=False).decode("utf-8")
        cards.append(
            f'<div class="card">{svg}<div class="name">{escape(reminder.name)}</div></div>'
        )
    body = "\n".join(cards) or "<p>No reminders yet.</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NFC Reminders QR codes</title>
<style>
  body {{ font-family: sans-serif; margin: 16px; color: #000; background: #fff; }}
  h1 {{ font-size: 18px; }}
  p.hint {{ font-size: 13px; color: #444; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
  .card {{ border: 1px dashed #999; padding: 8px; text-align: center; break-inside: avoid; }}
  .card svg {{ width: 100%; height: auto; }}
  .name {{ font-weight: bold; margin-top: 4px; }}
  @media print {{ h1, p.hint {{ display: none; }} body {{ margin: 0; }} }}
</style>
</head>
<body>
<h1>NFC Reminders QR codes</h1>
<p class="hint">Print this page and cut along the dashed lines. Scan a code with a phone that has the Home Assistant app to mark that reminder done.</p>
<div class="grid">
{body}
</div>
</body>
</html>
"""


class QrSheetView(HomeAssistantView):
    """Serves the printable sheet to a signed-in user or a signed link."""

    url = QR_SHEET_URL
    name = "api:nfc_reminders:qr_sheet"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        manager = hass.data[DOMAIN]
        html = await hass.async_add_executor_job(
            sheet_html, list(manager.reminders.values())
        )
        return web.Response(text=html, content_type="text/html")


@callback
def async_sheet_link(hass: HomeAssistant) -> str:
    """A link to the sheet that works for one hour without signing in again."""
    return async_sign_path(hass, QR_SHEET_URL, SHEET_LINK_VALID, use_content_user=True)


@callback
def async_announce_sheet(hass: HomeAssistant) -> str:
    """Put the sheet link in a persistent notification and return it."""
    link = async_sheet_link(hass)
    persistent_notification.async_create(
        hass,
        f"[Open the printable QR sheet]({link})\n\nThe link works for one hour.",
        title="NFC Reminders QR sheet",
        notification_id=SHEET_NOTIFICATION_ID,
    )
    return link
