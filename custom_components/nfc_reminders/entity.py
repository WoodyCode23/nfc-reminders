"""Base class for everything that belongs to one reminder."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_NOTIFICATIONS, SIGNAL_UPDATE
from .manager import Manager
from .reminder import Reminder


def is_reminder_entry(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_NOTIFICATIONS


class ReminderEntity(Entity):
    """A thin view of one reminder; refreshes on the shared update signal."""

    _attr_should_poll = False

    def __init__(self, manager: Manager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=self.reminder.name,
            manufacturer="NFC Reminders",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def reminder(self) -> Reminder:
        return self._manager.reminders[self._entry.entry_id]

    @property
    def available(self) -> bool:
        return self._entry.entry_id in self._manager.reminders

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
