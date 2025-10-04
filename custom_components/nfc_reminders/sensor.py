"""Sensor platform for NFC Reminders."""
from datetime import datetime, timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_REMINDER_NAME,
    CONF_NFC_TAG_ID,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NFC Reminder sensors."""
    reminder_name = config_entry.data[CONF_REMINDER_NAME]
    safe_name = reminder_name.lower().replace(" ", "_")
    
    entities = [
        NFCReminderLastScanSensor(hass, config_entry, safe_name, reminder_name),
        NFCReminderDaysSinceSensor(hass, config_entry, safe_name, reminder_name),
        NFCReminderProgressSensor(hass, config_entry, safe_name, reminder_name),
    ]
    
    async_add_entities(entities, True)


class NFCReminderLastScanSensor(SensorEntity):
    """Sensor showing when the reminder was last scanned."""

    def __init__(self, hass, config_entry, safe_name, reminder_name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._safe_name = safe_name
        self._reminder_name = reminder_name
        self._attr_name = f"{reminder_name} Last Scan"
        self._attr_unique_id = f"{safe_name}_last_scan_display"
        self._datetime_entity = f"input_datetime.{safe_name}_last_scan"
        self._state = None

    @property
    def state(self):
        """Return the state of the sensor."""
        datetime_state = self.hass.states.get(self._datetime_entity)
        if datetime_state and datetime_state.state not in ["unknown", "unavailable"]:
            try:
                dt = datetime.fromisoformat(datetime_state.state)
                return dt.strftime("%B %d, %Y at %I:%M %p")
            except (ValueError, AttributeError):
                return "Never scanned"
        return "Never scanned"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:nfc-variant"

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        @callback
        def sensor_state_listener(event):
            """Handle state changes."""
            self.async_schedule_update_ha_state(True)

        async_track_state_change_event(
            self.hass, [self._datetime_entity], sensor_state_listener
        )


class NFCReminderDaysSinceSensor(SensorEntity):
    """Sensor showing days since last scan."""

    def __init__(self, hass, config_entry, safe_name, reminder_name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._safe_name = safe_name
        self._reminder_name = reminder_name
        self._attr_name = f"{reminder_name} Days Since Scan"
        self._attr_unique_id = f"{safe_name}_days_since_scan"
        self._datetime_entity = f"input_datetime.{safe_name}_last_scan"
        self._attr_unit_of_measurement = "days"
        self._attr_device_class = "duration"

    @property
    def state(self):
        """Return the state of the sensor."""
        datetime_state = self.hass.states.get(self._datetime_entity)
        if datetime_state and datetime_state.state not in ["unknown", "unavailable"]:
            try:
                last_scan = datetime.fromisoformat(datetime_state.state)
                now = dt_util.now()
                diff = now - dt_util.as_local(last_scan)
                return round(diff.total_seconds() / 86400, 1)
            except (ValueError, AttributeError):
                return 99
        return 99

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-clock"

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        @callback
        def sensor_state_listener(event):
            """Handle state changes."""
            self.async_schedule_update_ha_state(True)

        async_track_state_change_event(
            self.hass, [self._datetime_entity], sensor_state_listener
        )


class NFCReminderProgressSensor(SensorEntity):
    """Sensor showing progress percentage toward next reminder."""

    def __init__(self, hass, config_entry, safe_name, reminder_name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._safe_name = safe_name
        self._reminder_name = reminder_name
        self._attr_name = f"{reminder_name} Progress"
        self._attr_unique_id = f"{safe_name}_progress"
        self._datetime_entity = f"input_datetime.{safe_name}_last_scan"
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        """Return the state of the sensor."""
        datetime_state = self.hass.states.get(self._datetime_entity)
        if datetime_state and datetime_state.state not in ["unknown", "unavailable"]:
            try:
                last_scan = datetime.fromisoformat(datetime_state.state)
                now = dt_util.now()
                diff = now - dt_util.as_local(last_scan)
                
                interval = self._config_entry.data[CONF_INTERVAL]
                unit = self._config_entry.data[CONF_INTERVAL_UNIT]
                
                # Calculate threshold in seconds
                if unit == "minutes":
                    threshold = interval * 60
                elif unit == "hours":
                    threshold = interval * 3600
                else:  # days
                    threshold = interval * 86400
                
                percentage = min((diff.total_seconds() / threshold) * 100, 100)
                return round(percentage)
            except (ValueError, AttributeError):
                return 0
        return 0

    @property
    def icon(self):
        """Return the icon."""
        state = self.state
        if state < 50:
            return "mdi:check-circle"
        elif state < 80:
            return "mdi:alert-circle"
        else:
            return "mdi:alert-circle-outline"

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        state_val = self.state
        if state_val < 50:
            status = "good"
        elif state_val < 80:
            status = "warning"
        else:
            status = "overdue"
            
        return {
            "status": status,
            "interval": self._config_entry.data[CONF_INTERVAL],
            "interval_unit": self._config_entry.data[CONF_INTERVAL_UNIT],
            "nfc_tag_id": self._config_entry.data[CONF_NFC_TAG_ID],
        }

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        @callback
        def sensor_state_listener(event):
            """Handle state changes."""
            self.async_schedule_update_ha_state(True)

        async_track_state_change_event(
            self.hass, [self._datetime_entity], sensor_state_listener
        )