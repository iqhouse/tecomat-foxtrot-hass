from __future__ import annotations
from typing import Any

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

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        if not var.lower().endswith(f"{THERMOSTAT_BASE.lower()}_type"):
            continue

        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit(f"_{THERMOSTAT_BASE}", 1)[0] if THERMOSTAT_BASE in base.upper() else base
        
        try:
            t_type_raw = await client.async_get(var)
            t_type = int(t_type_raw.strip())
            
            if t_type not in (1, 2, 3):
                continue

            name = (await client.async_get(f"{base}_name")).strip() or plc_base
            current_temp = float((await client.async_get(f"{base}_meastemp")).replace(",", "."))
            min_temp = float((await client.async_get(f"{base}_mintemp")).replace(",", "."))
            max_temp = float((await client.async_get(f"{base}_maxtemp")).replace(",", "."))
            
            if t_type == 1:
                target_temp = float((await client.async_get(f"{base}_setpoint")).replace(",", "."))
                is_on = (await client.async_get(f"{base}_coolmode")).strip() in ("1", "true", "TRUE")
                is_active = (await client.async_get(f"{base}_cool")).strip() in ("1", "true", "TRUE")
                auto_mode = False
                heat_active = False
            elif t_type == 2:
                target_temp = float((await client.async_get(f"{base}_setpoint")).replace(",", "."))
                is_on = (await client.async_get(f"{base}_heatmode")).strip() in ("1", "true", "TRUE")
                is_active = (await client.async_get(f"{base}_heat")).strip() in ("1", "true", "TRUE")
                auto_mode = False
                heat_active = False
            else:
                target_temp = float((await client.async_get(f"{base}_setpoint")).replace(",", "."))
                heat_mode = (await client.async_get(f"{base}_heatmode")).strip() in ("1", "true", "TRUE")
                cool_mode = (await client.async_get(f"{base}_coolmode")).strip() in ("1", "true", "TRUE")
                heat_active = (await client.async_get(f"{base}_heat")).strip() in ("1", "true", "TRUE")
                cool_active = (await client.async_get(f"{base}_cool")).strip() in ("1", "true", "TRUE")
                if heat_mode:
                    is_on = True
                    is_active = heat_active
                elif cool_mode:
                    is_on = True
                    is_active = cool_active
                else:
                    is_on = False
                    is_active = False

            entities.append(TecomatThermostat(
                name, client, plc_base, base, t_type,
                target_temp, current_temp, min_temp, max_temp, 
                is_on, is_active, False, heat_active,
                heat_mode if t_type == 3 else False,
                cool_mode if t_type == 3 else False,
                entry.entry_id
            ))
        except Exception as e:
            continue

    async_add_entities(entities)

class TecomatThermostat(ClimateEntity):
    _attr_has_entity_name = False
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, name, client, plc_base, base, t_type, target, current, min_t, max_t, is_on, is_active, auto_mode, heat_active, heat_mode_state, cool_mode_state, entry_id):
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

        if self._type == 1:
            self._attr_hvac_modes = [HVACMode.COOL, HVACMode.OFF]
            self._attr_icon = "mdi:snowflake"
            self._mode_var = f"{base}_coolmode"
            self._active_var = f"{base}_cool"
            self._automode_var = None
            self._heatmode_var = None
            self._heat_var = None
            self._attr_hvac_mode = HVACMode.COOL if is_on else HVACMode.OFF
        elif self._type == 2:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
            self._attr_icon = "mdi:thermometer-lines"
            self._mode_var = f"{base}_heatmode"
            self._active_var = f"{base}_heat"
            self._automode_var = None
            self._heatmode_var = None
            self._heat_var = None
            self._attr_hvac_mode = HVACMode.HEAT if is_on else HVACMode.OFF
        else:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
            self._attr_icon = "mdi:thermometer-auto"
            self._mode_var = f"{base}_coolmode"
            self._automode_var = None
            self._heatmode_var = f"{base}_heatmode"
            self._heat_var = f"{base}_heat"
            self._active_var = f"{base}_cool"
            self._auto_mode_state = False
            self._heat_mode_state = heat_mode_state if t_type == 3 else False
            self._cool_mode_state = cool_mode_state if t_type == 3 else False
            self._heat_active_state = heat_active if t_type == 3 else False
            self._cool_active_state = is_active if t_type == 3 else False
            if is_on:
                self._attr_hvac_mode = HVACMode.HEAT if heat_mode_state else HVACMode.COOL
            else:
                self._attr_hvac_mode = HVACMode.OFF

        self._update_hvac_action(is_active, heat_active)

        self._client.register_value_entity(f"{base}_setpoint", self._on_diff_setpoint)
        self._client.register_value_entity(f"{base}_meastemp", self._on_diff_meas)
        self._client.register_value_entity(self._mode_var, self._on_diff_mode)
        self._client.register_value_entity(self._active_var, self._on_diff_active)
        if self._type == 3:
            self._client.register_value_entity(self._heatmode_var, self._on_diff_heatmode)
            self._client.register_value_entity(self._heat_var, self._on_diff_heat)

    def _update_hvac_action(self, cool_active, heat_active=False):
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        elif self._type == 3:
            if self._attr_hvac_mode == HVACMode.HEAT:
                self._attr_hvac_action = HVACAction.HEATING if heat_active else HVACAction.IDLE
            elif self._attr_hvac_mode == HVACMode.COOL:
                self._attr_hvac_action = HVACAction.COOLING if cool_active else HVACAction.IDLE
            else:
                self._attr_hvac_action = HVACAction.OFF
        elif cool_active if self._type == 1 else heat_active:
            self._attr_hvac_action = HVACAction.COOLING if self._type == 1 else HVACAction.HEATING
        else:
            self._attr_hvac_action = HVACAction.IDLE

    def _on_diff_setpoint(self, value):
        try:
            self._attr_target_temperature = float(value.strip().replace(",", "."))
            self.async_write_ha_state()
        except ValueError: pass

    def _on_diff_meas(self, value):
        try:
            self._attr_current_temperature = float(value.strip().replace(",", "."))
            self.async_write_ha_state()
        except ValueError: pass

    def _on_diff_mode(self, value):
        is_on = value.strip() in ("1", "true", "TRUE")
        if self._type == 1:
            self._attr_hvac_mode = HVACMode.COOL if is_on else HVACMode.OFF
        elif self._type == 2:
            self._attr_hvac_mode = HVACMode.HEAT if is_on else HVACMode.OFF
        else:
            self._cool_mode_state = is_on
            self._update_hvac_mode_type3()
        self.async_write_ha_state()

    def _on_diff_active(self, value):
        is_active = value.strip() in ("1", "true", "TRUE")
        if self._type == 3:
            self._cool_active_state = is_active
            self._update_hvac_action(is_active, self._heat_active_state)
        else:
            self._update_hvac_action(is_active)
        self.async_write_ha_state()

    def _on_diff_heatmode(self, value):
        if self._type != 3:
            return
        self._heat_mode_state = value.strip() in ("1", "true", "TRUE")
        self._update_hvac_mode_type3()
        self.async_write_ha_state()

    def _on_diff_heat(self, value):
        if self._type != 3:
            return
        self._heat_active_state = value.strip() in ("1", "true", "TRUE")
        self._update_hvac_action(self._cool_active_state, self._heat_active_state)
        self.async_write_ha_state()

    def _update_hvac_mode_type3(self):
        if self._type != 3:
            return
        if self._heat_mode_state:
            self._attr_hvac_mode = HVACMode.HEAT
        elif self._cool_mode_state:
            self._attr_hvac_mode = HVACMode.COOL
        else:
            self._attr_hvac_mode = HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if self._type == 3:
            if hvac_mode == HVACMode.OFF:
                await self._client.async_set(self._heatmode_var, "0")
                await self._client.async_set(self._mode_var, "0")
            elif hvac_mode == HVACMode.HEAT:
                await self._client.async_set(self._heatmode_var, "1")
                await self._client.async_set(self._mode_var, "0")
            elif hvac_mode == HVACMode.COOL:
                await self._client.async_set(self._heatmode_var, "0")
                await self._client.async_set(self._mode_var, "1")
        else:
            on_val = "1" if hvac_mode != HVACMode.OFF else "0"
            await self._client.async_set(self._mode_var, on_val)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._client.async_set(f"{self._base}_setpoint", f"{temp:.1f}")

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(f"{self._base}_setpoint")
        self._client.unregister_value_entity(f"{self._base}_meastemp")
        self._client.unregister_value_entity(self._mode_var)
        self._client.unregister_value_entity(self._active_var)
        if self._type == 3:
            self._client.unregister_value_entity(self._heatmode_var)
            self._client.unregister_value_entity(self._heat_var)