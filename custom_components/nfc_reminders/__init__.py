"""NFC Reminders Integration."""
import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, CONF_NFC_TAG_ID, CONF_REMINDER_NAME

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NFC Reminders from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Create the helper entities automatically
    await _create_helper_entities(hass, entry)

    # Listen for NFC tag scans
    async def handle_tag_scanned(event):
        """Handle NFC tag scanned event."""
        tag_id = event.data.get("tag_id")
        
        # Check if this tag matches our reminder
        if tag_id == entry.data.get(CONF_NFC_TAG_ID):
            reminder_name = entry.data.get(CONF_REMINDER_NAME)
            safe_name = reminder_name.lower().replace(" ", "_")
            
            # Update the datetime helper
            datetime_entity = f"input_datetime.{safe_name}_last_scan"
            if hass.states.get(datetime_entity):
                now = datetime.now()
                await hass.services.async_call(
                    "input_datetime",
                    "set_datetime",
                    {
                        "entity_id": datetime_entity,
                        "datetime": now.isoformat()[:19]
                    },
                    blocking=True
                )
                _LOGGER.info(f"Updated {datetime_entity} after NFC scan")

    hass.bus.async_listen("tag_scanned", handle_tag_scanned)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _create_helper_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create input_datetime and input_text helper entities."""
    reminder_name = entry.data.get(CONF_REMINDER_NAME)
    safe_name = reminder_name.lower().replace(" ", "_")
    
    # Create input_datetime
    datetime_entity_id = f"input_datetime.{safe_name}_last_scan"
    if not hass.states.get(datetime_entity_id):
        await hass.services.async_call(
            "input_datetime",
            "create",
            {
                "name": f"{reminder_name} Last Scan",
                "has_date": True,
                "has_time": True,
            },
            blocking=True,
        )
        _LOGGER.info(f"Created helper entity: {datetime_entity_id}")
    
    # Create input_text
    text_entity_id = f"input_text.{safe_name}_last_cleaned_by"
    if not hass.states.get(text_entity_id):
        await hass.services.async_call(
            "input_text",
            "create",
            {
                "name": f"{reminder_name} Last Cleaned By",
                "initial": "Unknown",
                "max": 50,
            },
            blocking=True,
        )
        _LOGGER.info(f"Created helper entity: {text_entity_id}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and associated helpers."""
    reminder_name = entry.data.get(CONF_REMINDER_NAME)
    safe_name = reminder_name.lower().replace(" ", "_")
    
    # Remove input_datetime helper
    datetime_entity_id = f"input_datetime.{safe_name}_last_scan"
    if hass.states.get(datetime_entity_id):
        await hass.services.async_call(
            "input_datetime",
            "remove",
            {"entity_id": datetime_entity_id},
            blocking=True,
        )
        _LOGGER.info(f"Removed helper entity: {datetime_entity_id}")
    
    # Remove input_text helper
    text_entity_id = f"input_text.{safe_name}_last_cleaned_by"
    if hass.states.get(text_entity_id):
        await hass.services.async_call(
            "input_text",
            "remove",
            {"entity_id": text_entity_id},
            blocking=True,
        )
        _LOGGER.info(f"Removed helper entity: {text_entity_id}")
    
    # Clean up all created sensors
    entity_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    
    for entity_entry in entries:
        entity_reg.async_remove(entity_entry.entity_id)