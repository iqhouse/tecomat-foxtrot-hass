"""Light platform for Tecomat Foxtrot."""
import logging
from typing import Any

from homeassistant.components.light import (
    LightEntity, 
    ColorMode, 
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.const import Platform
from .const import DOMAIN, LIGHT_BASE

_LOGGER = logging.getLogger(__name__)

# Definícia štandardných limitov pre Kelviny (teplá biela - studená biela)
DEFAULT_MIN_KELVIN = 2000
DEFAULT_MAX_KELVIN = 6500

async def async_setup_entry(hass, entry, async_add_entities):
    """Nastavenie platformy svetiel pre Tecomat Foxtrot."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        # Hľadáme premenné, ktoré končia na _ONOFF (základ pre svetlo)
        if not var.lower().endswith(f"{LIGHT_BASE.lower()}_onoff"):
            continue

        base = var.rsplit("_", 1)[0]
        # Vyčistenie identifikátora pre unikátne ID
        plc_base = base.rsplit("_LIGHT", 1)[0] if "_LIGHT" in base.upper() else base
        
        try:
            # Zistenie typu svetla z PLC (0 = On/Off, 1 = Dimmer, 2 = Tunable White)
            raw_type = await client.async_get(f"{base}_type")
            light_type = int(float(raw_type.strip().replace(",", ".")))

            name = (await client.async_get(f"{base}_name")).strip() or plc_base
            
            # Počiatočný stav
            raw_init = await client.async_get(var)
            initial_on = raw_init.strip() in ("1", "true", "TRUE")

            entities.append(TecomatLight(
                name, client, plc_base, base, light_type, initial_on, entry.entry_id
            ))
        except Exception as e:
            _LOGGER.error("Chyba pri pridávaní svetla %s: %s", var, e)
            continue

    async_add_entities(entities)

class TecomatLight(LightEntity):
    """Reprezentácia Tecomat svetla (Switch / Dimmer / White Temp)."""

    def __init__(self, name, client, plc_base, base, light_type, initial_on, entry_id):
        self._attr_name = name
        self._client = client
        self._base = base
        self._state_var = f"{base}_onoff"
        self._dim_var = f"{base}_dim"
        self._temp_var = f"{base}_temp"
        
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_light"
        self._attr_is_on = initial_on
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        self._attr_should_poll = False

        # Konfigurácia podľa typu svetla
        if light_type == 1: # Stmievač
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        elif light_type == 2: # Tunable White (teplota farby)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            # Oprava varovania HA: Nastavenie limitov v Kelvinoch
            self._attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
            self._attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN
        else: # Klasické On/Off svetlo
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}

        # Registrácia spätnej väzby (push)
        self._client.register_value_entity(self._state_var, self._on_diff_state)
        if light_type >= 1:
            self._client.register_value_entity(self._dim_var, self._on_diff_dim)
        if light_type == 2:
            self._client.register_value_entity(self._temp_var, self._on_diff_temp)

    # --- Callbacky pre zmeny z PLC ---

    def _on_diff_state(self, value):
        self._attr_is_on = value.strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    def _on_diff_dim(self, value):
        try:
            dim_pct = float(value.strip().replace(",", "."))
            # Prepočet z 0-100% na 0-255 pre HA
            self._attr_brightness = int((dim_pct / 100.0) * 255)
            self.async_write_ha_state()
        except (ValueError, TypeError):
            pass

    def _on_diff_temp(self, value):
        try:
            # PLC posiela hodnotu priamo v Kelvinoch
            self._attr_color_temp_kelvin = int(float(value.strip().replace(",", ".")))
            self.async_write_ha_state()
        except (ValueError, TypeError):
            pass

    # --- Ovládacie metódy ---

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Zapnutie svetla s voliteľnými parametrami."""
        
        # 1. Nastavenie jasu
        if ATTR_BRIGHTNESS in kwargs:
            dim_pct = (kwargs[ATTR_BRIGHTNESS] / 255.0) * 100.0
            await self._client.async_set(self._dim_var, "{:.1f}".format(dim_pct))
        
        # 2. Nastavenie teploty farby (Kelvin)
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            await self._client.async_set(self._temp_var, str(kelvin))
            
        # 3. Ak nie je zadaný jas ani teplota, len pošleme ON
        if not kwargs or (ATTR_BRIGHTNESS not in kwargs and ATTR_COLOR_TEMP_KELVIN not in kwargs):
            await self._client.async_set(self._state_var, "1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Vypnutie svetla."""
        await self._client.async_set(self._state_var, "0")