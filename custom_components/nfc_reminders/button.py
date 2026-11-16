"""Buttons for NFC Reminders."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import GroupEntity, ReminderEntity, is_group_entry, is_reminder_entry
from .manager import get_manager
from .qr import async_announce_sheet
from .who import async_resolve_user


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if is_reminder_entry(entry):
        async_add_entities([MarkDoneButton(get_manager(hass), entry)])
    elif is_group_entry(entry):
        async_add_entities([GroupMarkDoneButton(get_manager(hass), entry)])
    else:
        async_add_entities([QrSheetButton(entry)])


async def _who_pressed(entity: ButtonEntity) -> str | None:
    user_id = entity._context.user_id if entity._context else None
    return await async_resolve_user(entity.hass, user_id)


class MarkDoneButton(ReminderEntity, ButtonEntity):
    """Does the same as scanning the tag."""

    _attr_icon = "mdi:check-bold"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Mark Done"
        self._attr_unique_id = f"{entry.entry_id}_mark_done"

    async def async_press(self) -> None:
        await self._manager.async_mark_done(
            [self._entry.entry_id], by=await _who_pressed(self)
        )


class GroupMarkDoneButton(GroupEntity, ButtonEntity):
    """Marks every reminder in the group done, the same as scanning the group's tag."""

    _attr_icon = "mdi:check-all"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder_group.name} Mark Done"
        self._attr_unique_id = f"{entry.entry_id}_mark_done"

    async def async_press(self) -> None:
        await self._manager.async_mark_done(
            [r.entry_id for r in self.members], by=await _who_pressed(self)
        )


class QrSheetButton(ButtonEntity):
    """Makes a link to a printable page with every QR code."""

    _attr_icon = "mdi:qrcode"
    _attr_name = "Create printable QR sheet"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_qr_sheet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="NFC Reminders",
            manufacturer="NFC Reminders",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        async_announce_sheet(self.hass)
