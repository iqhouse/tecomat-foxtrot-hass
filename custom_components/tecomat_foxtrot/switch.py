"""Switch platform for Tecomat Foxtrot."""
import asyncio
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, SOCKET_BASE

RELAY_BASE = "GTSAP1_RELAY"

async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        v_low = var.lower()
        is_socket = v_low.endswith(f"{SOCKET_BASE.lower()}_onoff")
        is_relay = v_low.endswith(f"{RELAY_BASE.lower()}_onoff")
        if not (is_socket or is_relay): continue

        base = var.rsplit("_", 1)[0]
        suffix = "_SOCKET" if is_socket else "_RELAY"
        plc_base = base.rsplit(suffix, 1)[0] if suffix in base.upper() else base
        
        await asyncio.sleep(0.05)
        try:
            name = (await client.async_get(f"{base}_name")).strip() or plc_base
            raw_init = await client.async_get(var)
            initial_state = raw_init.strip() in ("1", "true", "TRUE")
            entities.append(TecomatSwitch(name, client, plc_base, var, initial_state, "relay" if is_relay else "socket", entry.entry_id))
        except: continue

    async_add_entities(entities)

class TecomatSwitch(SwitchEntity):
    def __init__(self, name, client, plc_base, state_var, initial_state, switch_type, entry_id):
        self._attr_name = name
        self._client = client
        self._state_var = state_var
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_{switch_type}"
        self._attr_is_on = initial_state
        self._attr_should_poll = False
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._client.register_value_entity(self._state_var, self._on_diff_value)

    def _on_diff_value(self, raw_value: str) -> None:
        self._attr_is_on = raw_value.strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs): await self._client.async_set(self._state_var, "1")
    async def async_turn_off(self, **kwargs): await self._client.async_set(self._state_var, "0")