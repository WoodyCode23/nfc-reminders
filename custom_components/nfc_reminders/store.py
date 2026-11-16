"""Persistent last-done data, kept in Home Assistant's own storage."""
from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class ReminderStore:
    """Last-done time and who did it, keyed by config entry id."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, dict] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        reminders = (data or {}).get("reminders")
        self._data = reminders if isinstance(reminders, dict) else {}

    def get(self, entry_id: str) -> dict | None:
        """Return {"last_done": iso str | None, "last_done_by": str | None, "imported": bool}."""
        return self._data.get(entry_id)

    def set(
        self,
        entry_id: str,
        *,
        last_done: datetime | None,
        last_done_by: str | None,
        imported: bool = True,
    ) -> None:
        """Update one record in memory. Call async_save afterwards."""
        self._data[entry_id] = {
            "last_done": last_done.isoformat() if last_done else None,
            "last_done_by": last_done_by,
            "imported": imported,
        }

    async def async_save(self) -> None:
        await self._store.async_save({"reminders": self._data})

    async def async_set(
        self,
        entry_id: str,
        *,
        last_done: datetime | None,
        last_done_by: str | None,
        imported: bool = True,
    ) -> None:
        self.set(
            entry_id, last_done=last_done, last_done_by=last_done_by, imported=imported
        )
        await self.async_save()

    async def async_remove(self, entry_id: str) -> None:
        if self._data.pop(entry_id, None) is not None:
            await self.async_save()
