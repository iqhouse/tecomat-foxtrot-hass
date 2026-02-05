from __future__ import annotations

import re
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN, SOCKET_BASE

RELAY_BASE = "GTSAP1_RELAY"


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


def _extract_number(base: str, kind: str) -> str:
    m = re.search(rf"_{kind}(\d+)$", (base or ""), flags=re.IGNORECASE)
    return m.group(1) if m else ""


def _fallback_name(base: str, plc_base: str, switch_type: str) -> str:
    ctx = _context_from_plc_base(plc_base).replace("_", " ").strip().title()
    if switch_type == "socket":
        num = _extract_number(base, "SOCKET")
        return f"{ctx} Zásuvka {num}".strip() if ctx else f"Zásuvka {num}".strip()
    num = _extract_number(base, "RELAY")
    return f"{ctx} Relé {num}".strip() if ctx else f"Relé {num}".strip()


def _discover(client):
    items = []
    for var in client.variables:
        v_low = var.lower()
        is_socket = v_low.endswith(f"{SOCKET_BASE.lower()}_onoff")
        is_relay = v_low.endswith(f"{RELAY_BASE.lower()}_onoff")
        if not (is_socket or is_relay):
            continue

        base = var.rsplit("_", 1)[0]
        suffix = "_SOCKET" if is_socket else "_RELAY"
        plc_base = base.rsplit(suffix, 1)[0] if suffix in base.upper() else base
        items.append((var, base, plc_base, "relay" if is_relay else "socket"))

    items.sort(key=lambda x: (x[2] or x[1]).lower())
    return items


def get_required_var_names(client) -> list[str]:
    out: list[str] = []
    for state_var, base, _plc_base, _stype in _discover(client):
        out.append(client.resolve_var(f"{base}_name"))
        out.append(client.resolve_var(state_var))
    return out


async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entry_id = entry.entry_id

    candidates = _discover(client)
    values = entry_data.get("initial_values_switch") or []

    entities = []
    i = 0
    for state_var, base, plc_base, stype in candidates:
        if i + 2 > len(values):
            break

        name_raw = (values[i] or "").strip()
        state_raw = (values[i + 1] or "").strip()
        i += 2

        name = name_raw if name_raw and not _is_numeric_like(name_raw) else _fallback_name(base, plc_base, stype)
        initial_state = state_raw in ("1", "true", "TRUE")

        entities.append(
            TecomatSwitch(
                name=name,
                client=client,
                base=base,
                state_var=state_var,
                initial_state=initial_state,
                switch_type=stype,
                entry_id=entry_id,
            )
        )

    async_add_entities(entities)


class TecomatSwitch(SwitchEntity):
    _attr_should_poll = False

    def __init__(self, name, client, base, state_var, initial_state, switch_type, entry_id):
        self._attr_name = name
        self._client = client
        self._state_var = self._client.resolve_var(state_var)

        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{base}_{switch_type}"
        self._attr_is_on = initial_state
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._client.register_value_entity(self._state_var, self._on_diff_value)

    def _on_diff_value(self, raw_value: str) -> None:
        self._attr_is_on = (raw_value or "").strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._client.async_set(self._state_var, "1")

    async def async_turn_off(self, **kwargs):
        await self._client.async_set(self._state_var, "0")

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._state_var)