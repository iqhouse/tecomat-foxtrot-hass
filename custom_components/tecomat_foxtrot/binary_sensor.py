"""Binary sensor platform for Tecomat Foxtrot."""
import asyncio
from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN, CONTACT_BASE

async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        if not var.lower().endswith(f"{CONTACT_BASE.lower()}_state"):
            continue

        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit("_CONTACT", 1)[0] if "_CONTACT" in base.upper() else base
        
        await asyncio.sleep(0.05)
        try:
            name = (await client.async_get(f"{base}_name")).strip() or plc_base
            raw_init = await client.async_get(var)
            initial_state = raw_init.strip() in ("1", "true", "TRUE")
            entities.append(TecomatBinarySensor(name, client, plc_base, var, initial_state, entry.entry_id))
        except: continue

    async_add_entities(entities)

class TecomatBinarySensor(BinarySensorEntity):
    def __init__(self, name, client, plc_base, state_var, initial_state, entry_id):
        self._attr_name = name
        self._client = client
        self._state_var = state_var
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_state"
        self._attr_is_on = initial_state
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._client.register_value_entity(self._state_var, self._on_diff_value)

    def _on_diff_value(self, raw_value: str) -> None:
        self._attr_is_on = raw_value.strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._state_var)