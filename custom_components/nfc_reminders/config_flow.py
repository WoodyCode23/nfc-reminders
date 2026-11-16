"""Config flow for NFC Reminders."""
from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENTRY_TYPE,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_NOTIFY_ON_SCAN,
    CONF_REMINDER_NAME,
    CONF_TAG_IDS,
    CONF_TARGETS,
    CONF_TIMES,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_TIMES,
    DOMAIN,
    ENTRY_TYPE_NOTIFICATIONS,
    ENTRY_TYPE_REMINDER,
    EVENT_TAG_SCANNED,
    INTERVAL_UNITS,
    NOTIFICATIONS_TITLE,
    NOTIFICATIONS_UNIQUE_ID,
    TARGET_ENTITY_PREFIX,
    TARGET_SERVICE_PREFIX,
)
from .reminder import parse_time, safe_name

CONF_TAG_ID = "tag_id"

_INTERVAL = vol.All(vol.Coerce(int), vol.Range(min=1))
_UNIT_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=INTERVAL_UNITS,
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="interval_unit",
    )
)


def _known_tags(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Tags Home Assistant already knows, as dropdown options."""
    options = []
    for state in hass.states.async_all("tag"):
        tag_id = state.attributes.get("tag_id")
        if tag_id:
            options.append(selector.SelectOptionDict(value=tag_id, label=state.name))
    return sorted(options, key=lambda o: o["label"].lower())


def _tag_selector(
    hass: HomeAssistant, *, multiple: bool, extra: list[str] | None = None
) -> selector.SelectSelector:
    options = _known_tags(hass)
    known = {o["value"] for o in options}
    for tag_id in extra or []:
        if tag_id not in known:
            options.append(selector.SelectOptionDict(value=tag_id, label=tag_id))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=multiple,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _notify_targets(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Everything that can receive a notification: notify services and notify entities."""
    options = []
    for service in sorted(hass.services.async_services().get("notify", {})):
        if service == "send_message":
            continue
        options.append(
            selector.SelectOptionDict(
                value=f"{TARGET_SERVICE_PREFIX}{service}", label=f"notify.{service}"
            )
        )
    for state in sorted(hass.states.async_all("notify"), key=lambda s: s.entity_id):
        options.append(
            selector.SelectOptionDict(
                value=f"{TARGET_ENTITY_PREFIX}{state.entity_id}",
                label=f"{state.name} ({state.entity_id})",
            )
        )
    return options


class NFCRemindersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a reminder: name and interval, then how to get its tag."""

    VERSION = 2

    def __init__(self) -> None:
        self._reminder: dict[str, Any] = {}
        self._scanned_tag: str | None = None
        self._unsub_scan: CALLBACK_TYPE | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_REMINDER_NAME].strip()
            slug = safe_name(name)
            taken = any(
                safe_name(entry.data.get(CONF_REMINDER_NAME, "")) == slug
                for entry in self._async_current_entries()
                if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_NOTIFICATIONS
            )
            if not name or taken:
                errors["base"] = "name_exists" if taken else "name_required"
            else:
                self._reminder = {
                    CONF_REMINDER_NAME: name,
                    CONF_INTERVAL: user_input[CONF_INTERVAL],
                    CONF_INTERVAL_UNIT: user_input[CONF_INTERVAL_UNIT],
                }
                return await self.async_step_tag()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMINDER_NAME): str,
                    vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): _INTERVAL,
                    vol.Required(
                        CONF_INTERVAL_UNIT, default=DEFAULT_INTERVAL_UNIT
                    ): _UNIT_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_tag(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="tag", menu_options=["scan", "existing", "new_qr"]
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for the next tag scan."""
        if self._unsub_scan is None:

            @callback
            def _scanned(event: Event) -> None:
                tag_id = event.data.get("tag_id")
                if tag_id:
                    self._scanned_tag = tag_id

            self._unsub_scan = self.hass.bus.async_listen(EVENT_TAG_SCANNED, _scanned)

        errors: dict[str, str] = {}
        if user_input is not None:
            if self._scanned_tag:
                return self._create(self._scanned_tag)
            errors["base"] = "no_scan"
        return self.async_show_form(
            step_id="scan", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_existing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a tag Home Assistant already knows, or type an id."""
        errors: dict[str, str] = {}
        if user_input is not None:
            tag_id = str(user_input.get(CONF_TAG_ID, "")).strip()
            if tag_id:
                return self._create(tag_id)
            errors["base"] = "tag_required"
        return self.async_show_form(
            step_id="existing",
            data_schema=vol.Schema(
                {vol.Required(CONF_TAG_ID): _tag_selector(self.hass, multiple=False)}
            ),
            errors=errors,
        )

    async def async_step_new_qr(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A new tag that only exists as a QR code."""
        return self._create(str(uuid.uuid4()))

    async def async_step_import(
        self, import_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the one Notifications entry (started by the integration itself)."""
        await self.async_set_unique_id(NOTIFICATIONS_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=NOTIFICATIONS_TITLE,
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_NOTIFICATIONS},
            options={
                CONF_TIMES: list(DEFAULT_TIMES),
                CONF_TARGETS: [],
                CONF_NOTIFY_ON_SCAN: False,
            },
        )

    def _create(self, tag_id: str) -> ConfigFlowResult:
        self._stop_listening()
        return self.async_create_entry(
            title=self._reminder[CONF_REMINDER_NAME],
            data={
                CONF_ENTRY_TYPE: ENTRY_TYPE_REMINDER,
                **self._reminder,
                CONF_TAG_IDS: [tag_id],
            },
        )

    @callback
    def _stop_listening(self) -> None:
        if self._unsub_scan is not None:
            self._unsub_scan()
            self._unsub_scan = None

    @callback
    def async_remove(self) -> None:
        """The flow ended or was closed."""
        self._stop_listening()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_NOTIFICATIONS:
            return NotificationsOptionsFlow()
        return ReminderOptionsFlow()


class ReminderOptionsFlow(OptionsFlow):
    """Change a reminder's interval and tags. Takes effect straight away."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        current_tags = list(entry.data.get(CONF_TAG_IDS, []))
        errors: dict[str, str] = {}

        if user_input is not None:
            tags: list[str] = []
            for tag_id in user_input.get(CONF_TAG_IDS, []):
                tag_id = str(tag_id).strip()
                if tag_id and tag_id not in tags:
                    tags.append(tag_id)
            if not tags:
                errors["base"] = "tag_required"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_INTERVAL: user_input[CONF_INTERVAL],
                        CONF_INTERVAL_UNIT: user_input[CONF_INTERVAL_UNIT],
                        CONF_TAG_IDS: tags,
                    },
                )
                return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERVAL,
                        default=entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                    ): _INTERVAL,
                    vol.Required(
                        CONF_INTERVAL_UNIT,
                        default=entry.data.get(
                            CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT
                        ),
                    ): _UNIT_SELECTOR,
                    vol.Required(CONF_TAG_IDS, default=current_tags): _tag_selector(
                        self.hass, multiple=True, extra=current_tags
                    ),
                }
            ),
            errors=errors,
        )


class NotificationsOptionsFlow(OptionsFlow):
    """When the overdue overview goes out and who gets it."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = self.config_entry.options
        current_times = list(options.get(CONF_TIMES, DEFAULT_TIMES))
        current_targets = list(options.get(CONF_TARGETS, []))
        errors: dict[str, str] = {}

        if user_input is not None:
            times: set[str] = set()
            try:
                for part in str(user_input.get(CONF_TIMES, "")).split(","):
                    if part.strip():
                        times.add(parse_time(part).strftime("%H:%M"))
            except ValueError:
                errors[CONF_TIMES] = "invalid_time"
            else:
                if not times:
                    errors[CONF_TIMES] = "invalid_time"
            if not errors:
                return self.async_create_entry(
                    data={
                        CONF_TIMES: sorted(times),
                        CONF_TARGETS: list(user_input.get(CONF_TARGETS, [])),
                        CONF_NOTIFY_ON_SCAN: bool(
                            user_input.get(CONF_NOTIFY_ON_SCAN, False)
                        ),
                    }
                )

        target_options = _notify_targets(self.hass)
        listed = {o["value"] for o in target_options}
        for target in current_targets:
            if target not in listed:
                # Keep a target that has gone missing visible, so it can be removed.
                target_options.append(
                    selector.SelectOptionDict(value=target, label=target)
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TIMES, default=", ".join(current_times)): str,
                    vol.Optional(
                        CONF_TARGETS, default=current_targets
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=target_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_NOTIFY_ON_SCAN,
                        default=bool(options.get(CONF_NOTIFY_ON_SCAN, False)),
                    ): bool,
                }
            ),
            errors=errors,
        )
