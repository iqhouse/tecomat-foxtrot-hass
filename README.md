# Tecomat Foxtrot Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Home Assistant integrácia pre Tecomat Foxtrot PLC zariadenia cez PLCComS protokol.

## Funkcie

Táto integrácia poskytuje podporu pre:

- **Senzory** - Teplota, vlhkosť, osvetlenie, CO2, CO a všeobecné DISPLAY senzory
- **Binárne senzory** - Kontaktné senzory (CONTACT)
- **Prepínače** - Zásuvky (SOCKET)
- **Svetlá** - On/Off, stmievače a tunable white svetlá (LIGHT)
- **Žalúzie** - Ovládanie žalúzií a rolet (OPENER)
- **Termostaty** - Ovládanie kúrenia/chladenia (THERMOSTAT)
- **Button senzory** - Sledovanie klikov a stlačení tlačidiel (CLICK/PRESS)

## Inštalácia

### HACS (odporúčané)

1. Otvorte HACS v Home Assistant
2. Prejdite na **Integrations**
3. Kliknite na **⋮** (tri bodky) v pravom hornom rohu
4. Vyberte **Custom repositories**
5. Pridajte repozitár:
   - Repository: `https://github.com/repka/tecomat-foxtrot-hass`
   - Category: **Integration**
6. Nájdite **Tecomat Foxtrot** v HACS a nainštalujte
7. Reštartujte Home Assistant

### Manuálna inštalácia

1. Stiahnite si najnovšiu verziu z [releases](https://github.com/repka/tecomat-foxtrot-hass/releases)
2. Skopírujte priečinok `tecomat_foxtrot` do `custom_components` vo vašom Home Assistant
3. Reštartujte Home Assistant

## Konfigurácia

1. Prejdite do **Settings** → **Devices & Services**
2. Kliknite na **Add Integration**
3. Vyhľadajte **Tecomat Foxtrot**
4. Zadajte IP adresu a port PLC zariadenia (predvolený port: 5010)
5. Integrácia sa automaticky pripojí a načíta všetky dostupné entity

## Podporované entity

### Senzory

Integrácia automaticky detekuje a vytvára senzory z DISPLAY blokov v PLC:

- **Teplota** - Teplotné senzory s jednotkou °C
- **Vlhkosť** - Senzory vlhkosti v %
- **Osvetlenie** - Lux senzory
- **CO2** - Senzory CO2
- **CO** - Senzory CO
- **Všeobecné** - Ďalšie numerické senzory

### Binárne senzory

- **Kontakty** - Binárne stavy z CONTACT blokov

### Prepínače

- **Zásuvky** - Ovládanie zásuviek cez SOCKET bloky

### Svetlá

- **On/Off** - Jednoduché zapínanie/vypínanie
- **Stmievače** - Ovládanie jasu
- **Tunable White** - Ovládanie teploty farby

### Žalúzie

- **Ovládanie** - Ovládanie žalúzií a rolet cez OPENER bloky

### Termostaty

- **Kúrenie/Chladenie** - Ovládanie termostatov s podporou rôznych režimov

### Button senzory

Pre každú BUTTON premennú v PLC sa vytvoria dva senzory:

- **Click senzor** - Sleduje počet krátkych klikov (`sensor.{button_name}_click`)
- **Press senzor** - Sleduje počet dlhých stlačení (`sensor.{button_name}_press`)

Každý senzor obsahuje:
- Aktuálny počet stlačení (hodnota senzora)
- Atribúty: `count`, `plc_base`, `sensor_type`, `last_change`

## Automatizácie

### Príklad: Reakcia na klik tlačidla

```yaml
automation:
  - alias: "Button Click Action"
    trigger:
      platform: state
      entity_id: sensor.testbutton_click
    action:
      - service: light.toggle
        target:
          entity_id: light.example_light
```

### Príklad: Reakcia na stlačenie tlačidla

```yaml
automation:
  - alias: "Button Press Action"
    trigger:
      platform: state
      entity_id: sensor.testbutton_press
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.long_press_scene
```

## Technické detaily

### PLCComS protokol

Integrácia používa PLCComS TCP protokol pre komunikáciu s PLC zariadením:
- Push notifikácie zmien (DIFF)
- Automatické znovupripojenie pri strate spojenia
- Detekcia reštartu PLC a automatické znovunačítanie entít

### Podporované PLC bloky

- `GTSAP1_DISPLAY` - Senzory
- `GTSAP1_CONTACT` - Binárne senzory
- `GTSAP1_SOCKET` - Prepínače
- `GTSAP1_LIGHT` - Svetlá
- `GTSAP1_OPENER` - Žalúzie
- `GTSAP1_THERMOSTAT` - Termostaty
- `GTSAP1_BUTTON` - Tlačidlá

## Riešenie problémov

### Integrácia sa nepripojí

1. Skontrolujte, či je PLC zapnuté a dostupné v sieti
2. Overte IP adresu a port (predvolený port: 5010)
3. Skontrolujte firewall nastavenia
4. Pozrite sa do logov Home Assistant pre detailnejšie chybové hlásenia

### Entity sa nezobrazujú

1. Skontrolujte, či sú v PLC správne nakonfigurované bloky
2. Overte, či názvy premenných zodpovedajú očakávanému formátu
3. Reštartujte integráciu v Settings → Devices & Services

### Button senzory sa nevytvárajú

1. Skontrolujte, či existujú premenné `GTSAP1_BUTTON_CLICKCNT` a `GTSAP1_BUTTON_PRESSCNT`
2. Overte, či sú premenné správne pomenované podľa konvencie PLC

## Podpora

- **Issues**: [GitHub Issues](https://github.com/repka/tecomat-foxtrot-hass/issues)
- **Dokumentácia**: [README](https://github.com/repka/tecomat-foxtrot-hass#readme)

## Licencia

Tento projekt je licencovaný pod MIT licenciou - pozri [LICENSE](LICENSE) súbor pre detaily.

## Autor

Ing. Michal Repka (iQ House, s.r.o.)

---

**Poznámka**: Táto integrácia nie je oficiálne podporovaná spoločnosťou Teco a.s. Je to neoficiálna komunita podporovaná integrácia.
