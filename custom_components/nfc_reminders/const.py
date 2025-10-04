"""Constants for NFC Reminders."""

DOMAIN = "nfc_reminders"

CONF_REMINDER_NAME = "reminder_name"
CONF_NFC_TAG_ID = "nfc_tag_id"
CONF_INTERVAL = "interval"
CONF_INTERVAL_UNIT = "interval_unit"

INTERVAL_UNITS = ["minutes", "hours", "days"]

DEFAULT_INTERVAL = 7
DEFAULT_INTERVAL_UNIT = "days"