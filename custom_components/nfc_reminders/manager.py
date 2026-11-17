"""The one place that owns reminders, storage and the tag listener."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EMOJI,
    CONF_GROUP_NAME,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_MEMBERS,
    CONF_REMIND_AFTER,
    CONF_REMINDER_NAME,
    CONF_SLUG,
    CONF_TAG_IDS,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DOMAIN,
    EVENT_TAG_SCANNED,
    SIGNAL_UPDATE,
)
from .reminder import Group, Reminder
from .store import ReminderStore
from .who import async_resolve_device

_LOGGER = logging.getLogger(__name__)

_NO_NAME = ("", "unknown", "unavailable")

# (reminders marked, who did it, the group's name when a group did it)
DoneHook = Callable[[list[Reminder], str | None, str | None], Awaitable[None]]


def get_manager(hass: HomeAssistant) -> Manager:
    return hass.data[DOMAIN]


class Manager:
    """Reminders and groups by entry id, one tag listener, one refresh a minute."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.reminders: dict[str, Reminder] = {}
        self.groups: dict[str, Group] = {}
        self.notify_settings: dict | None = None
        self.on_done: DoneHook | None = None
        self._store = ReminderStore(hass)
        self._loaded = False
        self._unsubs: list[CALLBACK_TYPE] = []
        self._import_retries: dict[str, CALLBACK_TYPE] = {}

    async def async_start(self) -> None:
        """Load the store once and start listening. Safe to call again."""
        if not self._loaded:
            await self._store.async_load()
            self._loaded = True
        if not self._unsubs:
            self._unsubs = [
                self.hass.bus.async_listen(EVENT_TAG_SCANNED, self._handle_tag_scanned),
                async_track_time_change(self.hass, self._handle_tick, second=0),
            ]

    @callback
    def async_stop(self) -> None:
        """Stop listening. Reminders and stored data are kept."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    async def async_add_reminder(self, entry: ConfigEntry) -> Reminder:
        """Build a reminder from its entry and stored state."""
        await self.async_start()
        data = entry.data
        reminder = Reminder(
            entry_id=entry.entry_id,
            name=data[CONF_REMINDER_NAME],
            tag_ids=list(data.get(CONF_TAG_IDS, [])),
            interval=int(data.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
            unit=data.get(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT),
            remind_after=data.get(CONF_REMIND_AFTER) or None,
            slug=data.get(CONF_SLUG) or "",
            emoji=data.get(CONF_EMOJI) or "",
        )
        record = self._store.get(entry.entry_id)
        if record is not None:
            if record.get("last_done"):
                reminder.last_done = dt_util.parse_datetime(record["last_done"])
            reminder.last_done_by = record.get("last_done_by")
        self.reminders[entry.entry_id] = reminder
        if record is None:
            await self._async_import_helpers(reminder)
        # Groups that hold this reminder refresh their status.
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        return reminder

    async def async_add_group(self, entry: ConfigEntry) -> Group:
        """Build a group from its entry. Groups store nothing of their own."""
        await self.async_start()
        group = Group(
            entry_id=entry.entry_id,
            name=entry.data[CONF_GROUP_NAME],
            member_ids=list(entry.data.get(CONF_MEMBERS, [])),
            tag_ids=list(entry.data.get(CONF_TAG_IDS, [])),
        )
        self.groups[entry.entry_id] = group
        return group

    @callback
    def async_remove_group(self, entry_id: str) -> None:
        self.groups.pop(entry_id, None)
        self._stop_if_idle()

    def members_of(self, group_id: str) -> list[Reminder]:
        group = self.groups.get(group_id)
        return group.members(self.reminders) if group else []

    def entry_ids_for_tag(self, tag_id: str) -> list[str]:
        """Every reminder a tag marks: its own, plus all members of its groups."""
        found: list[str] = [
            entry_id
            for entry_id, reminder in self.reminders.items()
            if tag_id in reminder.tag_ids
        ]
        for group in self.groups.values():
            if tag_id in group.tag_ids:
                found.extend(r.entry_id for r in group.members(self.reminders))
        return list(dict.fromkeys(found))

    @callback
    def _stop_if_idle(self) -> None:
        if not self.reminders and not self.groups and self.notify_settings is None:
            self.async_stop()

    async def async_remove_reminder(self, entry_id: str, *, forget: bool) -> None:
        """Drop a reminder. With forget, its stored state goes too."""
        self.reminders.pop(entry_id, None)
        retry = self._import_retries.pop(entry_id, None)
        if retry is not None:
            retry()
        if forget:
            if not self._loaded:
                await self._store.async_load()
                self._loaded = True
            await self._store.async_remove(entry_id)
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        self._stop_if_idle()

    async def async_mark_done(
        self,
        entry_ids: list[str],
        *,
        by: str | None,
        when: datetime | None = None,
        label: str | None = None,
    ) -> None:
        """Mark reminders done now (or at `when`), save, and tell everyone.

        label names the group when a group's tag or button did it; it only shapes the message.
        """
        when = dt_util.as_utc(when) if when else dt_util.utcnow()
        done: list[Reminder] = []
        for entry_id in entry_ids:
            reminder = self.reminders.get(entry_id)
            if reminder is None:
                continue
            reminder.last_done = when
            reminder.last_done_by = by
            self._store.set(entry_id, last_done=when, last_done_by=by)
            done.append(reminder)
        if not done:
            return
        await self._store.async_save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        if self.on_done is not None:
            try:
                await self.on_done(done, by, label)
            except Exception:  # noqa: BLE001 - a failed message must not undo the scan
                _LOGGER.exception("Could not send the scan notification")

    @callback
    def _handle_tag_scanned(self, event: Event) -> None:
        tag_id = event.data.get("tag_id")
        if not tag_id:
            return
        entry_ids = self.entry_ids_for_tag(tag_id)
        if not entry_ids:
            return
        # A scan of a group's own tag is announced under the group's name.
        label = next((g.name for g in self.groups.values() if tag_id in g.tag_ids), None)
        self.hass.async_create_task(
            self._async_scan(entry_ids, event.data.get("device_id"), label)
        )

    async def _async_scan(
        self, entry_ids: list[str], device_id: str | None, label: str | None = None
    ) -> None:
        by = await async_resolve_device(self.hass, device_id)
        await self.async_mark_done(entry_ids, by=by, label=label)

    @callback
    def _handle_tick(self, now: datetime) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def _async_import_helpers(
        self, reminder: Reminder, *, may_retry: bool = True
    ) -> None:
        """Carry over the version 1 helpers once. They are only read, never written."""
        slug = reminder.slug  # helpers were named after the original name
        date_state = self.hass.states.get(f"input_datetime.{slug}_last_scan")

        if (
            date_state is None
            and may_retry
            and self.hass.state is not CoreState.running
        ):
            # Helpers may not be loaded yet during startup; look once more when it is.
            entry_id = reminder.entry_id

            async def _retry(_event: Event) -> None:
                self._import_retries.pop(entry_id, None)
                current = self.reminders.get(entry_id)
                if current is None or self._store.get(entry_id) is not None:
                    return
                await self._async_import_helpers(current, may_retry=False)
                async_dispatcher_send(self.hass, SIGNAL_UPDATE)

            self._import_retries[entry_id] = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, _retry
            )
            return

        last_done = None
        if date_state is not None:
            parsed = dt_util.parse_datetime(date_state.state)
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
                last_done = dt_util.as_utc(parsed)

        by = None
        by_state = self.hass.states.get(f"input_text.{slug}_last_cleaned_by")
        if by_state is not None and by_state.state.strip().lower() not in _NO_NAME:
            by = by_state.state.strip()

        if last_done is not None:
            reminder.last_done = last_done
            reminder.last_done_by = by
        await self._store.async_set(
            reminder.entry_id,
            last_done=reminder.last_done,
            last_done_by=reminder.last_done_by,
        )
