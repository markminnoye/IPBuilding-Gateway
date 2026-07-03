# Legacy IPBox webservice `actions.php` — protocolanalyse & RE-vergelijking

Last updated: 2026-07-03  
Bron: `reference/legacy-ipbox-webservice/actions.php` (IPBuilding centrale / IPBox mobile webservice; veldbevestigd 2026-07-03 op IP0000 @ `10.10.1.1`, identiek aan eerdere e-mail-levering)
Canonieke RE-index: [RE_STATE.md](../RE_STATE.md) · Payload-matrix: [evidence/2026-05-14_udp_payload_semantics_matrix.md](../evidence/2026-05-14_udp_payload_semantics_matrix.md)

> **Statuslabel:** dit is **referentiebron-code**, geen wire-bewijs. Het is server-side PHP van de IPBox-weblaag (mobile WebUI → `ipcom`-service). Het bevestigt en verklaart veel van onze veldbus-RE, maar de getoonde strings zijn het **TCP-webservice-protocol** (PHP ↔ `ipcom`), niet rechtstreeks UDP/1001 (`ipcom` ↔ modules). Behandel afgeleide veldbus-conclusies als **hypothese** tenzij ze al wire-confirmed zijn in `RE_STATE.md`.

---

## 1. Wat dit document is

`actions.php` is de AJAX-backend van de oude IPBox **mobile webinterface** (`http://10.10.1.1/mobile/`). Zie ook `IPBUILDING_KNOWLEDGE.md` §12.1.1 voor het veldmelding-voorbeeld `protocolToggleItem`. Architectuur die eruit blijkt:

```
Browser (mobile WebUI)
   │  HTTP GET ?methode=…&ip=…&ch=…
   ▼
actions.php  (PHP op de IPBox, Windows)
   ├─► PDO/ODBC → MS Access .mdb   (config & status: ipcom.mdb, DMX.mdb, RADIO.mdb)
   └─► SocketHandler TCP "webservice" → ipcom-service  (commando's + status)
                                            │
                                            ▼  (intern, niet in dit bestand)
                                         UDP/1001 → relay/dimmer/input/audio modules
```

Twee belangrijke implicaties:

1. Er is een **applicatielaag-protocol** boven de veldbus: korte ASCII-commando's met mnemonics (`TGL`, `CLR`, `DIM`, `SET`, `INF`, `TAF`, `TAN`) over TCP naar de `ipcom`-service. De `ipcom`-service vertaalt die naar de veldbus UDP/1001-frames die wij hebben gereverse-engineerd (`S`/`C`/`T`/`P`…).
2. De **config woont in MS Access DB's** (`C:\Program Files\ipcom\ipcom.mdb`). Dit is precies het "IPBox-projectmodel" dat wij **niet** willen klonen, maar dat wel het databegrip oplevert voor ons eigen dunne mapping-model.

---

## 2. Het TCP-webservice-commandovocabulaire (PHP → `ipcom`)

Elk commando opent een TCP-socket, schrijft een commandostring, leest het antwoord, schrijft `END`, sluit. Geëxtraheerd uit de `methode`-handlers:

| `methode` (HTTP) | TCP-string naar `ipcom` | Betekenis | Adres-vorm |
| --- | --- | --- | --- |
| `protocolToggleItem` | `TGL;<ip>-<ch>` | Toggle uitgang | `ip-ch` |
| `protocolClearItem` | `CLR;<ip>-<ch>` | Uitschakelen (clear) | `ip-ch` |
| `protocolSetDimValue` | `DIM;<ip>-<ch>_<val>` | Dimwaarde zetten (`val` 0-pad naar 2 cijfers <10) | `ip-ch_val` |
| `protocolCallSoftComp` | `<reqStr>` (rauw) | Softcomponent/macro aanroepen | n.v.t. |
| `switchRegime` | `<regimeId>` (rauw) | Regime/sfeer activeren | regime-ID |
| `protocolGetCurrRegime` | `AAVX` | Huidig regime opvragen → `substr(resp,0,4)` | — |
| `getStatus` | `<reqStr>` (rauw) | Generieke statusquery (long socket) | — |
| `activateTempDeviation` | `TAF;<ip>-<address>_<reqTemp>_<reqTime>` | Thermostaat tijdelijke afwijking AAN | `ip-addr_temp_time` |
| `deleteTempDeviation` | `TAN;<ip>-<address>` | Thermostaat afwijking annuleren | `ip-addr` |
| `getAudioPlayerStatus` | `INF;<ipBarix>[;<ip>-<ch>]` | Audiostatus opvragen | `ip[;ip-ch]` |
| `audioPlayerPower` | `<reqStr>` (rauw) | Audio power toggle | — |
| `audioPlayerSetValue` | `SET;<ip>-20_<vol>` / `-23_<bass+100>` / `-22_<treb+100>` | Audio Vol/Bass/Treb absoluut | `ip-ch_val` |
| `audioPlayerNavigateValue` | `SET;<ip>-<03/04/09/10/07/08>_000` | Audio Vol/Bass/Treb stap ↑/↓ | `ip-ch_000` |
| `protocolAudioPlayerLoadPlaylist` | `SET;<ip>-21_<playList>` | Playlist laden | `ip-ch_val` |
| `protocolAudioPlayerLoadSong` | `SET;<ip>-33_<song>` | Nummer laden | `ip-ch_val` |

**Framing van dit laag-protocol:** `MNEMONIC;<ip>-<ch>[_<value>]`, terminator `END` op een aparte write. Separators: `;` scheidt mnemonic van argument, `-` scheidt ip van kanaal, `_` scheidt kanaal van waarde. Meerdere targets met extra `;`-segment (zie audio `INF`).

### Audiokanaal-mapping (Barix-achtig, modula 3)
Vaste kanaalnummers binnen één audio-IP:

| Functie | Kanaal | Noot |
| --- | --- | --- |
| Volume absoluut | 20 | |
| Bass absoluut | 23 | waarde `+100` offset |
| Treble absoluut | 22 | waarde `+100` offset |
| Vol ↑ / ↓ | 03 / 04 | step, waarde `000` |
| Bass ↑ / ↓ | 09 / 10 | step |
| Treble ↑ / ↓ | 07 / 08 | step |
| Playlist select | 21 | |
| Song select | 33 | |

---

## 3. Vergelijking met onze veldbus-RE (UDP/1001)

Dit is de kern. De webservice-mnemonics mappen één-op-veel op de UDP-frames die wij wire-confirmed hebben.

| Webservice (TCP, dit bestand) | Veldbus (UDP/1001, onze RE) | Overeenkomst | RE-bron |
| --- | --- | --- | --- |
| `INF;<ip>` (status opvragen) | `I0000` poll + `I…` replies (`I<CH><state>`, `I0154xxx`, `I\x02R…E`) | **Sterk.** `INF`→`I`-familie. `I` = "info/status" op beide lagen. | matrix r17–27 |
| `CLR;<ip>-<ch>` (off) | `C<CH>00` relay OFF / `C<ch><val>1030` dimmer OFF | **Sterk.** `CLR`→`C`. Eerste letter mnemonic = veldbus-prefix. | matrix r9, r24 |
| `TGL;<ip>-<ch>` (toggle) | `T<CH>00` relay toggle | **Sterk.** `TGL`→`T`. | matrix r13; relay set 2026-05-19 |
| `DIM;<ip>-<ch>_<val>` | `S<ch><val>1030` dimmer dim | **Gedeeltelijk.** `DIM` (webservice) → `S…1030` (veldbus). Mnemonic ≠ veldbus-letter hier: dim-AAN gebruikt `S` op de bus, `DIM` op TCP. | matrix r24 |
| `SET;<ip>-<ch>_<val>` (audio/generiek) | — (audio niet veldbus-gecaptured) | Onbevestigd op wire. Audio loopt mogelijk via Barix-IP, niet via UDP/1001-modules. | open |
| (geen webservice-equivalent: relay ON) | `S<CH>00` relay ON | Relay-ON gaat in de WebUI via `TGL` (toggle) of regime, niet via een aparte "ON". Veldbus `S`=ON staat los van TCP `SET`. | relay set 2026-05-19 |
| (geen) | `P<CH>00` pulse + `P000000000` echo | Pulse is een **module/config-eigenschap** (relay `pulse`-veld in `UpdateRelay`), niet los aanroepbaar in deze WebUI. | matrix r14, r19 |
| `AAVX` (huidig regime) / `switchRegime` | — | Regimes/sferen leven in `ipcom` (`SoftComp` `AAV%`), niet als losse veldbus-frames. Bevestigt: **sferen = centrale-logica, niet veldbus.** | §4 hieronder |
| `TAF` / `TAN` (thermostaat) | — | Thermostaat-veldbus niet door ons gecaptured. Nieuwe `T*F`/`T*N`-mnemonics. | open |

### Belangrijkste inzichten uit de vergelijking

1. **Mnemonic-eerste-letter ≈ veldbus-prefix, maar niet 1:1.** `CLR→C`, `TGL→T`, `INF→I` kloppen mooi met onze wire-confirmed veldbus-letters. Maar `DIM` wordt op de bus `S…1030` en relay-ON (`S`) heeft géén eigen TCP-mnemonic. Conclusie: de single-letter veldbus-prefixes (`S`/`C`/`T`/`P`/`I`) zijn een **eigen, lager alfabet** dat `ipcom` genereert; de TCP-mnemonics zijn de UI-laag. Niet blind aannemen dat elke TCP-mnemonic een veldbus-frame is.

2. **`I` = info/status is consistent over beide lagen.** Dit versterkt onze interpretatie van de hele `I…`-familie (`I0000` poll, `I<CH><state>` relay, `I0154xxx` dimmer, `I\x02R…E` input) als de status/poll-tak van het protocol.

3. **Adresvorm `<ip>-<ch>` op TCP** wordt door `ipcom` gesplitst: routeer naar module-IP (`10.10.1.30` etc.), emit kanaalcommando op UDP/1001. Dit verklaart waarom onze veldbus-frames alleen `<channel>` bevatten en niet het IP — het IP zit in de bestemming van het UDP-pakket, niet in de payload. Sluit aan bij `RE_STATE` (relay command = `I000{channel}{state}`, IP = pakket-destination).

4. **Geen envelope/`J`-separator in de TCP-laag.** Onze hub→relay wire-envelope (`<pfx>J` + kern, matrix r10/r22) bestaat **niet** in dit bestand. Bevestigt dat de `[pfx]J`-wrapper een artefact is van de `ipcom`→module UDP-transmissie (transmission-sequence marker), níét van de applicatielaag. Goede onafhankelijke ondersteuning voor onze conclusie dat de prefix-byte geen commando-semantiek draagt.

5. **`END`-terminator** is een TCP-sessieafsluiter richting `ipcom`, geen veldbus-byte. Niet verwarren met veldbus-framing.

---

## 4. Config-model (MS Access) — input voor ons eigen dunne mapping-model

`ipcom.mdb` tabellen die uit de SQL blijken:

- **`Componenten`** (hardware-componenten): kolommen `Type`, `Modula`, `Adres`, `Omschrijving`, `mobileView`, `actief`.
  - `Modula` = devicetype-code (zie tabel hieronder).
  - `Adres` = veldbus-adres; relay-adressen waarvan `substr(Adres,0,1)=="F"` krijgen speciale behandeling (uitzondering op `Modula==2`-filter).
- **`SoftComp`** (softcomponenten / macro's / regimes): `ID`, `Type`, `Omschrijving`. **`ID LIKE 'AAV%'` = regimes/sferen** (de "moods" die wij hadden uitgesteld). `AAVX` = query-commando voor huidig regime.
- **`paswoord`**: `gebruikersnaam`, `paswoord` (plaintext! login-check via string-SQL — klassieke SQL-injectie, puur historische noot).
- **`Audioswitch`**: `IP`, `IPSource` (audio-routing/bron-mapping).
- **`DMX.mdb` → `Status`**: `Channel`, `Value` — RGB-LED via DMX, **3 kanalen per LED** (R/G/B), kleur als hex; channel-index = `(dmxCh*3)-2`.
- **`RADIO.mdb` → `Radio`**: `pat` (pad/URL), `Naam` (stationnaam).

### `Modula` devicetype-codes (afgeleid uit de handlers)

| Modula | Betekenis (afgeleid) | Bewijs in code |
| --- | --- | --- |
| 1 | Dimmer | `if Modula==1 { dimAmount++ }`, `showGroupItemsDim` filtert `Modula = 1` |
| 2 | (uitgesloten van mobileView tenzij `Adres` begint met `F`) — waarschijnlijk thermostaat/HVAC of intern type | `if Modula != 2 \|\| substr(Adres,0,1)=="F"` |
| 3 | Audio (Barix audioswitch) | `loadAudioPlayer`: `if modula==3 { lookup Audioswitch.IPSource }` |
| 24 | Camera type A (`/enu/cameraWxH.jpg`) | `showVideoImage` |
| 25 | Camera type B (`/video.jpg`) | `showVideoImage` |
| (overig) | Camera generiek (`/cgi-bin/viewer/video.jpg?resolution=`) | `showVideoImage` else-tak |

> Let op: dit `Modula`-schema is van de **oude** IPBox-software en hoeft niet identiek te zijn aan de huidige module-firmware/REST `Modula`-codes. Vergelijk met `IPBUILDING_KNOWLEDGE.md` (TYPE_-codes, o.a. `TYPE_SPHERE=100`) voordat je het overneemt.

### Wat dit betekent voor onze architectuur
- Bevestigt het **productprincipe** (AGENTS.md): sferen/regimes (`AAV%`-softcomponents) en knop→actie-regels zijn **centrale-logica** in `ipcom`, niet iets dat op de veldbus zit. → Hoort bij ons in **Home Assistant**, niet in de gateway.
- De minimale mapping die we wél nodig hebben (device/kanaal ↔ veldbus-adres) komt overeen met `Componenten.Adres` + `Modula` + module-IP. Geen tweede projectdatabase nodig.
- Audio-Vol/Bass/Treb-kanaalmapping (§2) is bruikbaar als/wanneer audio in scope komt.

---

## 5. Nieuwe leads / open vragen toegevoegd door dit bestand

1. **Thermostaat-protocol** (`TAF`/`TAN`, `Modula==2`?): nieuw, nog geen veldbus-capture. Kandidaat voor latere RE als HVAC in scope komt.
2. **Audio over UDP/1001 vs Barix-IP**: `SET;ip-ch_val` met vaste kanaalnummers (20/22/23/...). Onbekend of `ipcom` dit naar UDP/1001 of rechtstreeks naar de Barix-HTTP/streaming stuurt.
3. **`SET`-mnemonic op de veldbus**: bestaat er een veldbus-`SET`-frame, of vertaalt `ipcom` `SET` naar iets anders? Niet wire-confirmed.
4. **Regime/sfeer-activatie** schrijft de rauwe `regimeId` naar `ipcom`. Als we ooit de sferen-RE (uitgesteld) oppakken: het query-commando is `AAVX` en de ID-conventie is `AAV…`. Sluit aan bij `RE_STATE` "Unknowns → Input logical flow".
5. **`DIM`-waarde-encoding**: webservice padt naar 2 cijfers (`val<10 → "0"+val`); onze veldbus-dimmer gebruikt value-codes `10`–`99` met `S<ch><val>1030`. Mogelijke directe relatie tussen WebUI-`val` en veldbus value-code, maar de `1030`-staart en kalibratie (soft-AAN/UIT §12.3) zitten in `ipcom`, niet hier.

---

## 6. Conclusie

`actions.php` is een waardevolle **referentie/Rosetta-stone** die onze veldbus-RE op meerdere punten onafhankelijk ondersteunt:

- **Bevestigt**: `I`=status/poll-familie, `C`=off, `T`=toggle als coherent commando-alfabet; `<ip>-<ch>`-routing waarbij IP in de pakketbestemming zit; sferen/regimes als centrale-logica (niet veldbus); pulse als config-eigenschap.
- **Verfijnt**: de TCP-mnemonics (`TGL/CLR/DIM/SET/INF/TAF/TAN`) zijn de **applicatielaag** boven onze UDP-frames; `ipcom` is de vertaler. De `<pfx>J`-envelope en `END` zijn transport-artefacten, geen commando-semantiek — dit ondersteunt onze ingetrokken "prefix-byte=commando"-hypothese.
- **Voegt toe**: thermostaat- (`TAF/TAN`) en audio- (`SET` + kanaalmap) vocabulaire, en het `Modula`-devicetype-schema uit `ipcom.mdb` als referentie voor ons eigen dunne mapping-model.

Geen wijziging aan wire-confirmed status in `RE_STATE.md` nodig; dit document is puur **versterkend referentiemateriaal**. Afgeleide veldbus-claims (audio-`SET`, thermostaat) blijven **hypothese** tot wire-bewijs.
