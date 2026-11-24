from __future__ import annotations

import re
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.event import EventEntity
from .const import DOMAIN, BUTTON_BASE

_LOGGER = logging.getLogger(__name__)


def _slugify_plc_id(plc_id: str) -> str:
    s = (plc_id or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _to_int(raw: str) -> int:
    try:
        text = str(raw or "").strip().replace(",", ".")
        return int(float(text))
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


def _is_numeric_like(value: str) -> bool:
    if not value or not str(value).strip():
        return True
    try:
        float(str(value).strip().replace(",", "."))
        return True
    except ValueError:
        return False


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

        if _is_numeric_like(name):
            name = plc_base

        entities.append(TecomatButtonEvent(
            hass=hass,
            name=name,
            client=client,
            plc_base=plc_base,
            click_counter_var=rec["click"],
            press_counter_var=rec["press"],
            initial_click_count=_to_int(click_raw),
            initial_press_count=_to_int(press_raw),
            entry_id=entry_id,
            suggested_entity_id=f"event.{slug}",
        ))

    if entities:
        async_add_entities(entities)


class TecomatButtonEvent(EventEntity):
    _attr_should_poll = False
    _attr_event_types = ["click", "press"]

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        client,
        plc_base: str,
        click_counter_var: str,
        press_counter_var: str,
        initial_click_count: int,
        initial_press_count: int,
        entry_id: str,
        suggested_entity_id: str,
    ):
        self.hass = hass
        self._attr_name = name
        self._client = client
        self._plc_base = plc_base
        self._click_counter_var = self._client.resolve_var(click_counter_var)
        self._press_counter_var = self._client.resolve_var(press_counter_var)
        self._prev_click_count = int(initial_click_count or 0)
        self._prev_press_count = int(initial_press_count or 0)

        self._attr_unique_id = f"{DOMAIN}:{entry_id}:{plc_base}"
        self.entity_id = suggested_entity_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

        self._client.register_value_entity(
            self._click_counter_var,
            self._on_click_count_change,
        )
        self._client.register_value_entity(
            self._press_counter_var,
            self._on_press_count_change,
        )

    async def async_will_remove_from_hass(self) -> None:
        self._client.unregister_value_entity(self._click_counter_var)
        self._client.unregister_value_entity(self._press_counter_var)

    def _on_click_count_change(self, raw_value: str) -> None:
        self._handle_count_change(
            raw_value,
            event_type="click",
            previous_count_attr="_prev_click_count",
        )

    def _on_press_count_change(self, raw_value: str) -> None:
        self._handle_count_change(
            raw_value,
            event_type="press",
            previous_count_attr="_prev_press_count",
        )

    def _handle_count_change(
        self,
        raw_value: str,
        event_type: str,
        previous_count_attr: str,
    ) -> None:
        try:
            new_count = _to_int(raw_value)
            previous_count = getattr(self, previous_count_attr)

            count_increased = new_count > previous_count
            pulse_started = previous_count == 0 and new_count > 0
            counter_wrapped = previous_count > 0 and new_count == 0

            if count_increased or pulse_started:
                setattr(self, previous_count_attr, new_count)
                event_attributes = {
                    "count": new_count,
                    "plc_base": self._plc_base,
                }
                self._trigger_event(event_type, event_attributes)
                self._attr_event_type = event_type
                self._attr_event_attributes = event_attributes
                self.async_write_ha_state()
                self.hass.bus.async_fire(
                    "tecomat_foxtrot_button",
                    {
                        "entity_id": self.entity_id,
                        "event_type": event_type,
                        **event_attributes,
                    },
                )
                return
            if counter_wrapped:
                setattr(self, previous_count_attr, new_count)
                return
            setattr(self, previous_count_attr, new_count)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Invalid %s counter value for button %s: %r (%s)",
                event_type,
                self._plc_base,
                raw_value,
                err,
            )
            return

    @property
    def extra_state_attributes(self):
        return {
            "plc_base": self._plc_base,
            "click_count": self._prev_click_count,
            "press_count": self._prev_press_count,
        }