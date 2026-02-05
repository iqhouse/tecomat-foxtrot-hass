from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, THERMOSTAT_BASE


def _safe_int(s: str, default: int = 0) -> int:
    try:
        return int((s or "").strip())
    except (ValueError, TypeError):
        return default


def _safe_float(s: str, default: float = 0.0) -> float:
    try:
        return float((s or "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return default


def _discover_thermostats(client):
    candidates = []
    for type_var in client.variables:
        if not type_var.lower().endswith(f"{THERMOSTAT_BASE.lower()}_type"):
            continue
        base = type_var.rsplit("_", 1)[0]
        plc_base = base.rsplit(f"_{THERMOSTAT_BASE}", 1)[0] if THERMOSTAT_BASE in base.upper() else base
        candidates.append((type_var, base, plc_base))
    return candidates


def get_required_var_names(client) -> list[str]:
    out: list[str] = []
    for type_var, base, _plc_base in _discover_thermostats(client):
        out.extend(
            [
                client.resolve_var(type_var),
                client.resolve_var(f"{base}_name"),
                client.resolve_var(f"{base}_meastemp"),
                client.resolve_var(f"{base}_mintemp"),
                client.resolve_var(f"{base}_maxtemp"),
                client.resolve_var(f"{base}_setpoint"),
                client.resolve_var(f"{base}_coolmode"),
                client.resolve_var(f"{base}_cool"),
                client.resolve_var(f"{base}_heatmode"),
                client.resolve_var(f"{base}_heat"),
            ]
        )
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    candidates = _discover_thermostats(client)
    values = entry_data.get("initial_values_climate") or []
    idx = 0

    for type_var, base, plc_base in candidates:
        if idx + 10 > len(values):
            break

        chunk = values[idx : idx + 10]
        idx += 10

        t_type = _safe_int(chunk[0], -1)
        if t_type not in (1, 2, 3):
            continue

        name = (chunk[1] or "").strip() or plc_base
        current_temp = _safe_float(chunk[2], 20.0)
        min_temp = _safe_float(chunk[3], 5.0)
        max_temp = _safe_float(chunk[4], 35.0)
        target_temp = _safe_float(chunk[5], 21.0)

        coolmode = (chunk[6] or "").strip() in ("1", "true", "TRUE")
        cool = (chunk[7] or "").strip() in ("1", "true", "TRUE")
        heatmode = (chunk[8] or "").strip() in ("1", "true", "TRUE")
        heat = (chunk[9] or "").strip() in ("1", "true", "TRUE")

        if t_type == 1:
            is_on = coolmode
            is_active = cool
            heat_active = False
            heat_mode_state = False
            cool_mode_state = False
        elif t_type == 2:
            is_on = heatmode
            is_active = heat
            heat_active = False
            heat_mode_state = False
            cool_mode_state = False
        else:
            heat_active = heat
            heat_mode_state = heatmode
            cool_mode_state = coolmode
            if heatmode:
                is_on = True
                is_active = heat_active
            elif coolmode:
                is_on = True
                is_active = cool
            else:
                is_on = False
                is_active = False

        entities.append(
            TecomatThermostat(
                name,
                client,
                plc_base,
                base,
                t_type,
                target_temp,
                current_temp,
                min_temp,
                max_temp,
                is_on,
                is_active,
                False,
                heat_active,
                heat_mode_state,
                cool_mode_state,
                entry.entry_id,
            )
        )

    async_add_entities(entities)


class TecomatThermostat(ClimateEntity):
    _attr_has_entity_name = False
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_should_poll = False

    def __init__(
        self,
        name,
        client,
        plc_base,
        base,
        t_type,
        target,
        current,
        min_t,
        max_t,
        is_on,
        is_active,
        auto_mode,
        heat_active,
        heat_mode_state,
        cool_mode_state,
        entry_id,
    ):
        self._client = client
        self._base = base
        self._type = t_type

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_thermostat"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature = target
        self._attr_current_temperature = current
        self._attr_min_temp = min_t
        self._attr_max_temp = max_t

        self._setpoint_var = self._client.resolve_var(f"{base}_setpoint")
        self._meastemp_var = self._client.resolve_var(f"{base}_meastemp")

        if self._type == 1:
            self._attr_hvac_modes = [HVACMode.COOL, HVACMode.OFF]
            self._attr_icon = "mdi:snowflake"
            self._mode_var = self._client.resolve_var(f"{base}_coolmode")
            self._active_var = self._client.resolve_var(f"{base}_cool")
            self._attr_hvac_mode = HVACMode.COOL if is_on else HVACMode.OFF
            self._attr_hvac_action = HVACAction.COOLING if is_active else HVACAction.IDLE
            self._heatmode_var = None
            self._heat_var = None
        elif self._type == 2:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
            self._attr_icon = "mdi:thermometer-lines"
            self._mode_var = self._client.resolve_var(f"{base}_heatmode")
            self._active_var = self._client.resolve_var(f"{base}_heat")
            self._attr_hvac_mode = HVACMode.HEAT if is_on else HVACMode.OFF
            self._attr_hvac_action = HVACAction.HEATING if is_active else HVACAction.IDLE
            self._heatmode_var = None
            self._heat_var = None
        else:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
            self._attr_icon = "mdi:thermometer-auto"
            self._mode_var = self._client.resolve_var(f"{base}_coolmode")
            self._active_var = self._client.resolve_var(f"{base}_cool")
            self._heatmode_var = self._client.resolve_var(f"{base}_heatmode")
            self._heat_var = self._client.resolve_var(f"{base}_heat")

            self._heat_mode_state = heat_mode_state
            self._cool_mode_state = cool_mode_state
            self._heat_active_state = heat_active
            self._cool_active_state = is_active

            if is_on:
                self._attr_hvac_mode = HVACMode.HEAT if heat_mode_state else HVACMode.COOL
            else:
                self._attr_hvac_mode = HVACMode.OFF

            self._update_hvac_action()

        self._client.register_value_entity(self._setpoint_var, self._on_diff_setpoint)
        self._client.register_value_entity(self._meastemp_var, self._on_diff_meas)
        self._client.register_value_entity(self._mode_var, self._on_diff_mode)
        self._client.register_value_entity(self._active_var, self._on_diff_active)
        if self._type == 3:
            self._client.register_value_entity(self._heatmode_var, self._on_diff_heatmode)
            self._client.register_value_entity(self._heat_var, self._on_diff_heat)

    def _update_hvac_action(self):
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
            return

        if self._type == 3:
            if self._attr_hvac_mode == HVACMode.HEAT:
                self._attr_hvac_action = HVACAction.HEATING if self._heat_active_state else HVACAction.IDLE
            elif self._attr_hvac_mode == HVACMode.COOL:
                self._attr_hvac_action = HVACAction.COOLING if self._cool_active_state else HVACAction.IDLE
            else:
                self._attr_hvac_action = HVACAction.OFF
            return

    def _on_diff_setpoint(self, value):
        try:
            self._attr_target_temperature = float((value or "").replace(",", "."))
            self.async_write_ha_state()
        except Exception:
            pass

    def _on_diff_meas(self, value):
        try:
            self._attr_current_temperature = float((value or "").replace(",", "."))
            self.async_write_ha_state()
        except Exception:
            pass

    def _on_diff_mode(self, value):
        state = (value or "").strip() in ("1", "true", "TRUE")

        if self._type == 1:
            self._attr_hvac_mode = HVACMode.COOL if state else HVACMode.OFF
        elif self._type == 2:
            self._attr_hvac_mode = HVACMode.HEAT if state else HVACMode.OFF
        else:
            self._cool_mode_state = state
            if self._attr_hvac_mode == HVACMode.OFF and state:
                self._attr_hvac_mode = HVACMode.COOL
            elif not state and not self._heat_mode_state:
                self._attr_hvac_mode = HVACMode.OFF

        if self._type == 3:
            self._update_hvac_action()
        self.async_write_ha_state()

    def _on_diff_active(self, value):
        active = (value or "").strip() in ("1", "true", "TRUE")

        if self._type == 1:
            self._attr_hvac_action = HVACAction.COOLING if active else HVACAction.IDLE
        elif self._type == 2:
            self._attr_hvac_action = HVACAction.HEATING if active else HVACAction.IDLE
        else:
            self._cool_active_state = active
            self._update_hvac_action()

        self.async_write_ha_state()

    def _on_diff_heatmode(self, value):
        self._heat_mode_state = (value or "").strip() in ("1", "true", "TRUE")
        if self._attr_hvac_mode == HVACMode.OFF and self._heat_mode_state:
            self._attr_hvac_mode = HVACMode.HEAT
        elif not self._heat_mode_state and not self._cool_mode_state:
            self._attr_hvac_mode = HVACMode.OFF
        self._update_hvac_action()
        self.async_write_ha_state()

    def _on_diff_heat(self, value):
        self._heat_active_state = (value or "").strip() in ("1", "true", "TRUE")
        self._update_hvac_action()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE not in kwargs:
            return
        await self._client.async_set(self._setpoint_var, str(kwargs[ATTR_TEMPERATURE]))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if self._type == 1:
            await self._client.async_set(self._mode_var, "1" if hvac_mode == HVACMode.COOL else "0")
        elif self._type == 2:
            await self._client.async_set(self._mode_var, "1" if hvac_mode == HVACMode.HEAT else "0")
        else:
            if hvac_mode == HVACMode.OFF:
                await self._client.async_set(self._mode_var, "0")
                await self._client.async_set(self._heatmode_var, "0")
            elif hvac_mode == HVACMode.COOL:
                await self._client.async_set(self._heatmode_var, "0")
                await self._client.async_set(self._mode_var, "1")
            elif hvac_mode == HVACMode.HEAT:
                await self._client.async_set(self._mode_var, "0")
                await self._client.async_set(self._heatmode_var, "1")

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._setpoint_var)
        self._client.unregister_value_entity(self._meastemp_var)
        self._client.unregister_value_entity(self._mode_var)
        self._client.unregister_value_entity(self._active_var)
        if self._type == 3:
            self._client.unregister_value_entity(self._heatmode_var)
            self._client.unregister_value_entity(self._heat_var)