from __future__ import annotations

import re
from typing import Any

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_COLOR_TEMP_KELVIN,
)

from .const import DOMAIN, LIGHT_BASE


def _to_float(raw: str, default: float = 0.0) -> float:
    try:
        return float((raw or "").strip().replace(",", "."))
    except Exception:
        return default


def _is_truthy(raw: str) -> bool:
    return (raw or "").strip() in ("1", "true", "TRUE")


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


def _extract_light_number(base: str) -> str:
    m = re.search(r"_LIGHT(\d+)$", (base or ""), flags=re.IGNORECASE)
    return m.group(1) if m else ""


def _fallback_name(base: str, plc_base: str) -> str:
    ctx = _context_from_plc_base(plc_base).replace("_", " ").strip().title()
    num = _extract_light_number(base)
    if ctx and num:
        return f"{ctx} Svetlo {num}"
    if ctx:
        return f"{ctx} Svetlo"
    return f"Svetlo {num}".strip() if num else "Svetlo"


def _discover(client):
    idx: dict[str, dict[str, str]] = {}

    def ensure(base: str) -> dict[str, str]:
        k = base.upper()
        if k not in idx:
            idx[k] = {"base": base}
        return idx[k]

    for var in client.variables:
        v_up = var.upper()

        if v_up.endswith(f"{LIGHT_BASE.upper()}_ONOFF"):
            base = var.rsplit("_", 1)[0]
            ensure(base)["onoff"] = var
            continue

        for key, suf in (
            ("dimlevel", "_DIMLEVEL"),
            ("tgtlevel", "_TGTLEVEL"),
            ("rgb", "_RGB"),
            ("colortemp", "_COLORTEMP"),
        ):
            if v_up.endswith(suf):
                base = var[: -len(suf)]
                ensure(base)[key] = var
                break

    out = []
    for rec in idx.values():
        if "onoff" not in rec:
            continue

        base = rec["base"]
        plc_base = base.rsplit("_LIGHT", 1)[0] if "_LIGHT" in base.upper() else base

        out.append(
            {
                "base": base,
                "plc_base": plc_base,
                "onoff": rec["onoff"],
                "dimlevel": rec.get("dimlevel"),
                "tgtlevel": rec.get("tgtlevel"),
                "rgb": rec.get("rgb"),
                "colortemp": rec.get("colortemp"),
            }
        )

    out.sort(key=lambda d: (d["plc_base"] or d["base"]).lower())
    return out


def get_required_var_names(client) -> list[str]:
    out: list[str] = []
    for d in _discover(client):
        base = d["base"]
        out.extend(
            [
                client.resolve_var(f"{base}_type"),
                client.resolve_var(f"{base}_dimtype"),
                client.resolve_var(f"{base}_name"),
                client.resolve_var(d["onoff"]),
                client.resolve_var(d.get("dimlevel") or f"{base}_dimlevel"),
                client.resolve_var(d.get("rgb") or f"{base}_rgb"),
                client.resolve_var(d.get("colortemp") or f"{base}_colortemp"),
                client.resolve_var(f"{base}_minTempK"),
                client.resolve_var(f"{base}_maxTempK"),
            ]
        )
    return out


async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entry_id = entry.entry_id

    lights = _discover(client)
    values = entry_data.get("initial_values_light") or []

    entities = []
    i = 0

    for d in lights:
        if i + 9 > len(values):
            break

        chunk = values[i : i + 9]
        i += 9

        base = d["base"]
        plc_base = d["plc_base"]

        raw_type = (chunk[0] or "").strip()
        is_dimmable = raw_type in ("1", "true", "TRUE")

        dimtype = int(_to_float(chunk[1], 0.0)) if is_dimmable else 0

        name_raw = (chunk[2] or "").strip()
        name = name_raw if name_raw and not _is_numeric_like(name_raw) else _fallback_name(base, plc_base)

        initial_on = _is_truthy(chunk[3])

        initial_brightness = None
        initial_rgb = None
        initial_temp = None

        min_temp = int(_to_float(chunk[7], 2000.0))
        max_temp = int(_to_float(chunk[8], 6500.0))

        if is_dimmable:
            dim_pct = _to_float(chunk[4], 0.0)
            initial_brightness = int((dim_pct / 100.0) * 255)

            if dimtype == 1:
                initial_rgb = int(_to_float(chunk[5], 0.0))
            elif dimtype == 2:
                initial_temp = int(_to_float(chunk[6], 0.0))

        entities.append(
            TecomatLight(
                name=name,
                client=client,
                base=base,
                is_dimmable=is_dimmable,
                dimtype=dimtype,
                initial_on=initial_on,
                initial_brightness=initial_brightness,
                initial_rgb=initial_rgb,
                initial_temp=initial_temp,
                min_temp=min_temp,
                max_temp=max_temp,
                dimlevel_var=d.get("dimlevel"),
                tgtlevel_var=d.get("tgtlevel"),
                rgb_var=d.get("rgb"),
                temp_var=d.get("colortemp"),
                entry_id=entry_id,
            )
        )

    async_add_entities(entities)


class TecomatLight(LightEntity):
    _attr_should_poll = False

    def __init__(
        self,
        name: str,
        client,
        base: str,
        is_dimmable: bool,
        dimtype: int,
        initial_on: bool,
        initial_brightness: int | None,
        initial_rgb: int | None,
        initial_temp: int | None,
        min_temp: int,
        max_temp: int,
        dimlevel_var: str | None,
        tgtlevel_var: str | None,
        rgb_var: str | None,
        temp_var: str | None,
        entry_id: str,
    ):
        self._attr_name = name
        self._client = client
        self._base = base
        self._dimtype = dimtype
        self._is_dimmable = is_dimmable

        self._state_var = self._client.resolve_var(f"{base}_onoff")
        self._dimlevel_var = self._client.resolve_var(dimlevel_var or f"{base}_dimlevel")
        self._tgtlevel_var = self._client.resolve_var(tgtlevel_var or f"{base}_tgtlevel")
        self._rgb_var = self._client.resolve_var(rgb_var or f"{base}_rgb")
        self._temp_var = self._client.resolve_var(temp_var or f"{base}_colortemp")

        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{base}_light"
        self._attr_is_on = initial_on
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._attr_min_color_temp_kelvin = min_temp
        self._attr_max_color_temp_kelvin = max_temp

        self._is_closing = False
        self._last_brightness = initial_brightness if initial_brightness and initial_brightness > 0 else 255

        if not is_dimmable:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
        elif dimtype == 1:
            self._attr_color_mode = ColorMode.RGB
            self._attr_supported_color_modes = {ColorMode.RGB}
            if initial_rgb is not None:
                self._attr_rgb_color = (
                    initial_rgb & 0xFF,
                    (initial_rgb >> 8) & 0xFF,
                    (initial_rgb >> 16) & 0xFF,
                )
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

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._state_var)
        if self._is_dimmable:
            self._client.unregister_value_entity(self._dimlevel_var)
            if self._dimtype == 1:
                self._client.unregister_value_entity(self._rgb_var)
            elif self._dimtype == 2:
                self._client.unregister_value_entity(self._temp_var)

    def _on_diff_state(self, value: str) -> None:
        new_state = _is_truthy(value)
        self._is_closing = not new_state
        self._attr_is_on = new_state
        self.async_write_ha_state()

    def _on_diff_dim(self, value: str) -> None:
        dim_pct = _to_float(value, 0.0)
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

    def _on_diff_rgb(self, value: str) -> None:
        try:
            rgb_int = int(_to_float(value, 0.0))
        except Exception:
            return
        self._attr_rgb_color = (
            rgb_int & 0xFF,
            (rgb_int >> 8) & 0xFF,
            (rgb_int >> 16) & 0xFF,
        )
        self.async_write_ha_state()

    def _on_diff_temp(self, value: str) -> None:
        try:
            self._attr_color_temp_kelvin = int(_to_float(value, 0.0))
        except Exception:
            return
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_closing = False

        if ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            dim_pct = (brightness / 255.0) * 100.0

            if brightness <= 0:
                self._is_closing = True
                await self._client.async_set(self._state_var, "0")
                return

            self._last_brightness = brightness
            target_v = self._tgtlevel_var if self._dimtype == 0 else self._dimlevel_var
            await self._client.async_set(target_v, f"{dim_pct:.1f}")

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            await self._client.async_set(self._temp_var, str(int(kwargs[ATTR_COLOR_TEMP_KELVIN])))

        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            rgb_int = (int(r) & 0xFF) | ((int(g) & 0xFF) << 8) | ((int(b) & 0xFF) << 16)
            await self._client.async_set(self._rgb_var, str(rgb_int))

        await self._client.async_set(self._state_var, "1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_closing = True
        await self._client.async_set(self._state_var, "0")