"""Button sensor platform for Tecomat Foxtrot (PLCComS) - CLICK and PRESS sensors."""
from __future__ import annotations
import logging
import re
from datetime import datetime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import STATE_UNKNOWN
from .const import DOMAIN, BUTTON_BASE

_LOGGER = logging.getLogger(__name__)

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
    """Set up button sensor entities (CLICK and PRESS)."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities: list[TecomatButtonSensor] = []

    # Nájdeme všetky BUTTON entity podľa CLICKCNT alebo PRESSCNT premenných
    button_bases = set()
    
    _LOGGER.debug("Hľadanie BUTTON entít medzi %d premennými", len(client.variables))
    for var in client.variables:
        var_lower = var.lower()
        if var_lower.endswith(f"{BUTTON_BASE.lower()}_clickcnt") or var_lower.endswith(f"{BUTTON_BASE.lower()}_presscnt"):
            # Extrahujeme base názov (napr. MAIN.FBTESTBUTTON z MAIN.FBTESTBUTTON.GTSAP1_BUTTON_CLICKCNT)
            parts = var.rsplit(".", 1)
            if len(parts) == 2:
                base = parts[0]
                # Odstránime GTSAP1_BUTTON z konca ak tam je
                if base.upper().endswith("_" + BUTTON_BASE):
                    base = base.rsplit("_", 1)[0]
                button_bases.add(base)
                _LOGGER.debug("Nájdená BUTTON premenná: %s (base: %s)", var, base)
    
    _LOGGER.debug("Nájdených %d BUTTON entít", len(button_bases))

    # Pre každú button entitu vytvoríme dva senzory (CLICK a PRESS)
    for base in button_bases:
        # Nájdeme všetky potrebné premenné
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
            # Načítame názov tlačidla
            if name_var:
                name = (await client.async_get(name_var)).strip()
            else:
                name = base.split(".")[-1] if "." in base else base
            
            if not name:
                name = base.split(".")[-1] if "." in base else base
            
            # Načítame počiatočné hodnoty
            initial_click = _to_int(await client.async_get(click_var))
            initial_press = _to_int(await client.async_get(press_var))
            
            plc_base = base.split(".")[-1] if "." in base else base
            slug = _slugify_plc_id(plc_base)
            
            # Vytvoríme dva senzory: jeden pre CLICK, jeden pre PRESS
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
            _LOGGER.warning("Chyba pri vytváraní button sensor entít pre %s: %s", base, e)
            continue

    # Pridáme entity do Home Assistant
    if async_add_entities and entities:
        async_add_entities(entities)
    _LOGGER.info("Vytvorených %d button sensor entít (CLICK + PRESS)", len(entities))

class TecomatButtonSensor(SensorEntity):
    """Senzor pre sledovanie button počítadla (CLICK alebo PRESS)."""
    
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
        
        # Sledovanie predchádzajúcej hodnoty pre detekciu zmien (nábežná hrana)
        self._prev_count = initial_count
        self._attr_native_value = initial_count
        
        # Timestamp poslednej zmeny (pre edge trigger)
        self._last_change_time = None
        
        # Registrácia callbacku pre zmeny hodnôt
        self._client.register_value_entity(self._counter_var, self._on_count_change)
    
    async def async_will_remove_from_hass(self) -> None:
        """Odregistrovať callback pri odstránení entity."""
        self._client.unregister_value_entity(self._counter_var)
    
    def _on_count_change(self, raw_value: str) -> None:
        """Callback pre zmenu počítadla - aktualizuje senzor pri nábežnej hrane."""
        try:
            new_count = _to_int(raw_value)
            
            # Detekcia nábežnej hrany - ak sa hodnota zmenila (zvýšila)
            if new_count > self._prev_count:
                # Aktualizujeme hodnotu senzora
                self._attr_native_value = new_count
                self._last_change_time = datetime.now()
                
                # Zapíšeme zmenu do stavu (nábežná hrana - senzor sa "aktivuje")
                self.async_write_ha_state()
                
                _LOGGER.debug("Button %s senzor aktualizovaný: %s (count=%d)", 
                             self._sensor_type.upper(), self._plc_base, new_count)
                
                self._prev_count = new_count
            elif new_count != self._prev_count:
                # Hodnota sa zmenila, ale nezvyšila sa (možno reset)
                self._attr_native_value = new_count
                self._prev_count = new_count
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.warning("Chyba pri spracovaní %s zmeny pre %s: %s", 
                          self._sensor_type, self._plc_base, e)
    
    @property
    def extra_state_attributes(self):
        """Vráti dodatočné atribúty senzora."""
        attrs = {
            "plc_base": self._plc_base,
            "sensor_type": self._sensor_type,
        }
        if self._last_change_time:
            attrs["last_change"] = self._last_change_time.isoformat()
        return attrs
