from __future__ import annotations
import re
from datetime import datetime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import STATE_UNKNOWN
from .const import DOMAIN, BUTTON_BASE

def _slugify_plc_id(plc_id: str) -> str:
    s = plc_id.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _to_int(raw: str) -> int:
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return 0

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities: list[TecomatButtonSensor] = []

    button_bases = set()
    
    for var in client.variables:
        var_lower = var.lower()
        if var_lower.endswith(f"{BUTTON_BASE.lower()}_clickcnt") or var_lower.endswith(f"{BUTTON_BASE.lower()}_presscnt"):
            parts = var.rsplit(".", 1)
            if len(parts) == 2:
                base = parts[0]
                if base.upper().endswith("_" + BUTTON_BASE):
                    base = base.rsplit("_", 1)[0]
                button_bases.add(base)

    for base in button_bases:
        click_var = None
        press_var = None
        name_var = None
        
        for var in client.variables:
            var_lower = var.lower()
            if var_lower.endswith(f"{BUTTON_BASE.lower()}_clickcnt") and base in var:
                click_var = var
            elif var_lower.endswith(f"{BUTTON_BASE.lower()}_presscnt") and base in var:
                press_var = var
            elif var_lower.endswith(f"{BUTTON_BASE.lower()}_name") and base in var:
                name_var = var
        
        if not click_var or not press_var:
            continue
        
        try:
            if name_var:
                name = (await client.async_get(name_var)).strip()
            else:
                name = base.split(".")[-1] if "." in base else base
            
            if not name:
                name = base.split(".")[-1] if "." in base else base
            
            initial_click = _to_int(await client.async_get(click_var))
            initial_press = _to_int(await client.async_get(press_var))
            
            plc_base = base.split(".")[-1] if "." in base else base
            slug = _slugify_plc_id(plc_base)
            
            entities.append(TecomatButtonSensor(
                hass=hass,
                name=f"{name} Click",
                client=client,
                plc_base=plc_base,
                counter_var=click_var,
                initial_count=initial_click,
                entry_id=entry.entry_id,
                suggested_entity_id=f"sensor.{slug}_click",
                sensor_type="click"
            ))
            
            entities.append(TecomatButtonSensor(
                hass=hass,
                name=f"{name} Press",
                client=client,
                plc_base=plc_base,
                counter_var=press_var,
                initial_count=initial_press,
                entry_id=entry.entry_id,
                suggested_entity_id=f"sensor.{slug}_press",
                sensor_type="press"
            ))
        except Exception as e:
            continue

    if async_add_entities and entities:
        async_add_entities(entities)

class TecomatButtonSensor(SensorEntity):
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    
    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        client,
        plc_base: str,
        counter_var: str,
        initial_count: int,
        entry_id: str,
        suggested_entity_id: str,
        sensor_type: str
    ):
        self.hass = hass
        self._attr_name = name
        self._client = client
        self._plc_base = plc_base
        self._counter_var = counter_var
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_{sensor_type}"
        self.entity_id = suggested_entity_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}
        
        self._prev_count = initial_count
        self._attr_native_value = initial_count
        
        self._last_change_time = None
        
        self._client.register_value_entity(self._counter_var, self._on_count_change)
    
    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._counter_var)
    
    def _on_count_change(self, raw_value: str) -> None:
        try:
            new_count = _to_int(raw_value)
            
            if new_count > self._prev_count:
                self._attr_native_value = new_count
                self._last_change_time = datetime.now()
                self.async_write_ha_state()
                self._prev_count = new_count
            elif new_count != self._prev_count:
                self._attr_native_value = new_count
                self._prev_count = new_count
                self.async_write_ha_state()
        except Exception as e:
            pass
    
    @property
    def extra_state_attributes(self):
        attrs = {
            "plc_base": self._plc_base,
            "sensor_type": self._sensor_type,
            "count": self._attr_native_value,
        }
        if self._last_change_time:
            attrs["last_change"] = self._last_change_time.isoformat()
        return attrs
