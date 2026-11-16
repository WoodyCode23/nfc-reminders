"""Shared fixtures."""
import sys

import pytest

if sys.platform == "win32":
    # The harness blocks sockets, but the Windows event loop needs a loopback pair.
    import pytest_socket

    pytest_socket.disable_socket = lambda *a, **k: None
    pytest_socket.socket_allow_hosts = lambda *a, **k: None

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nfc_reminders.const import (
    CONF_ENTRY_TYPE,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_REMINDER_NAME,
    CONF_TAG_IDS,
    DOMAIN,
    ENTRY_TYPE_REMINDER,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""
    yield


@pytest.fixture(autouse=True)
async def home_time_zone(hass):
    """Ryan's home runs on Eastern time; helper dates are local wall time."""
    await hass.config.async_set_time_zone("America/New_York")


def v1_entry(name, tag_id, interval, unit="days", options=None):
    """A config entry in the version 1 shape."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title=name,
        data={
            "reminder_name": name,
            "nfc_tag_id": tag_id,
            "interval": interval,
            "interval_unit": unit,
        },
        options=options or {},
    )


def v2_entry(name, tag_ids, interval=5, unit="days"):
    """A reminder entry in the version 2 shape."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title=name,
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_REMINDER,
            CONF_REMINDER_NAME: name,
            CONF_TAG_IDS: list(tag_ids),
            CONF_INTERVAL: interval,
            CONF_INTERVAL_UNIT: unit,
        },
    )


async def setup_entries(hass, *entries):
    """Add entries and set the integration up once."""
    for entry in entries:
        entry.add_to_hass(hass)
    if entries:
        await hass.config_entries.async_setup(entries[0].entry_id)
    await hass.async_block_till_done()


# (name, interval in days, helper state in local wall time)
RYAN_HOME = [
    ("Litter Box 1", 5, "2026-09-04 16:40:41"),
    ("Litter Box 2", 5, "2026-09-04 16:40:41"),
    ("Litter Box 3", 5, "2026-09-04 16:40:41"),
    ("Litter Box 4", 5, "2026-09-04 16:40:41"),
    ("Spare Bathroom", 20, "2026-03-07 10:53:17"),
    ("Master Bathroom", 20, "2026-03-07 10:53:17"),
    ("Downstairs Bathroom", 20, "2026-03-07 10:53:42"),
    ("Furnace Filter", 30, "2025-12-28 17:21:43"),
    ("Ryans Teeth", 1, None),
]
