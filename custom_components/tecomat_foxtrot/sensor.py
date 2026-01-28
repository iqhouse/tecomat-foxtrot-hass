from __future__ import annotations
import asyncio
import re
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import (
    DOMAIN, DISP, SENSOR_DISPLAY_SYMBOL_LUX, SENSOR_DISPLAY_SYMBOL_CO2,
    SENSOR_DISPLAY_SYMBOL_CO, SENSOR_DISPLAY_SYMBOL_TEMP,
    SENSOR_DISPLAY_SYMBOL_HUMIDITY, SENSOR_DISPLAY_SYMBOL_GENERIC,
    SENSOR_DISPLAY_TYPE_REAL,
)

def _to_float(raw: str) -> float:
    return float(raw.strip().replace(",", "."))

def _slugify_plc_id(plc_id: str) -> str:
    s = plc_id.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities: list[SensorEntity] = []

    for value_var in client.variables:
        if not value_var.lower().endswith(f"{DISP.lower()}_value"):
            continue

        base = value_var.rsplit(".", 1)[0]
        plc_base = base.rsplit("_DISPLAY", 1)[0] if base.upper().endswith("_DISPLAY") else base
        slug = _slugify_plc_id(plc_base)
        suggested_entity_id = f"sensor.{slug}"

        try:
            display_type = int(_to_float(await client.async_get(f"{base}.{DISP}_TYPE")))
            symbol = int(_to_float(await client.async_get(f"{base}.{DISP}_SYMBOL")))
            if display_type != SENSOR_DISPLAY_TYPE_REAL: continue
            
            name = (await client.async_get(f"{base}.{DISP}_NAME")).strip() or plc_base
            unit = (await client.async_get(f"{base}.{DISP}_UNIT")).strip()
            raw_init = await client.async_get(value_var)
            initial_value = _to_float(raw_init)
        except Exception:
            continue

        common_args = {
            "name": name, "client": client, "plc_base": plc_base,
            "suggested_entity_id": suggested_entity_id, "value_var": value_var,
            "unit": unit, "initial_value": initial_value, "entry_id": entry.entry_id
        }

        if symbol == SENSOR_DISPLAY_SYMBOL_GENERIC:
            try:
                precision_raw = await client.async_get(f"{base}.{DISP}_PRECISION")
                precision = int(_to_float(precision_raw))
            except Exception:
                precision = 0
            entities.append(TecomatGenericDisplaySensor(**common_args, precision=precision))
        elif symbol == SENSOR_DISPLAY_SYMBOL_TEMP:
            entities.append(TecomatTemperatureSensor(**common_args))
        elif symbol == SENSOR_DISPLAY_SYMBOL_HUMIDITY:
            entities.append(TecomatHumiditySensor(**common_args))
        elif symbol == SENSOR_DISPLAY_SYMBOL_LUX:
            entities.append(TecomatLuxSensor(**common_args))
        elif symbol == SENSOR_DISPLAY_SYMBOL_CO2:
            entities.append(TecomatCO2Sensor(**common_args))
        elif symbol == SENSOR_DISPLAY_SYMBOL_CO:
            entities.append(TecomatCOSensor(**common_args))

    async_add_entities(entities)
    
    from .event import async_setup_entry as async_setup_event_entry
    await async_setup_event_entry(hass, entry, async_add_entities)

class _TecomatRealPushSensor(SensorEntity):
    _ROUND_N: int | None = None
    _attr_should_poll = False

    def __init__(self, name, client, plc_base, suggested_entity_id, value_var, unit, initial_value, entry_id):
        self._attr_name = name
        self._client = client
        self._value_var = value_var
        self._attr_unique_id = f"tecomat_foxtrot:{plc_base}"
        self.entity_id = suggested_entity_id
        self._attr_native_value = round(initial_value, self._ROUND_N) if self._ROUND_N is not None else initial_value
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._client.register_value_entity(self._value_var, self._on_diff_value)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._value_var)

    def _on_diff_value(self, raw_value: str) -> None:
        try:
            val = _to_float(raw_value)
            self._attr_native_value = round(val, self._ROUND_N) if self._ROUND_N is not None else val
            self.async_write_ha_state()
        except Exception: pass

class TecomatTemperatureSensor(_TecomatRealPushSensor):
    _ROUND_N = 2
    def __init__(self, **kwargs):
        kwargs["unit"] = UnitOfTemperature.CELSIUS if "c" in kwargs.get("unit", "").lower() else kwargs.get("unit")
        super().__init__(**kwargs)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE

class TecomatHumiditySensor(_TecomatRealPushSensor):
    _ROUND_N = 1
    def __init__(self, **kwargs):
        kwargs["unit"] = "%"
        super().__init__(**kwargs)
        self._attr_device_class = SensorDeviceClass.HUMIDITY

class TecomatLuxSensor(_TecomatRealPushSensor):
    _ROUND_N = 0
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE

class TecomatCO2Sensor(_TecomatRealPushSensor):
    _ROUND_N = 0
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_device_class = SensorDeviceClass.CO2

class TecomatCOSensor(_TecomatRealPushSensor):
    _ROUND_N = 0

class TecomatGenericDisplaySensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, name, client, plc_base, suggested_entity_id, value_var, unit, initial_value, entry_id, precision):
        self._attr_name = name
        self._client = client
        self._value_var = value_var
        self._attr_unique_id = f"tecomat_foxtrot:{plc_base}"
        self.entity_id = suggested_entity_id
        self._precision = int(precision) if precision is not None else 0
        self._attr_native_value = round(initial_value, self._precision)
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._client.register_value_entity(self._value_var, self._on_diff_value)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._value_var)

    def _on_diff_value(self, raw_value: str) -> None:
        try:
            val = _to_float(raw_value)
            self._attr_native_value = round(val, self._precision)
            self.async_write_ha_state()
        except Exception: 
            pass