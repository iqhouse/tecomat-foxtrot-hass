from __future__ import annotations

import re
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN, CONTACT_BASE


def _is_numeric_like(s: str) -> bool:
    if s is None:
        return True
    t = str(s).strip()
    if not t:
        return True
    t = t.replace(",", ".")
    try:
        float(t)
        return True
    except ValueError:
        return False


def _context_from_plc_base(plc_base: str) -> str:
    parts = (plc_base or "").split(".")
    if not parts:
        return ""
    last = parts[-1].upper()
    if last.startswith("GTSAP1") and len(parts) >= 2:
        return parts[-2]
    return parts[-1]


def _extract_number(base: str) -> str:
    m = re.search(r"_CONTACT(\d+)$", (base or ""), flags=re.IGNORECASE)
    return m.group(1) if m else ""


def _fallback_name(base: str, plc_base: str) -> str:
    ctx = _context_from_plc_base(plc_base).replace("_", " ").strip().title()
    num = _extract_number(base)
    if ctx and num:
        return f"{ctx} Kontakt {num}"
    if ctx:
        return f"{ctx} Kontakt"
    return f"Kontakt {num}".strip() if num else "Kontakt"


def _discover(client):
    items = []
    for var in client.variables:
        if not var.lower().endswith(f"{CONTACT_BASE.lower()}_state"):
            continue
        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit("_CONTACT", 1)[0] if "_CONTACT" in base.upper() else base
        items.append((var, base, plc_base))
    items.sort(key=lambda x: (x[2] or x[1]).lower())
    return items


def get_required_var_names(client) -> list[str]:
    out: list[str] = []
    for state_var, base, _plc_base in _discover(client):
        out.append(client.resolve_var(f"{base}_name"))
        out.append(client.resolve_var(state_var))
    return out


async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entry_id = entry.entry_id

    candidates = _discover(client)
    values = entry_data.get("initial_values_binary_sensor") or []

    entities = []
    i = 0
    for state_var, base, plc_base in candidates:
        if i + 2 > len(values):
            break

        name_raw = (values[i] or "").strip()
        state_raw = (values[i + 1] or "").strip()
        i += 2

        name = name_raw if name_raw and not _is_numeric_like(name_raw) else _fallback_name(base, plc_base)
        initial_state = state_raw in ("1", "true", "TRUE")

        entities.append(TecomatBinarySensor(name, client, base, state_var, initial_state, entry_id))

    async_add_entities(entities)


class TecomatBinarySensor(BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, name, client, base, state_var, initial_state, entry_id):
        self._attr_name = name
        self._client = client
        self._state_var = self._client.resolve_var(state_var)

        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{base}_state"
        self._attr_is_on = initial_state
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._client.register_value_entity(self._state_var, self._on_diff_value)

    def _on_diff_value(self, raw_value: str) -> None:
        self._attr_is_on = (raw_value or "").strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._state_var)