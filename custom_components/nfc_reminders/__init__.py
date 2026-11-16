"""NFC Reminders: scan a tag or a QR code when a chore is done, get told when it is overdue."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ENTRY_TYPE,
    CONF_NFC_TAG_ID,
    CONF_TAG_IDS,
    DOMAIN,
    ENTRY_TYPE_NOTIFICATIONS,
    ENTRY_TYPE_REMINDER,
    SERVICE_CREATE_QR_SHEET,
    SERVICE_MARK_DONE,
)
from .manager import Manager, get_manager
from .notifications import async_setup_notifications
from .qr import QrSheetView, async_announce_sheet
from .who import async_resolve_user

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button", "image"]
NOTIFICATION_PLATFORMS = ["button"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

MARK_DONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("when"): cv.datetime,
    }
)


def _is_notifications(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_NOTIFICATIONS


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create the manager, the services and the QR sheet page."""
    manager = Manager(hass)
    hass.data[DOMAIN] = manager

    async def _mark_done(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        entry_ids: list[str] = []
        for entity_id in call.data[ATTR_ENTITY_ID]:
            entity = registry.async_get(entity_id)
            if (
                entity is None
                or entity.platform != DOMAIN
                or entity.config_entry_id not in manager.reminders
            ):
                raise ServiceValidationError(
                    f"{entity_id} does not belong to an NFC reminder"
                )
            if entity.config_entry_id not in entry_ids:
                entry_ids.append(entity.config_entry_id)
        by = await async_resolve_user(hass, call.context.user_id)
        await manager.async_mark_done(entry_ids, by=by, when=call.data.get("when"))

    async def _create_qr_sheet(call: ServiceCall) -> ServiceResponse:
        link = async_announce_sheet(hass)
        return {"url": link} if call.return_response else None

    hass.services.async_register(
        DOMAIN, SERVICE_MARK_DONE, _mark_done, schema=MARK_DONE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_QR_SHEET,
        _create_qr_sheet,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.http.register_view(QrSheetView())

    if not any(_is_notifications(e) for e in hass.config_entries.async_entries(DOMAIN)):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 had one tag per reminder; version 2 has a list."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = dict(entry.data)
        tag_id = data.pop(CONF_NFC_TAG_ID, None)
        data[CONF_TAG_IDS] = [tag_id] if tag_id else []
        data[CONF_ENTRY_TYPE] = ENTRY_TYPE_REMINDER
        # Version 1 saved interval edits into options but never read them; data wins.
        hass.config_entries.async_update_entry(entry, data=data, options={}, version=2)
        _LOGGER.info("Migrated reminder %s to version 2", entry.title)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = get_manager(hass)
    if _is_notifications(entry):
        await manager.async_start()
        async_setup_notifications(hass, manager, entry)
        platforms = NOTIFICATION_PLATFORMS
    else:
        await manager.async_add_reminder(entry)
        platforms = PLATFORMS
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = get_manager(hass)
    if _is_notifications(entry):
        unloaded = await hass.config_entries.async_unload_platforms(
            entry, NOTIFICATION_PLATFORMS
        )
        if unloaded and not manager.reminders:
            # on_unload callbacks (which clear notify_settings) run after this returns.
            manager.async_stop()
        return unloaded
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await manager.async_remove_reminder(entry.entry_id, forget=False)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget the stored state of a deleted reminder."""
    if _is_notifications(entry) or DOMAIN not in hass.data:
        return
    await get_manager(hass).async_remove_reminder(entry.entry_id, forget=True)
