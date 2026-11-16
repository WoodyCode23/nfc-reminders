"""Overdue binary sensors for NFC Reminders."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import GroupEntity, ReminderEntity, is_group_entry, is_reminder_entry
from .manager import get_manager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = get_manager(hass)
    if is_reminder_entry(entry):
        async_add_entities([OverdueSensor(manager, entry)])
    elif is_group_entry(entry):
        async_add_entities([GroupOverdueSensor(manager, entry)])


class OverdueSensor(ReminderEntity, BinarySensorEntity):
    """On from the moment the reminder is due."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Overdue"
        self._attr_unique_id = f"{entry.entry_id}_overdue"

    @property
    def is_on(self) -> bool:
        return self.reminder.is_overdue(dt_util.utcnow())


class GroupOverdueSensor(GroupEntity, BinarySensorEntity):
    """On while any reminder in the group is overdue."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.group.name} Overdue"
        self._attr_unique_id = f"{entry.entry_id}_overdue"

    @property
    def is_on(self) -> bool:
        now = dt_util.utcnow()
        return any(r.is_overdue(now) for r in self.members)

    @property
    def extra_state_attributes(self) -> dict:
        now = dt_util.utcnow()
        return {"overdue": [r.name for r in self.members if r.is_overdue(now)]}
