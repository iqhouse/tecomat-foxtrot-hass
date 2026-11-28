from __future__ import annotations

from homeassistant.components.cover import (
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from homeassistant.exceptions import HomeAssistantError

from .const import COVER_BASE, DOMAIN


JALOUSIE_TYPE = 10


def _discover_covers(client):
    candidates = []
    seen = set()
    for var in client.variables:
        if not var.lower().endswith(f"{COVER_BASE.lower()}_current"):
            continue
        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit("_OPENER", 1)[0] if "_OPENER" in base.upper() else base
        key = plc_base.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((var, base, plc_base))
    return candidates


def get_required_var_names(client) -> list[str]:
    known = {var.lower() for var in client.variables}
    out = []
    for current_var, base, _plc_base in _discover_covers(client):
        out.extend([client.resolve_var(f"{base}_name"), current_var])
        for suffix in ("type", "tiltCurrent", "moving", "referenced"):
            var = f"{base}_{suffix}"
            if var.lower() in known:
                out.append(client.resolve_var(var))
    return out


def _parse_percent(value):
    try:
        return max(0, min(100, int(float(value.strip().replace(",", ".")))))
    except (AttributeError, ValueError, OverflowError):
        return None


def _is_true(value):
    return (value or "").strip().lower() in ("1", "true")


async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    values = dict(zip(
        get_required_var_names(client),
        entry_data.get("initial_values_cover") or [],
    ))
    known = {var.lower() for var in client.variables}
    entities = []

    for current_var, base, plc_base in _discover_covers(client):
        if current_var not in values:
            continue
        name = (values.get(client.resolve_var(f"{base}_name")) or "").strip() or plc_base
        initial_pos = _parse_percent(values[current_var] or "0")
        if initial_pos is None:
            continue
        type_raw = values.get(client.resolve_var(f"{base}_type")) or ""
        is_jalousie = type_raw.strip() == str(JALOUSIE_TYPE)
        has_tilt = is_jalousie and all(
            f"{base}_{suffix}".lower() in known for suffix in ("tiltCurrent", "tiltTarget")
        )
        has_stop = is_jalousie and f"{base}_stop".lower() in known
        entities.append(
            TecomatCover(
                name,
                client,
                plc_base,
                base,
                initial_pos,
                entry.entry_id,
                is_jalousie=is_jalousie,
                has_tilt=has_tilt,
                has_stop=has_stop,
                has_reference=is_jalousie and f"{base}_reference".lower() in known,
                reference_status=(
                    values.get(client.resolve_var(f"{base}_referenced"))
                    if is_jalousie and f"{base}_referenced".lower() in known else None
                ),
                initial_tilt=_parse_percent(values.get(client.resolve_var(f"{base}_tiltCurrent"))),
                initial_moving=_is_true(values.get(client.resolve_var(f"{base}_moving"))),
            )
        )

    async_add_entities(entities)


class TecomatCover(CoverEntity):
    _attr_should_poll = False

    def __init__(
        self, name, client, plc_base, base, initial_pos, entry_id, *,
        is_jalousie=False, has_tilt=False, has_stop=False, initial_tilt=None,
        initial_moving=False, has_reference=False, reference_status=None,
    ):
        self._attr_name = name
        self._client = client
        self._is_jalousie = is_jalousie

        self._current_var = self._client.resolve_var(f"{base}_current")
        self._target_var = self._client.resolve_var(f"{base}_target")
        self._moving_var = self._client.resolve_var(f"{base}_moving")
        self._tilt_current_var = client.resolve_var(f"{base}_tiltCurrent") if has_tilt else None
        self._tilt_target_var = client.resolve_var(f"{base}_tiltTarget") if has_tilt else None
        self._stop_var = client.resolve_var(f"{base}_stop") if has_stop else None

        self._reference_var = client.resolve_var(f"{base}_reference") if has_reference else None
        self._referenced_var = (
            client.resolve_var(f"{base}_referenced") if reference_status is not None else None
        )
        self._referenced = _is_true(reference_status) if self._referenced_var else None

        self._attr_unique_id = f"{DOMAIN}:{plc_base}_opener"
        self._attr_current_cover_position = initial_pos
        self._last_position = initial_pos
        self._attr_current_cover_tilt_position = initial_tilt if has_tilt else None
        self._is_moving = initial_moving
        self._direction: str | None = None

        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        if is_jalousie:
            self._attr_device_class = CoverDeviceClass.BLIND
        elif any(x in (name or "").lower() for x in ["gate", "brana", "vrata"]):
            self._attr_device_class = CoverDeviceClass.GATE
        else:
            self._attr_device_class = CoverDeviceClass.SHUTTER

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
        )

        if not is_jalousie or self._stop_var:
            self._attr_supported_features |= CoverEntityFeature.STOP
        if self._tilt_current_var:
            self._attr_supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
            if self._stop_var:
                self._attr_supported_features |= CoverEntityFeature.STOP_TILT

    async def async_added_to_hass(self) -> None:
        self._client.register_value_entity(self._current_var, self._on_diff_pos)
        self._client.register_value_entity(self._moving_var, self._on_diff_moving)
        if self._tilt_current_var:
            self._client.register_value_entity(self._tilt_current_var, self._on_diff_tilt)

        if self._referenced_var:
            self._client.register_value_entity(self._referenced_var, self._on_diff_referenced)

    @property
    def current_cover_position(self) -> int | None:
        return None if self._referenced is False else self._attr_current_cover_position

    @property
    def current_cover_tilt_position(self) -> int | None:
        return None if self._referenced is False else self._attr_current_cover_tilt_position

    def _on_diff_referenced(self, value):
        self._referenced = _is_true(value)
        self.async_write_ha_state()

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        if position is None:
            return None
        return position <= (0 if self._is_jalousie else 1)

    @property
    def is_opening(self) -> bool:
        return self._is_moving and self._direction == "opening"

    @property
    def is_closing(self) -> bool:
        return self._is_moving and self._direction == "closing"

    def _on_diff_pos(self, value):
        new_position = _parse_percent(value)
        if new_position is None:
            return

        # The target variable is write-only. Position changes therefore also
        # determine the direction when the cover is operated outside HA.
        if self._last_position is not None:
            if new_position > self._last_position:
                self._direction = "opening"
            elif new_position < self._last_position:
                self._direction = "closing"

        self._last_position = new_position
        self._attr_current_cover_position = new_position
        self.async_write_ha_state()

    def _on_diff_tilt(self, value):
        tilt = _parse_percent(value)
        if tilt is not None:
            self._attr_current_cover_tilt_position = tilt
            self.async_write_ha_state()

    def _on_diff_moving(self, value):
        self._is_moving = _is_true(value)
        if not self._is_moving:
            self._direction = None
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs):
        if not self._is_jalousie:
            self._direction = "opening"
            self.async_write_ha_state()
        await self._async_set_height(100)

    async def async_close_cover(self, **kwargs):
        if not self._is_jalousie:
            self._direction = "closing"
            self.async_write_ha_state()
        await self._async_set_height(0)

    async def async_set_cover_position(self, **kwargs):
        pos = max(0, min(100, int(kwargs.get("position", 0))))
        current = self._attr_current_cover_position

        if not self._is_jalousie and current is not None:
            if pos > current:
                self._direction = "opening"
            elif pos < current:
                self._direction = "closing"
            else:
                self._direction = None

        self.async_write_ha_state()
        await self._async_set_height(pos)

    async def _async_set_height(self, position):
        if self._reference_var and position in (0, 100):
            await self._client.async_set(self._reference_var, "1" if position == 0 else "2")
            return
        if position not in (0, 100):
            self._require_reference()
        await self._client.async_set(self._target_var, str(position))

    def _require_reference(self):
        if self._referenced is False:
            raise HomeAssistantError(
                "Neznáma pozícia. Najskôr otvorte žalúziu do krajnej polohy."
            )

    async def async_open_cover_tilt(self, **kwargs):
        await self._async_set_tilt(100)

    async def async_close_cover_tilt(self, **kwargs):
        await self._async_set_tilt(0)

    async def async_set_cover_tilt_position(self, **kwargs):
        await self._async_set_tilt(kwargs[ATTR_TILT_POSITION])

    async def _async_set_tilt(self, position):
        if self._tilt_target_var:
            self._require_reference()
            await self._client.async_set(self._tilt_target_var, str(position))

    async def async_stop_cover_tilt(self, **kwargs):
        if self._tilt_target_var and self._stop_var:
            await self.async_stop_cover()

    async def async_stop_cover(self, **kwargs):
        if self._stop_var:
            await self._client.async_set(self._stop_var, "1")
            return
        if self._is_jalousie:
            return
        self._direction = None
        self.async_write_ha_state()
        await self._client.async_set(
            self._target_var,
            str(self._attr_current_cover_position or 0),
        )

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._current_var, self._on_diff_pos)
        self._client.unregister_value_entity(self._moving_var, self._on_diff_moving)
        if self._tilt_current_var:
            self._client.unregister_value_entity(self._tilt_current_var, self._on_diff_tilt)
        if self._referenced_var:
            self._client.unregister_value_entity(self._referenced_var, self._on_diff_referenced)
