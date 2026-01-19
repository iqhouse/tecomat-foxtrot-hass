"""Config flow for Tecomat Foxtrot."""

import asyncio
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_PORT
from .plccoms import PLCComSClient


class TecomatFoxtrotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            # Validate connection with timeout to avoid UI hang.
            client = PLCComSClient(self.hass, host, port)
            try:
                await asyncio.wait_for(client.async_connect(list_only=True), timeout=5)
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                try:
                    await client.async_disconnect()
                except Exception:
                    pass

            if not errors:
                return self.async_create_entry(
                    title=f"Tecomat Foxtrot ({host})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)