"""Work out who did it, from the scanning device or the logged-in user."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


async def async_resolve_user(hass: HomeAssistant, user_id: str | None) -> str | None:
    """Person name for a user id, else the user's own name, else None."""
    if not user_id:
        return None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.name
    user = await hass.auth.async_get_user(user_id)
    if user is not None and user.name:
        return user.name
    return None


async def async_resolve_device(hass: HomeAssistant, device_id: str | None) -> str | None:
    """Person behind a scanning phone, else the phone's name, else None."""
    if not device_id:
        return None
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "mobile_app":
            continue
        name = await async_resolve_user(hass, entry.data.get("user_id"))
        if name:
            return name
    return device.name_by_user or device.name or None
