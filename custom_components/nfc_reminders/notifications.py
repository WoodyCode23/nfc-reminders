"""The overdue overview, the scan message, and the Notifications entry."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NOTIFY_ON_SCAN,
    CONF_TARGETS,
    CONF_TIMES,
    DEFAULT_TIMES,
    DOMAIN,
    ISSUE_NO_TARGETS,
    TARGET_ENTITY_PREFIX,
    TARGET_SERVICE_PREFIX,
)
from .reminder import Reminder, parse_time

_LOGGER = logging.getLogger(__name__)

OVERDUE_MARK = "\U0001F534"  # red circle
SOON_MARK = "\U0001F7E1"  # yellow circle
DONE_MARK = "✅"  # green check


def _things(count: int, what: str) -> str:
    return f"1 thing {what}" if count == 1 else f"{count} things {what}"


def build_overview(
    reminders: Iterable[Reminder], now: datetime
) -> tuple[str, str] | None:
    """Overdue chores (most overdue first), then due-soon ones (soonest first).

    A chore is due soon only when it has a remind_after and is past it. None when there is nothing.
    """
    reminders = list(reminders)
    overdue = sorted(
        (r for r in reminders if r.is_overdue(now)), key=lambda r: r.ratio(now), reverse=True
    )
    soon = sorted((r for r in reminders if r.is_due_soon(now)), key=lambda r: r.next_due)
    if not overdue and not soon:
        return None
    if overdue and soon:
        title = f"{OVERDUE_MARK} {len(overdue)} overdue, {SOON_MARK} {len(soon)} due soon"
    elif overdue:
        title = f"{OVERDUE_MARK} {_things(len(overdue), 'overdue')}"
    else:
        title = f"{SOON_MARK} {_things(len(soon), 'due soon')}"
    # Each line leads with the reminder's own emoji, or a red or yellow dot when it has none.
    lines = [f"{r.emoji or OVERDUE_MARK} {r.overview_line(now)}" for r in overdue]
    lines += [f"{r.emoji or SOON_MARK} {r.due_soon_line(now)}" for r in soon]
    return title, "\n".join(lines)


def _clock(when: datetime) -> str:
    """Local time like "2:05 PM"."""
    return dt_util.as_local(when).strftime("%I:%M %p").lstrip("0")


def build_scan_message(
    done: list[Reminder], by: str | None, when: datetime, label: str | None = None
) -> tuple[str, str]:
    """One message for one scan, however many reminders it marked.

    label is the group's name when a group's tag or button did it.
    """
    if label:
        title = f"{DONE_MARK} {label} done"
    elif len(done) == 1:
        title = f"{DONE_MARK} {done[0].name} done"
    else:
        title = f"{DONE_MARK} {len(done)} things done"
    names = ", ".join(r.label for r in done)
    return title, f"{names}\nMarked done by {by or 'someone'} at {_clock(when)}"


async def async_send(
    hass: HomeAssistant, targets: list[str], title: str, message: str
) -> None:
    """Send to every target. One broken target never blocks the others."""
    for target in targets:
        try:
            if target.startswith(TARGET_ENTITY_PREFIX):
                await hass.services.async_call(
                    "notify",
                    "send_message",
                    {
                        "entity_id": target[len(TARGET_ENTITY_PREFIX):],
                        "title": title,
                        "message": message,
                    },
                    blocking=True,
                )
            else:
                service = target.removeprefix(TARGET_SERVICE_PREFIX)
                await hass.services.async_call(
                    "notify",
                    service,
                    {"title": title, "message": message},
                    blocking=True,
                )
        except Exception as err:  # noqa: BLE001 - keep going for the other targets
            _LOGGER.warning("Could not notify %s: %s", target, err)


def async_schedule(hass: HomeAssistant, manager, options: dict) -> Callable[[], None]:
    """Send the overview at each configured time. Returns an unsubscribe."""
    targets = list(options.get(CONF_TARGETS, []))

    async def _send_overview(_now: datetime) -> None:
        overview = build_overview(manager.reminders.values(), dt_util.utcnow())
        if overview is None or not targets:
            return
        await async_send(hass, targets, *overview)

    unsubs = []
    for text in options.get(CONF_TIMES, DEFAULT_TIMES):
        try:
            when = parse_time(text)
        except ValueError:
            _LOGGER.warning("Ignoring a notification time that is not a time: %s", text)
            continue
        unsubs.append(
            async_track_time_change(
                hass, _send_overview, hour=when.hour, minute=when.minute, second=0
            )
        )

    @callback
    def _unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    return _unsubscribe


@callback
def _async_update_issue(hass: HomeAssistant, targets: list[str]) -> None:
    if targets:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_NO_TARGETS)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_NO_TARGETS,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NO_TARGETS,
    )


@callback
def async_setup_notifications(hass: HomeAssistant, manager, entry: ConfigEntry) -> None:
    """Apply the Notifications entry: schedule, scan message, repair issue."""
    options = {
        CONF_TIMES: list(entry.options.get(CONF_TIMES, DEFAULT_TIMES)),
        CONF_TARGETS: list(entry.options.get(CONF_TARGETS, [])),
        CONF_NOTIFY_ON_SCAN: bool(entry.options.get(CONF_NOTIFY_ON_SCAN, False)),
    }
    manager.notify_settings = options
    targets = options[CONF_TARGETS]

    unschedule = async_schedule(hass, manager, options)

    if options[CONF_NOTIFY_ON_SCAN]:

        async def _on_done(
            done: list[Reminder], by: str | None, label: str | None = None
        ) -> None:
            if targets:
                when = done[0].last_done or dt_util.utcnow()
                await async_send(
                    hass, targets, *build_scan_message(done, by, when, label)
                )

        manager.on_done = _on_done
    else:
        manager.on_done = None

    _async_update_issue(hass, targets)

    @callback
    def _teardown() -> None:
        unschedule()
        manager.on_done = None
        manager.notify_settings = None

    entry.async_on_unload(_teardown)
