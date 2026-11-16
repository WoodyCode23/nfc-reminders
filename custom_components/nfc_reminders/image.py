"""QR code image for each reminder."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import ReminderEntity, is_reminder_entry
from .manager import get_manager
from .qr import qr_svg


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not is_reminder_entry(entry):
        return
    async_add_entities([QrImage(hass, get_manager(hass), entry)])


class QrImage(ReminderEntity, ImageEntity):
    """The QR code of the reminder's first tag."""

    _attr_content_type = "image/svg+xml"
    _attr_icon = "mdi:qrcode"

    def __init__(self, hass: HomeAssistant, manager, entry) -> None:
        ImageEntity.__init__(self, hass)
        ReminderEntity.__init__(self, manager, entry)
        self._attr_name = f"{self.reminder.name} QR Code"
        self._attr_unique_id = f"{entry.entry_id}_qr"
        self._tag_id = self._first_tag()
        self._attr_image_last_updated = dt_util.utcnow()

    def _first_tag(self) -> str | None:
        tags = self.reminder.tag_ids
        return tags[0] if tags else None

    async def async_image(self) -> bytes | None:
        tag_id = self._first_tag()
        if tag_id is None:
            return None
        return await self.hass.async_add_executor_job(qr_svg, tag_id)

    @callback
    def _handle_update(self) -> None:
        tag_id = self._first_tag()
        if tag_id != self._tag_id:
            self._tag_id = tag_id
            self._attr_image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()
