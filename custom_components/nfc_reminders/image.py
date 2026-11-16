"""QR code image for each reminder and each group."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import GroupEntity, ReminderEntity, is_group_entry, is_reminder_entry
from .manager import get_manager
from .qr import qr_svg


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = get_manager(hass)
    if is_reminder_entry(entry):
        async_add_entities([QrImage(hass, manager, entry)])
    elif is_group_entry(entry):
        async_add_entities([GroupQrImage(hass, manager, entry)])


class _QrImageMixin(ImageEntity):
    """The QR code of the first tag; the picture changes when that tag changes."""

    _attr_content_type = "image/svg+xml"
    _attr_icon = "mdi:qrcode"
    _tag_id: str | None

    def _tags(self) -> list[str]:
        raise NotImplementedError

    def _first_tag(self) -> str | None:
        tags = self._tags()
        return tags[0] if tags else None

    def _start_image(self, name: str, unique_id: str) -> None:
        self._attr_name = f"{name} QR Code"
        self._attr_unique_id = unique_id
        self._tag_id = self._first_tag()
        self._attr_image_last_updated = dt_util.utcnow()

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


class QrImage(ReminderEntity, _QrImageMixin):
    _handle_update = _QrImageMixin._handle_update

    def __init__(self, hass: HomeAssistant, manager, entry) -> None:
        ImageEntity.__init__(self, hass)
        ReminderEntity.__init__(self, manager, entry)
        self._start_image(self.reminder.name, f"{entry.entry_id}_qr")

    def _tags(self) -> list[str]:
        return self.reminder.tag_ids


class GroupQrImage(GroupEntity, _QrImageMixin):
    _handle_update = _QrImageMixin._handle_update

    def __init__(self, hass: HomeAssistant, manager, entry) -> None:
        ImageEntity.__init__(self, hass)
        GroupEntity.__init__(self, manager, entry)
        self._start_image(self.group.name, f"{entry.entry_id}_qr")

    def _tags(self) -> list[str]:
        return self.group.tag_ids
