"""Config flow for Spa Client integration."""
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

# Import the device class from the component that you want to support
from .const import (
    _LOGGER,
    CONF_SYNC_TIME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .spaclient import spaclient
from homeassistant import config_entries, core, exceptions
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_NAME, default="Spa Client"): str,
    }
)


@callback
def configured_instances(hass):
    """Return a set of configured Spa Client instances."""

    return {entry.title for entry in hass.config_entries.async_entries(DOMAIN)}


class SpaClientConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Spa Client."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        return await self.async_step_user(import_config)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input:
            try:
                await validate_input(self.hass, user_input)
                return self.async_create_entry(title="", data=user_input)
            except AlreadyConfigured:
                return self.async_abort(reason="already_configured")
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Spa Client."""

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL)),
                vol.Optional(CONF_SYNC_TIME, default=self.config_entry.options.get(CONF_SYNC_TIME, False),): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


async def validate_input(hass, data):
    """Validate the user input allows us to connect."""

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data[CONF_HOST] == data[CONF_HOST]:
            raise AlreadyConfigured

    spa = spaclient(data[CONF_HOST])

    try:
        connected = await spa.validate_connection()
    finally:
        await spa.close()

    if not connected:                                                    #To switch to development mode, comment out this line
        raise CannotConnect                                              #To switch to development mode, comment out this line


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class AlreadyConfigured(exceptions.HomeAssistantError):
    """Error to indicate this device is already configured."""
