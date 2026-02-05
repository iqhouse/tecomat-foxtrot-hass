from __future__ import annotations

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
    return float((raw or "").strip().replace(",", "."))


def _is_numeric_like(s: str) -> bool:
    if not s or not str(s).strip():
        return True
    t = str(s).strip().replace(",", ".")
    try:
        float(t)
        return True
    except ValueError:
        return False


def _friendly_name_from_id(identifier: str) -> str:
    if not identifier or not identifier.strip():
        return "Senzor"
    parts = identifier.strip().split(".")
    part = parts[-1]
    s = part.replace("_", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s.title() if s else "Senzor"


def _slugify_plc_id(plc_id: str) -> str:
    s = (plc_id or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _discover_displays(client):
    out = []
    for value_var in client.variables:
        if not value_var.lower().endswith(f"{DISP.lower()}_value"):
            continue
        base = value_var.rsplit(".", 1)[0]
        plc_base = base.rsplit("_DISPLAY", 1)[0] if base.upper().endswith("_DISPLAY") else base
        slug = _slugify_plc_id(plc_base)
        suggested_entity_id = f"sensor.{slug}"
        out.append((value_var, base, plc_base, suggested_entity_id))
    # stabilné poradie
    out.sort(key=lambda x: (x[2] or x[1]).lower())
    return out


def get_required_var_names(client) -> list[str]:
    out = []
    for value_var, base, _plc_base, _eid in _discover_displays(client):
        out.extend([
            f"{base}.{DISP}_TYPE", f"{base}.{DISP}_SYMBOL", f"{base}.{DISP}_NAME",
            f"{base}.{DISP}_UNIT", value_var, f"{base}.{DISP}_PRECISION",
        ])
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities: list[SensorEntity] = []

    entry_id = entry.entry_id
    candidates = _discover_displays(client)

    values = entry_data.get("initial_values_sensor") or []
    idx = 0

    for value_var, base, plc_base, suggested_entity_id in candidates:
        if idx + 6 > len(values):
            break

        try:
            display_type = int(_to_float(values[idx]))
            symbol = int(_to_float(values[idx + 1]))
            name_raw = (values[idx + 2] or "").strip()
            unit = (values[idx + 3] or "").strip()
            initial_value = _to_float(values[idx + 4])
            try:
                precision = int(_to_float(values[idx + 5]))
            except Exception:
                precision = 0
        except Exception:
            idx += 6
            continue

        idx += 6

        if display_type != SENSOR_DISPLAY_TYPE_REAL:
            continue

        if name_raw and not _is_numeric_like(name_raw):
            name = name_raw
        else:
            name = _friendly_name_from_id(plc_base or base)

        common_args = {
            "name": name, "client": client, "plc_base": plc_base,
            "suggested_entity_id": suggested_entity_id, "value_var": value_var,
            "unit": unit, "initial_value": initial_value, "entry_id": entry_id,
        }

        if symbol == SENSOR_DISPLAY_SYMBOL_GENERIC:
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

    # event senzory (button counters)
    from .event import async_setup_entry as async_setup_event_entry
    await async_setup_event_entry(hass, entry, async_add_entities)


class _TecomatRealPushSensor(SensorEntity):
    _ROUND_N: int | None = None
    _attr_should_poll = False

    def __init__(self, name, client, plc_base, suggested_entity_id, value_var, unit, initial_value, entry_id):
        self._attr_name = name
        self._client = client
        self._value_var = value_var
        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{plc_base}"  # ponechané
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
        except Exception:
            pass


class TecomatTemperatureSensor(_TecomatRealPushSensor):
    _ROUND_N = 2

    def __init__(self, **kwargs):
        kwargs["unit"] = UnitOfTemperature.CELSIUS if "c" in (kwargs.get("unit", "") or "").lower() else kwargs.get("unit")
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

    def __init__(self, name, client, plc_base, suggested_entity_id, value_var, unit, initial_value, entry_id, precision: int = 0):
        self._attr_name = name
        self._client = client
        self._value_var = value_var
        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{plc_base}"  # ponechané
        self.entity_id = suggested_entity_id
        self._precision = int(precision or 0)
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