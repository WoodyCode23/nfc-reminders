"""Base classes for the entities of a reminder and of a group."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_GROUP,
    ENTRY_TYPE_REMINDER,
    SIGNAL_UPDATE,
)
from .manager import Manager
from .reminder import Group, Reminder


def is_reminder_entry(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_REMINDER


def is_group_entry(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_GROUP


class _UpdatingEntity(Entity):
    """Refreshes on the shared update signal (scans, edits, once a minute)."""

    _attr_should_poll = False

    def __init__(self, manager: Manager, entry: ConfigEntry, name: str, model: str) -> None:
        self._manager = manager
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="NFC Reminders",
            model=model,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ReminderEntity(_UpdatingEntity):
    """A thin view of one reminder."""

    def __init__(self, manager: Manager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, manager.reminders[entry.entry_id].name, "Reminder")

    @property
    def reminder(self) -> Reminder:
        return self._manager.reminders[self._entry.entry_id]

    @property
    def available(self) -> bool:
        return self._entry.entry_id in self._manager.reminders


class GroupEntity(_UpdatingEntity):
    """A thin view of one group and its member reminders."""

    def __init__(self, manager: Manager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, manager.groups[entry.entry_id].name, "Group")

    @property
    def reminder_group(self) -> Group:
        # Not "group": Home Assistant reserves Entity.group for its own entity groups.
        return self._manager.groups[self._entry.entry_id]

    @property
    def members(self) -> list[Reminder]:
        return self._manager.members_of(self._entry.entry_id)

    @property
    def available(self) -> bool:
        return self._entry.entry_id in self._manager.groups
