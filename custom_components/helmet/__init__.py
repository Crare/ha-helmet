"""Helmet library loans integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HelmetAuthError, HelmetClient, HelmetData, HelmetError
from .const import DOMAIN, UPDATE_INTERVAL, VERSION

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_CARDS_URL = f"/{DOMAIN}/helmet-cards.js"
_CARDS_PATH = Path(__file__).parent / "frontend" / "helmet-cards.js"

type HelmetConfigEntry = ConfigEntry[HelmetCoordinator]


class HelmetCoordinator(DataUpdateCoordinator[HelmetData]):
    """Polls the library site every few hours."""

    def __init__(self, hass: HomeAssistant, entry: HelmetConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = HelmetClient(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    async def _async_update_data(self) -> HelmetData:
        try:
            data = await self.client.fetch()
        except HelmetAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HelmetError as err:
            raise UpdateFailed(str(err)) from err
        if data.loans_total and not data.loans:
            _LOGGER.warning(
                "Helmet reports %s loans but none could be read from the page; "
                "the page layout may have changed",
                data.loans_total,
            )
        if data.holds_ready != sum(hold.ready for hold in data.holds):
            _LOGGER.warning(
                "Helmet reports %s reservations ready for pickup but %s were "
                "recognised on the page; the page layout may have changed",
                data.holds_ready,
                sum(hold.ready for hold in data.holds),
            )
        return data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard cards and load them on every dashboard."""
    if hass.http is not None:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARDS_URL, str(_CARDS_PATH), True)]
        )
        add_extra_js_url(hass, f"{_CARDS_URL}?v={VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HelmetConfigEntry) -> bool:
    coordinator = HelmetCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HelmetConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
