from __future__ import annotations

import re
from datetime import datetime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from .const import DOMAIN, BUTTON_BASE


def _slugify_plc_id(plc_id: str) -> str:
    s = (plc_id or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _to_int(raw: str) -> int:
    try:
        return int((raw or "").strip())
    except (ValueError, TypeError):
        return 0


def _build_button_index(client):
    click_suf = f"{BUTTON_BASE.lower()}_clickcnt"
    press_suf = f"{BUTTON_BASE.lower()}_presscnt"
    name_suf = f"{BUTTON_BASE.lower()}_name"

    idx = {}
    for var in client.variables:
        v = var.lower()
        if not (v.endswith(click_suf) or v.endswith(press_suf) or v.endswith(name_suf)):
            continue

        parts = var.rsplit(".", 1)
        base = parts[0] if len(parts) == 2 else var.rsplit("_", 1)[0]
        if base.upper().endswith("_" + BUTTON_BASE):
            base = base.rsplit("_", 1)[0]

        rec = idx.setdefault(base, {})
        if v.endswith(click_suf):
            rec["click"] = var
        elif v.endswith(press_suf):
            rec["press"] = var
        elif v.endswith(name_suf):
            rec["name"] = var

    out = []
    for base, rec in idx.items():
        if "click" in rec and "press" in rec:
            out.append((base, rec))
    out.sort(key=lambda x: x[0].lower())
    return out


def get_required_var_names(client) -> list[str]:
    out = []
    for _base, rec in _build_button_index(client):
        name_var = rec.get("name") or rec["click"]
        out.extend([name_var, rec["click"], rec["press"]])
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entry_id = entry.entry_id
    entities = []

    buttons = _build_button_index(client)
    values = entry_data.get("initial_values_event") or []
    idx = 0

    for base, rec in buttons:
        if idx + 3 > len(values):
            break

        name_raw, click_raw, press_raw = values[idx], values[idx + 1], values[idx + 2]
        idx += 3

        plc_base = base.split(".")[-1] if "." in base else base
        slug = _slugify_plc_id(plc_base)

        name = (name_raw or "").strip()
        if not name:
            name = plc_base

        entities.append(TecomatButtonSensor(
            hass=hass,
            name=f"{name} Click",
            client=client,
            plc_base=plc_base,
            counter_var=rec["click"],
            initial_count=_to_int(click_raw),
            entry_id=entry_id,
            suggested_entity_id=f"sensor.{slug}_click",
            sensor_type="click",
        ))
        entities.append(TecomatButtonSensor(
            hass=hass,
            name=f"{name} Press",
            client=client,
            plc_base=plc_base,
            counter_var=rec["press"],
            initial_count=_to_int(press_raw),
            entry_id=entry_id,
            suggested_entity_id=f"sensor.{slug}_press",
            sensor_type="press",
        ))

    if entities:
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
        sensor_type: str,
    ):
        self.hass = hass
        self._attr_name = name
        self._client = client
        self._plc_base = plc_base
        self._counter_var = counter_var
        self._sensor_type = sensor_type

        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{plc_base}_{sensor_type}"  # ponechané
        self.entity_id = suggested_entity_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._prev_count = int(initial_count or 0)
        self._attr_native_value = int(initial_count or 0)
        self._last_change_time = None

        self._client.register_value_entity(self._counter_var, self._on_count_change)

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._counter_var)

    def _on_count_change(self, raw_value: str) -> None:
        try:
            new_count = _to_int(raw_value)
            if new_count != self._prev_count:
                self._attr_native_value = new_count
                if new_count > self._prev_count:
                    self._last_change_time = datetime.now()
                self._prev_count = new_count
                self.async_write_ha_state()
        except Exception:
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