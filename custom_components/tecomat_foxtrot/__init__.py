from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .plccoms import PLCComSClient

from . import sensor, binary_sensor, switch, light, cover, climate, event


async def _async_reload_platforms(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
    Platform.CLIMATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = PLCComSClient(hass, entry.data[CONF_HOST], entry.data[CONF_PORT])
    await client.async_connect()

    entry_data = {"client": client}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry_data

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Tecomat Foxtrot ({entry.data[CONF_HOST]})",
        manufacturer="Teco a.s.",
        model="Foxtrot CP-xxxx",
    )

    # ---------- Prefetch ----------
    # uprav podľa výkonu PLC / siete
    BATCH = 250

    platform_vars = {
        "sensor": sensor.get_required_var_names(client),
        "binary_sensor": binary_sensor.get_required_var_names(client),
        "switch": switch.get_required_var_names(client),
        "light": light.get_required_var_names(client),
        "cover": cover.get_required_var_names(client),
        "climate": climate.get_required_var_names(client),
        "event": event.get_required_var_names(client),  # event rieši sensor.py
    }

    all_vars: list[str] = []
    for v in platform_vars.values():
        all_vars.extend(v)

    values: list[str] = []
    for i in range(0, len(all_vars), BATCH):
        values.extend(await client.async_get_many(all_vars[i : i + BATCH]))

    o = 0
    for key, vlist in platform_vars.items():
        entry_data[f"initial_values_{key}"] = values[o : o + len(vlist)]
        o += len(vlist)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def on_plc_restart():
        await _async_reload_platforms(hass, entry)

    client.register_restart_callback(on_plc_restart)
    client.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: PLCComSClient = entry_data["client"]
    await client.async_disconnect()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok