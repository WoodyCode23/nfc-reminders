"""Sensors for NFC Reminders."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import GroupEntity, ReminderEntity, is_group_entry, is_reminder_entry
from .manager import get_manager
from .reminder import safe_name, worst_status

_STATUS_ICONS = {
    "good": "mdi:check-circle",
    "warning": "mdi:alert-circle",
    "overdue": "mdi:alert-circle-outline",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = get_manager(hass)
    if is_group_entry(entry):
        async_add_entities([GroupStatusSensor(manager, entry)])
        return
    if not is_reminder_entry(entry):
        return
    async_add_entities(
        [
            LastScanSensor(manager, entry),
            DaysSinceSensor(manager, entry),
            ProgressSensor(manager, entry),
            StatusSensor(manager, entry),
            NextDueSensor(manager, entry),
            LastDoneBySensor(manager, entry),
        ]
    )


class LastScanSensor(ReminderEntity, SensorEntity):
    """When it was last done, as readable text (format kept from version 1)."""

    _attr_icon = "mdi:nfc-variant"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Last Scan"
        self._attr_unique_id = f"{safe_name(self.reminder.name)}_last_scan_display"

    @property
    def native_value(self) -> str:
        last = self.reminder.last_done
        if last is None:
            return "Never scanned"
        return dt_util.as_local(last).strftime("%B %d, %Y at %I:%M %p")


class DaysSinceSensor(ReminderEntity, SensorEntity):
    """Days since it was last done. Unknown when it never was."""

    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_suggested_display_precision = 1

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Days Since Scan"
        self._attr_unique_id = f"{safe_name(self.reminder.name)}_days_since_scan"

    @property
    def native_value(self) -> float | None:
        return self.reminder.days_since(dt_util.utcnow())


class ProgressSensor(ReminderEntity, SensorEntity):
    """How far through the interval it is, 0 to 100."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Progress"
        self._attr_unique_id = f"{safe_name(self.reminder.name)}_progress"

    @property
    def native_value(self) -> int:
        return self.reminder.progress(dt_util.utcnow())

    @property
    def icon(self) -> str:
        value = self.native_value
        if value < 50:
            return "mdi:check-circle"
        if value < 80:
            return "mdi:alert-circle"
        return "mdi:alert-circle-outline"

    @property
    def extra_state_attributes(self) -> dict:
        reminder = self.reminder
        return {
            "status": reminder.status(dt_util.utcnow()),
            "interval": reminder.interval,
            "interval_unit": reminder.unit,
            "nfc_tag_id": reminder.tag_ids[0] if reminder.tag_ids else None,
            "tag_ids": list(reminder.tag_ids),
        }


class StatusSensor(ReminderEntity, SensorEntity):
    """good, warning or overdue, as a state that automations can trigger on."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["good", "warning", "overdue"]
    _attr_translation_key = "status"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Status"
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        return self.reminder.status(dt_util.utcnow())

    @property
    def icon(self) -> str:
        return _STATUS_ICONS[self.native_value]


class GroupStatusSensor(GroupEntity, SensorEntity):
    """The most urgent status among the group's reminders."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["good", "warning", "overdue"]
    _attr_translation_key = "status"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder_group.name} Status"
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        return worst_status(self.members, dt_util.utcnow())

    @property
    def icon(self) -> str:
        return _STATUS_ICONS[self.native_value]

    @property
    def extra_state_attributes(self) -> dict:
        now = dt_util.utcnow()
        return {
            "members": [r.name for r in self.members],
            "overdue": [r.name for r in self.members if r.is_overdue(now)],
            "tag_ids": list(self.reminder_group.tag_ids),
        }


class NextDueSensor(ReminderEntity, SensorEntity):
    """When it is next due."""

    _attr_icon = "mdi:calendar-alert"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Next Due"
        self._attr_unique_id = f"{entry.entry_id}_next_due"

    @property
    def native_value(self) -> datetime | None:
        return self.reminder.next_due


class LastDoneBySensor(ReminderEntity, SensorEntity):
    """Who did it last."""

    _attr_icon = "mdi:account-check"

    def __init__(self, manager, entry) -> None:
        super().__init__(manager, entry)
        self._attr_name = f"{self.reminder.name} Last Done By"
        self._attr_unique_id = f"{entry.entry_id}_last_done_by"

    @property
    def native_value(self) -> str:
        return self.reminder.last_done_by or "Unknown"
