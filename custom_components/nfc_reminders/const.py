"""Constants for NFC Reminders."""

DOMAIN = "nfc_reminders"

CONF_REMINDER_NAME = "reminder_name"
CONF_NFC_TAG_ID = "nfc_tag_id"  # version 1 entries only; version 2 uses CONF_TAG_IDS
CONF_TAG_IDS = "tag_ids"
CONF_INTERVAL = "interval"
CONF_INTERVAL_UNIT = "interval_unit"
CONF_REMIND_AFTER = "remind_after"

CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_REMINDER = "reminder"
ENTRY_TYPE_NOTIFICATIONS = "notifications"
ENTRY_TYPE_GROUP = "group"

CONF_GROUP_NAME = "group_name"
CONF_MEMBERS = "members"

CONF_TIMES = "times"
CONF_TARGETS = "targets"
CONF_NOTIFY_ON_SCAN = "notify_on_scan"
DEFAULT_TIMES = ["09:00", "14:00"]

INTERVAL_UNITS = ["minutes", "hours", "days"]

DEFAULT_INTERVAL = 7
DEFAULT_INTERVAL_UNIT = "days"

# One signal; every entity refreshes when it fires.
SIGNAL_UPDATE = "nfc_reminders_update"

STORAGE_KEY = "nfc_reminders"
STORAGE_VERSION = 1

TAG_URL_PREFIX = "https://www.home-assistant.io/tag/"

EVENT_TAG_SCANNED = "tag_scanned"

NOTIFICATIONS_UNIQUE_ID = "notifications"
NOTIFICATIONS_TITLE = "Notifications"
ISSUE_NO_TARGETS = "no_notify_targets"

TARGET_SERVICE_PREFIX = "service:"
TARGET_ENTITY_PREFIX = "entity:"

SERVICE_MARK_DONE = "mark_done"
SERVICE_CREATE_QR_SHEET = "create_qr_sheet"

QR_SHEET_URL = "/api/nfc_reminders/qr_sheet"
