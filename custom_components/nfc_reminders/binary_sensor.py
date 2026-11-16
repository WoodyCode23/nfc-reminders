"""Overdue binary sensor for NFC Reminders."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import ReminderEntity, is_reminder_entry
from .manager import get_manager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not is_reminder_entry(entry):
        return
    async_add_entities([OverdueSensor(get_manager(hass), entry)])


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
