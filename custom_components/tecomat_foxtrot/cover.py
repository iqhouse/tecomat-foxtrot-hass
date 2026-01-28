from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
    CoverDeviceClass,
)
from .const import DOMAIN, COVER_BASE

async def async_setup_entry(hass, entry, async_add_entities):
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]
    entities = []

    for var in client.variables:
        if not var.lower().endswith(f"{COVER_BASE.lower()}_current"):
            continue

        base = var.rsplit("_", 1)[0]
        plc_base = base.rsplit("_OPENER", 1)[0] if "_OPENER" in base.upper() else base
        
        try:
            name_raw = await client.async_get(f"{base}_name")
            name = name_raw.strip() if name_raw else plc_base
            
            raw_pos = await client.async_get(var)
            initial_pos = int(float(raw_pos.strip().replace(",", ".")))
            
            entities.append(TecomatCover(name, client, plc_base, base, initial_pos, entry.entry_id))
        except Exception as e:
            continue

    async_add_entities(entities)

class TecomatCover(CoverEntity):
    _attr_should_poll = False

    def __init__(self, name, client, plc_base, base, initial_pos, entry_id):
        self._attr_name = name
        self._client = client
        self._base = base
        self._current_var = f"{base}_current"
        self._target_var = f"{base}_target"
        self._moving_var = f"{base}_moving"
        
        self._attr_unique_id = f"{DOMAIN}:{plc_base}_opener"
        self._attr_current_cover_position = initial_pos
        self._is_moving = False
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)}
        }
        
        if any(x in name.lower() for x in ["gate", "brana", "vrata"]):
            self._attr_device_class = CoverDeviceClass.GATE
        else:
            self._attr_device_class = CoverDeviceClass.SHUTTER

        self._attr_supported_features = (
            CoverEntityFeature.OPEN | 
            CoverEntityFeature.CLOSE | 
            CoverEntityFeature.STOP | 
            CoverEntityFeature.SET_POSITION
        )

        self._client.register_value_entity(self._current_var, self._on_diff_pos)
        self._client.register_value_entity(self._moving_var, self._on_diff_moving)

    @property
    def is_closed(self) -> bool | None:
        if self._attr_current_cover_position is None:
            return None
        return self._attr_current_cover_position <= 1

    @property
    def is_opening(self) -> bool:
        return self._is_moving and self._attr_current_cover_position < 99

    @property
    def is_closing(self) -> bool:
        return self._is_moving and self._attr_current_cover_position > 1

    def _on_diff_pos(self, value):
        try:
            self._attr_current_cover_position = int(float(value.strip().replace(",", ".")))
            self.async_write_ha_state()
        except (ValueError, TypeError):
            pass

    def _on_diff_moving(self, value):
        self._is_moving = value.strip() in ("1", "true", "TRUE")
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs):
        await self._client.async_set(self._target_var, "100")

    async def async_close_cover(self, **kwargs):
        await self._client.async_set(self._target_var, "0")

    async def async_stop_cover(self, **kwargs):
        pos_to_stop = self._attr_current_cover_position
        await self._client.async_set(self._target_var, str(pos_to_stop))

    async def async_set_cover_position(self, **kwargs):
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self._client.async_set(self._target_var, str(position))

    async def async_will_remove_from_hass(self):
        self._client.unregister_value_entity(self._current_var)
        self._client.unregister_value_entity(self._moving_var)