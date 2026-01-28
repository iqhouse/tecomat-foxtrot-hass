# Tecomat Foxtrot Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Home Assistant integrácia pre Tecomat Foxtrot PLC zariadenia cez PLCComS protokol.

## Funkcie

Táto integrácia poskytuje podporu pre:

- **Senzory** - Teplota, vlhkosť, osvetlenie, CO2, CO a všeobecné DISPLAY senzory
- **Binárne senzory** - Kontaktné senzory (CONTACT)
- **Prepínače** - Zásuvky (SOCKET) a relé (RELAY)
- **Svetlá** - On/Off, stmievače, RGB a tunable white svetlá (LIGHT)
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
   - Repository: `https://github.com/iqhouse/tecomat-foxtrot-hass`
   - Category: **Integration**
6. Nájdite **Tecomat Foxtrot** v HACS a nainštalujte
7. Reštartujte Home Assistant

### Manuálna inštalácia

1. Stiahnite si najnovšiu verziu z [releases](https://github.com/iqhouse/tecomat-foxtrot-hass/releases)
2. Skopírujte priečinok `custom_components/tecomat_foxtrot` do vášho Home Assistant konfiguračného priečinka
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
- **Všeobecné** - Ďalšie numerické senzory s nastaviteľnou presnosťou

### Binárne senzory

- **Kontakty** - Binárne stavy z CONTACT blokov (dvere, okná, detektory pohybu, atď.)

### Prepínače

- **Zásuvky** - Ovládanie zásuviek cez SOCKET bloky
- **Relé** - Ovládanie relé cez RELAY bloky

### Svetlá

Podpora pre rôzne typy osvetlenia:

- **On/Off** - Jednoduché zapínanie/vypínanie
- **Stmievače** - Ovládanie jasu (0-100%)
- **RGB** - Farebné svetlá s plnou RGB paletou
- **Tunable White** - Ovládanie teploty farby (2000-6500K)

### Žalúzie

- **Ovládanie pozície** - Presné nastavenie pozície (0-100%)
- **Otvorenie/Zatvorenie** - Jednoduché príkazy
- **Stop** - Zastavenie pohybu
- **Detekcia pohybu** - Indikácia, či sa žalúzia práve pohybuje

### Termostaty

Podpora pre tri typy termostatov:

- **Type 1** - Chladenie (COOL/OFF režimy)
- **Type 2** - Kúrenie (HEAT/OFF režimy)
- **Type 3** - Kombinovaný (HEAT/COOL/OFF režimy)

Funkcie:
- Nastavenie cieľovej teploty
- Zobrazenie aktuálnej teploty
- Indikácia aktívneho kúrenia/chladenia
- Min/max limitov teploty

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
  - alias: "Button Click - Toggle Light"
    trigger:
      platform: state
      entity_id: sensor.lobby_button_click
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state != trigger.from_state.state }}"
    action:
      - service: light.toggle
        target:
          entity_id: light.lobby_light
```

### Príklad: Reakcia na dlhé stlačenie

```yaml
automation:
  - alias: "Button Long Press - Activate Scene"
    trigger:
      platform: state
      entity_id: sensor.lobby_button_press
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state != trigger.from_state.state }}"
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.evening_mode
```

### Príklad: Automatické ovládanie termostatu

```yaml
automation:
  - alias: "Climate - Auto Temperature"
    trigger:
      platform: numeric_state
      entity_id: sensor.living_room_temperature
      below: 20
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room_thermostat
        data:
          temperature: 22
          hvac_mode: heat
```

## Technické detaily

### PLCComS protokol

Integrácia používa PLCComS TCP protokol pre komunikáciu s PLC zariadením:
- **Push notifikácie** - Okamžité aktualizácie pri zmene hodnôt (DIFF)
- **Automatické znovupripojenie** - Pri strate spojenia s exponenciálnym backoff (2-30s)
- **Detekcia reštartu PLC** - Automatické znovunačítanie entít po reštarte PLC
- **Kódovanie** - CP1250 pre podporu slovenských a českých znakov

### Podporované PLC bloky

Integrácia rozpoznáva tieto názvy blokov v PLC:

- `GTSAP1_DISPLAY` - Senzory (teplota, vlhkosť, CO2, atď.)
- `GTSAP1_CONTACT` - Binárne senzory (kontakty)
- `GTSAP1_SOCKET` - Prepínače (zásuvky)
- `GTSAP1_RELAY` - Prepínače (relé)
- `GTSAP1_LIGHT` - Svetlá (všetky typy)
- `GTSAP1_OPENER` - Žalúzie a rolety
- `GTSAP1_THERMOSTAT` - Termostaty
- `GTSAP1_BUTTON` - Tlačidlá

### Požiadavky

- Home Assistant 2024.1.0 alebo novší
- Tecomat Foxtrot PLC s aktivovaným PLCComS protokolom
- Sieťové pripojenie medzi Home Assistant a PLC

## Riešenie problémov

### Integrácia sa nepripojí

1. Skontrolujte, či je PLC zapnuté a dostupné v sieti
2. Overte IP adresu a port (predvolený port: 5010)
3. Skontrolujte, či je PLCComS protokol povolený na PLC
4. Skontrolujte firewall nastavenia na oboch stranách
5. Pozrite sa do logov Home Assistant pre detailnejšie chybové hlásenia:
   ```
   Settings → System → Logs
   ```

### Entity sa nezobrazujú

1. Skontrolujte, či sú v PLC správne nakonfigurované bloky s korektným názvom
2. Overte, že názvy premenných zodpovedajú konvencii (napr. `XXX_GTSAP1_LIGHT_onoff`)
3. Reštartujte integráciu v Settings → Devices & Services → Tecomat Foxtrot → ⋮ → Reload

### Button senzory sa nevytvárajú

1. Skontrolujte, či v PLC existujú premenné končiace na `GTSAP1_BUTTON_CLICKCNT` a `GTSAP1_BUTTON_PRESSCNT`
2. Overte, či sú premenné správne pomenované (case insensitive)
3. Skontrolujte logy na prípadné chyby pri inicializácii

### Svetlá nereagujú správne

1. Pre RGB svetlá overte, že existuje premenná `XXX_rgb`
2. Pre tunable white overte premenné `XXX_colortemp`, `XXX_minTempK`, `XXX_maxTempK`
3. Pre stmievače overte `XXX_dimlevel` a `XXX_tgtlevel` premenné

## Vývoj a príspevky

Príspevky sú vítané! Ak chcete prispieť:

1. Forkujte repozitár
2. Vytvorte feature branch (`git checkout -b feature/nova-funkcia`)
3. Commitnite zmeny (`git commit -am 'Pridaná nová funkcia'`)
4. Pushnite do branchu (`git push origin feature/nova-funkcia`)
5. Vytvorte Pull Request

## Podpora

- **Issues**: [GitHub Issues](https://github.com/iqhouse/tecomat-foxtrot-hass/issues)
- **Dokumentácia**: Tento README
- **Diskusie**: [GitHub Discussions](https://github.com/iqhouse/tecomat-foxtrot-hass/discussions)

## Changelog

### v0.9.5 (aktuálna)
- Prvé verejné vydanie
- Podpora pre všetky základné entity (senzory, svetlá, žalúzie, termostaty)
- Button senzory pre sledovanie klikov a dlhých stlačení
- Automatická detekcia reštartu PLC
- Push notifikácie pre všetky entity

## Licencia

Tento projekt je licencovaný pod MIT licenciou - pozri [LICENSE](LICENSE) súbor pre detaily.

## Autor

**Ing. Michal Repka**  
iQ House, s.r.o.

---

**Poznámka**: Táto integrácia nie je oficiálne podporovaná spoločnosťou Teco a.s. Je to komunitná integrácia vytvorená pre jednoduchšie prepojenie Tecomat Foxtrot zariadení s Home Assistant.

## Poďakovanie

Ďakujem komunite Home Assistant za skvelé nástroje a dokumentáciu, ktoré umožnili vytvorenie tejto integrácie.
