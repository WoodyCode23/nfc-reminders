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

SCAN_TITLE = "NFC Reminders"


def build_overview(
    reminders: Iterable[Reminder], now: datetime
) -> tuple[str, str] | None:
    """Title and body of the overview, most overdue first. None when nothing is overdue."""
    overdue = [r for r in reminders if r.is_overdue(now)]
    if not overdue:
        return None
    overdue.sort(key=lambda r: r.ratio(now), reverse=True)
    count = len(overdue)
    title = "1 thing overdue" if count == 1 else f"{count} things overdue"
    return title, "\n".join(r.overview_line(now) for r in overdue)


def build_scan_message(names: list[str], by: str | None) -> tuple[str, str]:
    """One message for one scan, however many reminders it marked."""
    return SCAN_TITLE, f"{by or 'Someone'} marked {', '.join(names)} done"


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

        async def _on_done(done: list[Reminder], by: str | None) -> None:
            if targets:
                await async_send(
                    hass, targets, *build_scan_message([r.name for r in done], by)
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
