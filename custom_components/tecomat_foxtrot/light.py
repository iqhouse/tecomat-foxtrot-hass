import asyncio
from typing import Any

from homeassistant.components.light import (
    LightEntity, 
    ColorMode, 
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_COLOR_TEMP_KELVIN,
)
from .const import DOMAIN, LIGHT_BASE

async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        if not var.lower().endswith(f"{LIGHT_BASE.lower()}_onoff"):
            continue

        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit("_LIGHT", 1)[0] if "_LIGHT" in base.upper() else base
        
        try:
            raw_type = await client.async_get(f"{base}_type")
            is_dimmable = raw_type.strip() in ("1", "true", "TRUE")
            
            dimtype = 0
            if is_dimmable:
                try:
                    raw_dimtype = await client.async_get(f"{base}_dimtype")
                    dimtype = int(float(raw_dimtype.strip().replace(",", ".")))
                except: pass

            name = (await client.async_get(f"{base}_name")).strip() or plc_base
            raw_init = await client.async_get(var)
            initial_on = raw_init.strip() in ("1", "true", "TRUE")
            
            initial_brightness = None
            initial_rgb = None
            initial_temp = None
            min_temp = 2000
            max_temp = 6500
            
            dimlevel_var = None
            tgtlevel_var = None
            rgb_var = None
            temp_var = None
            
            for v in client.variables:
                v_upper = v.upper()
                if v_upper.startswith(base.upper()):
                    if v_upper.endswith("_DIMLEVEL"): dimlevel_var = v
                    elif v_upper.endswith("_TGTLEVEL"): tgtlevel_var = v
                    elif v_upper.endswith("_RGB"): rgb_var = v
                    elif v_upper.endswith("_COLORTEMP"): temp_var = v

            if is_dimmable:
                try:
                    v_get = dimlevel_var or f"{base}_dimlevel"
                    raw_dim = await client.async_get(v_get)
                    dim_pct = float(raw_dim.strip().replace(",", "."))
                    initial_brightness = int((dim_pct / 100.0) * 255)
                except: pass

                if dimtype == 1:
                    try:
                        v_rgb = rgb_var or f"{base}_rgb"
                        raw_rgb = await client.async_get(v_rgb)
                        initial_rgb = int(float(raw_rgb.strip().replace(",", ".")))
                    except: pass
                
                elif dimtype == 2:
                    try:
                        temp_v = temp_var or f"{base}_colortemp"
                        initial_temp = int(float((await client.async_get(temp_v)).strip()))
                        min_temp = int(float((await client.async_get(f"{base}_minTempK")).strip()))
                        max_temp = int(float((await client.async_get(f"{base}_maxTempK")).strip()))
                    except: pass

            entities.append(TecomatLight(
                name, client, plc_base, base, is_dimmable, dimtype, initial_on, 
                initial_brightness, initial_rgb, initial_temp, min_temp, max_temp,
                dimlevel_var, tgtlevel_var, rgb_var, temp_var, entry.entry_id
            ))
        except Exception as e:
            continue

    async_add_entities(entities)

class TecomatLight(LightEntity):
    def __init__(self, name, client, plc_base, base, is_dimmable, dimtype, initial_on, 
                 initial_brightness, initial_rgb, initial_temp, min_temp, max_temp,
                 dimlevel_var, tgtlevel_var, rgb_var, temp_var, entry_id):
        self._attr_name = name
        self._client = client
        self._base = base
        self._dimtype = dimtype
        self._is_dimmable = is_dimmable
        
        self._state_var = f"{base}_onoff"
        self._dimlevel_var = dimlevel_var or f"{base}_dimlevel"
        self._tgtlevel_var = tgtlevel_var or f"{base}_tgtlevel"
        self._rgb_var = rgb_var or f"{base}_rgb"
        self._temp_var = temp_var or f"{base}_colortemp"
        
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_light"
        self._attr_is_on = initial_on
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._attr_should_poll = False
        
        self._attr_min_color_temp_kelvin = min_temp
        self._attr_max_color_temp_kelvin = max_temp

        self._last_brightness = initial_brightness if initial_brightness and initial_brightness > 0 else 255
        
        self._is_closing = False

        if not is_dimmable:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
        elif dimtype == 1:
            self._attr_color_mode = ColorMode.RGB
            self._attr_supported_color_modes = {ColorMode.RGB}
            if initial_rgb is not None:
                self._attr_rgb_color = (initial_rgb & 0xFF, (initial_rgb >> 8) & 0xFF, (initial_rgb >> 16) & 0xFF)
        elif dimtype == 2:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_temp_kelvin = initial_temp
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        if initial_brightness is not None:
            self._attr_brightness = initial_brightness

        self._client.register_value_entity(self._state_var, self._on_diff_state)
        if is_dimmable:
            self._client.register_value_entity(self._dimlevel_var, self._on_diff_dim)
            if dimtype == 1:
                self._client.register_value_entity(self._rgb_var, self._on_diff_rgb)
            elif dimtype == 2:
                self._client.register_value_entity(self._temp_var, self._on_diff_temp)

    def _on_diff_state(self, value):
        new_state = value.strip() in ("1", "true", "TRUE")
        
        if not new_state:
            self._is_closing = True
        else:
            self._is_closing = False
        
        self._attr_is_on = new_state
        self.async_write_ha_state()

    def _on_diff_dim(self, value):
        try:
            dim_pct = float(value.strip().replace(",", "."))
            brightness = int((dim_pct / 100.0) * 255)
            self._attr_brightness = brightness
            
            if brightness > 0:
                self._attr_is_on = True
                if not self._is_closing:
                    self._last_brightness = brightness
            else:
                self._attr_is_on = False
                self._is_closing = False
                
            self.async_write_ha_state()
        except: pass

    def _on_diff_rgb(self, value):
        try:
            rgb_int = int(float(value.strip().replace(",", ".")))
            self._attr_rgb_color = (rgb_int & 0xFF, (rgb_int >> 8) & 0xFF, (rgb_int >> 16) & 0xFF)
            self.async_write_ha_state()
        except: pass

    def _on_diff_temp(self, value):
        try:
            self._attr_color_temp_kelvin = int(float(value.strip()))
            self.async_write_ha_state()
        except: pass

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_closing = False
        
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            dim_pct = (brightness / 255.0) * 100.0
            
            if brightness <= 0:
                self._is_closing = True
                await self._client.async_set(self._state_var, "0")
                return
            else:
                self._last_brightness = brightness
                target_v = self._tgtlevel_var if self._dimtype == 0 else self._dimlevel_var
                await self._client.async_set(target_v, "{:.1f}".format(dim_pct))

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            temp = kwargs[ATTR_COLOR_TEMP_KELVIN]
            await self._client.async_set(self._temp_var, str(temp))

        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            rgb_int = (int(r) & 0xFF) | ((int(g) & 0xFF) << 8) | ((int(b) & 0xFF) << 16)
            await self._client.async_set(self._rgb_var, str(rgb_int))

        await self._client.async_set(self._state_var, "1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_closing = True
        
        await self._client.async_set(self._state_var, "0")