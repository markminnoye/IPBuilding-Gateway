# Jan Nolf — restore-test + gateway-log (2026-08-08)

Last updated: 2026-08-08

**Bron:** Spark mail van Jan Nolf (`jan@nolfvdh.be`)  
- `112379` — RE: moduleschets / restore-resultaat + log + WebUI-screenshots (08:37)  
- `112394` — kleine update op Mark’s stappenplan (11:25) + HA-screenshot dimmer  
Subject: *RE: integratie IPBuilding in HA — moduleschets, EEPROM’s & WebUI*  
Thread: [Spark](https://sparkmailapp.com/dpl/bl?token=QTptYXJrQHNvbmljcm9ja2V0LmJlO0lEOjQ0M2Q5OWVmLTUxN2MtNDVkOS04ZmVj%0D%0ALTY5NTExZjYyYmY3N0BTcGFyaztnSUQ6MTg3MjgwMzA1ODE5NDMyMTg4ODs0Mjc1%0D%0ANTUyMTY4)

**Assets:** [assets/2026-08-08_jan_nolf_restore_test/](assets/2026-08-08_jan_nolf_restore_test/)  
Log: `3059e002_ipbuilding_gateway_2026-08-08T06-36-58.965Z.log` (1000 regels, ringbuffer)  
OCR: `ocr_image00*.txt` · mailtekst: `jan_feedback_112379.txt`

**Voorafgaand:** [2026-08-06_jan_nolf_moduleschets_feedback.md](2026-08-06_jan_nolf_moduleschets_feedback.md) · config [`devices.nolf.json`](../reference/devices.nolf.json)

---

## 1. Antwoord van Jan (samenvatting)

### 1.1 Mail `112379` (08:37)

| Observatie | Status |
|------------|--------|
| Relaisuitgangen aanstuurbaar vanuit HA | ✅ werkt |
| Dimmers zichtbaar in HA | ✅ |
| Dimfunctie (uit / dimmen na aanzetten) | ❌ faalt — “licht aanzetten lukt, daarna niet meer uit of gedimd” |
| Drukknoppen zichtbaar | ✅ na update naar **gateway 1.6.2** |
| WebUI-screenshots na restore | ✅ bijgevoegd (6 PNG) |
| Add-on log | ✅ bijgevoegd |

### 1.2 Mail `112394` (11:25) — update op stappenplan

| Stap | Jan |
|------|-----|
| 1 Restore + 1.6.2 + entities zichtbaar | ✅ “Gelukt, alles lijkt zichtbaar” |
| 2 Passief testen relays + dimmer | Relays ✅ aanstuurbaar; **status in HA wordt niet bijgewerkt** → geen toggle, alleen switch. Dimmers ❌ (zelfde als eerder) |
| 3 Evalueren passief vs actief | Wil IPBox eruit: “Als de ipbox er tussenuit kan, graag!” |
| 4 Actief later | Genoteerd |

Screenshot `image007_ha_dimmer.png`: HA-geschiedenis **Ledverlichting keuken** — state grotendeels **Onbekend**; activity `08:18:16` / `08:39:33` “Is niet meer beschikbaar” (valt samen met gateway-restarts in de log).

---

## 2. WebUI na restore (screenshots)

Restore van `devices.nolf.json` is gelukt — namen/rooms matchen de config van 2026-08-06:

| Shot | Module | Inhoud |
|------|--------|--------|
| `image001` | `.30` relay | ch0–12 actief (o.a. Bediening poort, Verlichting bureau Jan, …) — header toont nog **v1.6.0** (pre-upgrade shot) |
| `image002` | `.30` rest + `.31` | ch13–23 `.30`; `.31` ch0–2 *Ongebruikt* / inactive |
| `image003` | `.32` + start `.42` | ch0 *TL tuinhuis*; ch1–7 unused |
| `image004` | `.42` dimmer | 4 kanalen: Zithoek, Lichtstraat, Badkamer, Slaapkamer (allen active, 200 W) |
| `image005`–`006` | `.55` input | pushbuttons zichtbaar (IP1100, label **Slave**); o.a. Verlichting bureau Jan / Sara |

---

## 3. Log-tijdlijn (vandaag 2026-08-08)

Add-on instance `3059e002` / `1258f4ac408845bc90f66d336842fcf3`.  
Log is een **1000-regel ringbuffer** (begint mid-stream 27-jul `19:11`, eindigt vandaag `08:34`).

| Tijd | Event |
|------|--------|
| 07:41 | Boot **v1.6.0**, `hub_role=slave`, install zonder `.31` (oude 4-module config) |
| 07:44:17 | `POST /api/v1/devices/reset` |
| 07:44:29 | `POST /api/v1/devices/import` → **5 modules**; devices-JSON ~11.7 KB |
| 07:45:33 | AtomicWriter: **5 modules, 60 pushbuttons** (full nolf-config) |
| 08:10 | Restart nog op **v1.6.0** met volle install incl. `.31`; enkele relay status-poll timeouts op ch0/9/10 |
| **08:18** | Boot **v1.6.2** — zelfde install; **alle 4 dimmer status-polls timeout** |
| 08:18:16 | Companion reconnect: `/api/v1/devices` → **21 KB** (knoppen mee); WS connected |
| 08:18–08:34 | WebUI refreshes; geen verdere dimmer STATE-updates in log |

Startup-banner (na 1.6.2):

```
IPBuilding Gateway v1.6.2  …  buttons_via_ha=True  hub_role=slave
install=relay@10.10.1.30, relay@10.10.1.31, relay@10.10.1.32, dimmer@10.10.1.42, input@10.10.1.55
```

---

## 4. Log-bevindingen (dimmerprobleem)

### 4.1 Dimmer `.42` — geen antwoord op status-poll

Na 1.6.2-boot:

```
08:18:13 WARNING gateway.state_poll  Dimmer status poll 10.10.1.42 ch0: no reply within timeout
08:18:14 WARNING gateway.state_poll  Dimmer status poll 10.10.1.42 ch1: no reply within timeout
08:18:14 WARNING gateway.state_poll  Dimmer status poll 10.10.1.42 ch2: no reply within timeout
08:18:15 WARNING gateway.state_poll  Dimmer status poll 10.10.1.42 ch3: no reply within timeout
```

Geen latere `STATE … 10.10.1.42` of “seeded N%” in dit logvenster.  
Gateway stuurt `encode_dimmer_status_poll` (`I{ch}000000`) — zelfde formaat als IPBox Action-log van Jan ([2026-08-05](2026-08-05_jan_nolf_ipbuilding_03.07_debug_actions.md)). Op **zijn** module komt hier geen reply binnen (timeout).

### 4.2 Geen command-timeouts zichtbaar voor dimmer

In deze 1000 regels: **geen** `command … timed out` / WS DIM/OFF-fouten.  
Jan’s “aan gaat, uit/dim niet” zit dus **niet** als expliciete command-failure in dit fragment — wel als structureel “module antwoordt niet op status-poll”. Mogelijke oorzaken (niet exclusief):

1. **Oudere 0-10V-module** (faceplate “8x 0-10 VOLT OUTPUTMODULE”, geen module-HTTP) — command/reply-semantiek wijkt af van lab-IP0300PoE `.40`.
2. **`hub_role=slave`** — IPBox blijft master op de veldbus; concurrentie/filter op wie replies krijgt.
3. Optimistic ON in HA (entity state) terwijl wire-OFF/DIM faalt of geen ack krijgt — zonder command-log niet te bewijzen uit dit bestand alleen.

### 4.3 Relays — wel bereikbaar

Status-poll seedt meerdere kanalen (`off` / `unknown`/`0015`). Past bij Jan’s “relais aanstuurbaar vanuit HA”.

### 4.4 Input `.55`

- ARP: `00:24:77:06:70:ba` @ `10.10.1.55` (bekend).
- HTTP `getSysSet` blijft falen (verwacht op oudere generatie).
- Pushbuttons komen uit **imported config**, niet uit module-HTTP — zichtbaar na 1.6.2 zoals beloofd.

### 4.5 Ruis in log (niet blocker)

Veel `HTTP identify 10.10.1.x: getSysSet failed` van eerdere forced-discovery sweeps (lege subnet). Geen ERROR-level regels in dit venster.

---

## 5. Statuscodes per kanaal (voor check met Jan)

Bron: startup status-poll in log bij boot **08:18** (gateway **v1.6.2**).  
Mapping gateway **v1.6.2 (deze log):** `0000`→off, `0100`→on, **alles anders**→`unknown` (HA toont Onbekend; toggle onbetrouwbaar).
Mapping gateway **≥1.6.4:** `00xx`→off, `01xx`→on (prefix-hypothese). Ruwe `state_code` blijft in API/logs. Dimmer `.42` ongewijzigd (geen poll-reply).

**In deze hele log: nergens `0100` (on).** Wel `0000`, `0015`, één× `0115`.

### 5.1 Relays `.30` / `.32` (actieve kanalen)

| IP | Ch | Naam | `state_code` | HA state |
|----|----|------|--------------|----------|
| `.30` | 0 | Bediening poort | `0000` | off |
| `.30` | 1 | Verlichting trap | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 2 | Verlichting kamer j&s | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 3 | Verlichting kamer 1 | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 4 | Verlichting zolder | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 5 | Verlichting voordeur kant wc | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 6 | Ledverlichting keuken | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 7 | Verlichting keuken | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 8 | Verlichting eetplaats | `0000` | off |
| `.30` | 9 | Verlichting bureau Jan | `0000` | off |
| `.30` | 10 | Verlichting berging | `0000` | off |
| `.30` | 11 | Verlichting kamer 2 | `0000` | off |
| `.30` | 12 | Spots terras | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 13 | Verlichting bureau Sara | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 14 | Verlichting toilet | `0115` | unknown → **on** (≥1.6.4) |
| `.30` | 15 | Verlichting voordeur kant links | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 17 | Verlichting keukenpilaar | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 18 | Wandverlichting boven | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 19 | Verlichting voordeur buiten | `0000` | off |
| `.30` | 20 | Ventilatie toilet beneden | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 21 | Inbouwspot achterdeur | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 22 | Verstraler oversteek | `0015` | unknown → **off** (≥1.6.4) |
| `.30` | 23 | Verlichting garage | `0015` | unknown → **off** (≥1.6.4) |
| `.32` | 0 | TL tuinhuis | `0000` | off |

`.31` + ongebruikte kanalen: `active: false` → niet gepolled.  
Codes **stabiel** over boots 07:41 / 08:10 / 08:18 (zelfde kanaal → zelfde code).

### 5.2 Dimmers `.42`

| Ch | Naam | Resultaat |
|----|------|-----------|
| 0 | Zithoek | **geen reply** (timeout) |
| 1 | Lichtstraat | **geen reply** |
| 2 | Badkamer | **geen reply** |
| 3 | Slaapkamer | **geen reply** |

Geen `state_code` — module antwoordt niet op status-poll.

### 5.3 Vragen aan Jan

1. Klopt het dat kanalen met `0000` (bureau Jan, eetplaats, berging, …) op dat moment **uit** stonden?
2. Wat was de echte stand van bv. *Ledverlichting keuken* / *trap* (`0015`)? Aan, uit, of wisselend?
3. *Verlichting toilet* (`0115`) — toevallig aan op dat moment?
4. Bevestiging: in HA blijven vooral de `0015`/`0115`-kanalen op **Onbekend** (zoals zijn screenshot keuken LED)?

Als (4) klopt: ja — in **v1.6.2** is dat precies waarom hij geen betrouwbare status/toggle in HA ziet. Schakelen kan nog wel; state-feedback faalt.

### 5.4 Decoder-update 2026-08-23 (gateway 1.6.4)

`relay_state_from_code` mapt nu prefix `00`→off en `01`→on. Companion ongewijzigd: als de gateway `off`/`on` stuurt, verdwijnt HA “Onbekend”.

**Dual encoding in deze log:** startup-poll gebruikt `0015`/`0115`/`0000`; na `S`/`C` (o.a. `.32` ch0, `.30` ch0/ch9) komen **lab-codes** `0100`/`0000` terug. Commando-pad was dus al in orde; alleen de startup-decode ontbrak.

**Veldvalidatie bij Jan (na 1.6.4):**

1. Kanalen die hier `0015` hadden (trap, keuken LED, …) moeten in HA **uit** staan, niet Onbekend.
2. Toilet (`0115`) moet **aan** staan als het fysiek aan was.
3. Toggle op een voormalig-`0015`-kanaal: commando werkt; reply in log is `0100` of `0000`.
4. Als polariteit omgekeerd is: alleen de prefix-interpretatie omdraaien, geen architectuurwijziging.

Fysieke AAN/UIT blijft de gate voordat RE_STATE “confirmed” mag worden.

---

## 6. Interpretatie / volgende stappen

| # | Actie | Waarom |
|---|-------|--------|
| 1 | Bevestigen of IPBox nog master is (`hub_role=slave` in log) | Dual-hub kan dimmer-replies/commands storen |
| 2 | Gericht dimmer-test: 1 kanaal ON → OFF → DIM via HA + verse log of pcap op `.42` | Bewijs of `S…1030` / off-payload aankomt en of module antwoordt |
| 3 | Vergelijken met lab-IP0300PoE: zelfde payloads op Jan’s “8× 0-10V” faceplate | Generatie-gap (al gesignaleerd 2026-08-06) |
| 4 | Relays + knoppen-UI als PASS parkeren | Restore + 1.6.2 knoppen-pad werkt |

**Passief/actief:** Jan test nog met box erin (slave). Dimmer-regressie eerst isoleren vóór actieve hub-overname.

---

## 7. Bestandsindex

| Bestand | Inhoud |
|---------|--------|
| `3059e002_ipbuilding_gateway_2026-08-08T06-36-58.965Z.log` | Add-on log (ringbuffer) |
| `image001.png` … `image006.png` | WebUI na restore |
| `ocr_image00*.txt` | Tesseract OCR |
| `jan_feedback_112379.txt` | Mailtekst Jan (08:37) |
| `jan_feedback_112394.txt` | Mailtekst Jan (11:25 update) |
| `image007_ha_dimmer.png` | HA geschiedenis Ledverlichting keuken (Onbekend / unavailable) |
