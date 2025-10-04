"""Config flow for NFC Reminders."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_REMINDER_NAME,
    CONF_NFC_TAG_ID,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    INTERVAL_UNITS,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
)

_LOGGER = logging.getLogger(__name__)


class NFCRemindersConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NFC Reminders."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate the input
            reminder_name = user_input[CONF_REMINDER_NAME]
            nfc_tag_id = user_input[CONF_NFC_TAG_ID]
            
            # Check for duplicate names
            existing_entries = self._async_current_entries()
            for entry in existing_entries:
                if entry.data.get(CONF_REMINDER_NAME) == reminder_name:
                    errors["base"] = "name_exists"
                    break
            
            if not errors:
                # Create the config entry
                return self.async_create_entry(
                    title=reminder_name,
                    data=user_input
                )

        data_schema = vol.Schema({
            vol.Required(CONF_REMINDER_NAME): cv.string,
            vol.Required(CONF_NFC_TAG_ID): cv.string,
            vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Required(CONF_INTERVAL_UNIT, default=DEFAULT_INTERVAL_UNIT): vol.In(
                INTERVAL_UNITS
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return NFCRemindersOptionsFlow(config_entry)


class NFCRemindersOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for NFC Reminders."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_INTERVAL,
                    default=self.config_entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(
                    CONF_INTERVAL_UNIT,
                    default=self.config_entry.data.get(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT)
                ): vol.In(INTERVAL_UNITS),
            })
        )