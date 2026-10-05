# Tecomat Foxtrot pre Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-v1.0.4-blue.svg)](https://github.com/iqhouse/tecomat-foxtrot-hass/releases)

Moderná integrácia pre PLC **Tecomat Foxtrot** využívajúca protokol **PLCComS**. Navrhnutá pre vysoký výkon, stabilitu a okamžitú odozvu v slovenskom a českom prostredí.

## Hlavné prednosti
* **Asynchrónne jadro**: Postavené na `asyncio` pre minimálne zaťaženie systému a rýchly chod.
* **Okamžité aktualizácie (Push)**: Integrácia nečaká na dopytovanie (polling), ale prijíma zmeny z PLC v reálnom čase pomocou `DIFF` správ.
* **Automatická detekcia**: Systém sám rozpozná a vytvorí entity (senzory, svetlá, žalúzie, termostaty) podľa štandardných názvov v PLC.
* **Vysoká odolnosť**: Inteligentná logika opätovného pripojenia a automatická synchronizácia stavov po reštarte PLC.

## Podporované zariadenia
* 💡 **Svetlá** (Zapnúť/Vypnúť, stmievanie, RGB, nastavenie teploty bielej)
* 🔌 **Spínače** (Relé, zásuvky, pomocné pohony)
* 🏁 **Žalúzie a brány** (Presné ovládanie polohy v % a zastavenie)
* 🌡️ **Klimatizácia a kúrenie** (Kompletné termostaty s režimami Heat/Cool)
* 📉 **Senzory** (Teplota, vlhkosť, osvetlenie, CO2, CO a textové informácie)
* 🔘 **Udalosti** (Sledovanie kliknutí a dĺžky stlačenia tlačidiel)

## Inštalácia

### Cez HACS (odporúčané)
1. V Home Assistant otvorte **HACS** > **Integrácie**.
2. Vpravo hore kliknite na tri bodky a vyberte **Vlastné repozitáre** (Custom repositories).
3. Vložte adresu: `https://github.com/iqhouse/tecomat-foxtrot-hass` a zvoľte kategóriu **Integrácia**.
4. Kliknite na **Inštalovať**.
5. Reštartujte Home Assistant.

### Manuálna inštalácia
Skopírujte priečinok `custom_components/tecomat_foxtrot` do vášho adresára `config/custom_components/` a reštartujte systém.

## Konfigurácia
1. Prejdite do **Nastavenia** > **Zariadenia a služby**.
2. Kliknite na **Pridať integráciu** a vyhľadajte **Tecomat Foxtrot**.
3. Zadajte IP adresu vášho PLC a port služby PLCComS (predvolene `5010`).

---

> **Dôležité:** Podrobný technický návod na nastavenie premenných v prostredí Mosaic, schémy zapojenia a konfiguráciu PLCComS nájdete v oficiálnom **PDF manuáli**, ktorý je dodávaný k vašej inštalácii.

---

© 2026 iQ House, s.r.o.. Všetky práva vyhradené.