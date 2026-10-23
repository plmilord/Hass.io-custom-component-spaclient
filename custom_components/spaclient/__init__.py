"""Init file for Spa Client integration."""
import asyncio
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

# Import the device class from the component that you want to support
from .const import (
    _LOGGER,
    CONF_SYNC_TIME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ICONS,
    MIN_SCAN_INTERVAL,
    SPA,
    SPACLIENT_COMPONENTS,
)
from .spaclient import spaclient
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL)),
                vol.Optional(CONF_SYNC_TIME, default=False): bool,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, base_config):
    """Configure the Spa Client component using flow only."""

    hass.data.setdefault(DOMAIN, {})

    if DOMAIN in base_config:
        for entry in base_config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=entry
                )
            )
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Spa Client from a config entry."""

    spa = spaclient(config_entry.data[CONF_HOST])
    data = {SPA: spa, "tasks": [], "sync_time_task": None}
    hass.data[DOMAIN][config_entry.entry_id] = data

    try:
        if not await spa.validate_connection():
            raise ConfigEntryNotReady("Unable to connect to the spa")

        await spa.send_additional_information_request()
        await spa.send_configuration_request()
        await spa.send_fault_log_request()
        await spa.send_filter_cycles_request()
        await spa.send_gfci_test_request()
        await spa.send_information_request()
        await spa.send_module_identification_request()
        await spa.send_preferences_request()

        data["tasks"] = [
            hass.async_create_background_task(spa.keep_alive_call(), "spaclient keep alive"),
            hass.async_create_background_task(spa.read_all_msg(), "spaclient reader"),
        ]
        await update_listener(hass, config_entry)
        await hass.config_entries.async_forward_entry_setups(config_entry, SPACLIENT_COMPONENTS)
    except (OSError, TimeoutError) as err:
        await _async_close(data)
        hass.data[DOMAIN].pop(config_entry.entry_id)
        raise ConfigEntryNotReady("Spa did not respond during setup") from err
    except BaseException:
        await _async_close(data)
        hass.data[DOMAIN].pop(config_entry.entry_id)
        raise

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    async def async_stop(event):
        await _async_close(data)

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    )

    spa.print_variables()
    return True


async def async_unload_entry(hass, config_entry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(config_entry, SPACLIENT_COMPONENTS):
        data = hass.data[DOMAIN].pop(config_entry.entry_id)
        await _async_close(data)
    return unload_ok


async def _async_close(data):
    """Stop all readers and timers before closing the spa connection."""
    tasks = list(data["tasks"])
    if data["sync_time_task"] is not None:
        tasks.append(data["sync_time_task"])
    data["tasks"] = []
    data["sync_time_task"] = None
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await data[SPA].close()


async def update_listener(hass, config_entry):
    """Handle options update."""

    data = hass.data[DOMAIN][config_entry.entry_id]
    if task := data["sync_time_task"]:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        data["sync_time_task"] = None

    if config_entry.options.get(CONF_SYNC_TIME):
        spa = data[SPA]

        async def sync_time():
            while config_entry.options.get(CONF_SYNC_TIME):
                if spa.get_gateway_status():
                    try:
                        await spa.set_current_time()
                    except OSError:
                        _LOGGER.debug("Spa disconnected during time sync")
                await asyncio.sleep(86400)

        data["sync_time_task"] = hass.async_create_background_task(
            sync_time(), "spaclient time sync"
        )


class SpaClientDevice(Entity):
    """Representation of a Spa Client device."""

    def __init__(self, spaclient, config_entry):
        """Initialize the Spa Client device."""
        self._device_name = config_entry.data[CONF_NAME]
        self._spaclient = spaclient

    async def async_added_to_hass(self):
        """Register state update callback."""

    @property
    def should_poll(self) -> bool:
        """Home Assistant will poll an entity when the should_poll property returns True."""
        return True

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"{self._spaclient.get_macaddr().replace(':', '')}#spa_client"

    @property
    def device_info(self):
        """Return the device information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._spaclient.get_macaddr().replace(':', ''))},
            "model": self._spaclient.get_model_name(),
            "manufacturer": "Balboa Water Group",
            "name": self._device_name,
            "sw_version": self._spaclient.get_ssid(),
        }
