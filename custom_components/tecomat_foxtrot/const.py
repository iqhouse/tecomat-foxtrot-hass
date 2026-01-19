"""Constants for Tecomat Foxtrot."""

DOMAIN = "tecomat_foxtrot"
CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 5010

# Zoznam všetkých platforiem (pridaný cover)
PLATFORMS = ["sensor", "binary_sensor", "switch", "light", "cover", "climate"]

# fb_iSensorTemp identifikácia (DISPLAY_* rodina)
SENSOR_DISPLAY_TYPE_REAL = 1
SENSOR_DISPLAY_SYMBOL_GENERIC = 0
SENSOR_DISPLAY_SYMBOL_TEMP = 100
SENSOR_DISPLAY_SYMBOL_HUMIDITY = 101
SENSOR_DISPLAY_SYMBOL_LUX = 107
SENSOR_DISPLAY_SYMBOL_CO2 = 104
SENSOR_DISPLAY_SYMBOL_CO = 105

# Identifikácia premenných podľa dokumentácie blokov
DISP = "GTSAP1_DISPLAY"
CONTACT_BASE = "GTSAP1_CONTACT"
SOCKET_BASE = "GTSAP1_SOCKET"
LIGHT_BASE = "GTSAP1_LIGHT"
COVER_BASE = "GTSAP1_OPENER"
THERMOSTAT_BASE = "GTSAP1_THERMOSTAT"
BUTTON_BASE = "GTSAP1_BUTTON"

# Prihlásenie k odberu všetkých zmien v PLC
SUBSCRIBE_WILDCARD = "EN:*"

# Kódovanie textov (Windows-1250 pre CZ/SK diakritiku)
ENCODING = "cp1250"

# Nastavenia pre znovupripojenie (sekundy)
RECONNECT_MIN_DELAY = 2
RECONNECT_MAX_DELAY = 30