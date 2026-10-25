# IPBuilding field bus capability matrix

Last updated: 2026-10-16

**Doel:** wat een **eigen centrale** op UDP/1001 vandaag al kan — **zonder** IPBox REST te hoeven nabootsen.

Northbound en centrale-architectuur: [docs/superpowers/specs/2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md).

| Capability | Veld-bus status | Evidence |
|------------|-----------------|----------|
| Relay ON/OFF | Confirmed encode/decode | Sprint 1, `gateway/payloads/relay.py` |
| Relay pulse + echo reply | Confirmed | `P0000` / `P000000000` (hub poll baseline) |
| Relay hub poll `I<ch>` | **Not supported** | `I0000` etc. → `I000000000` echo only — [2026-06-02_relay_poll_i_ch_test.md](evidence/2026-06-02_relay_poll_i_ch_test.md) |
| Relay status read | Confirmed (post-command) | `I<channel><state>` after `S`/`C` only — not via poll |
| Dimmer set level 10–100% | Confirmed | `S<ch><val>1<fade>` — fade `000`–`255`, default `000` (meteen). Oudere captures zijn fade `030` (`S<ch><val>1030`) |
| Dimmer OFF | Confirmed | `C<ch>001<fade>` — **niet** `S…00…`. Default fade `000`. Oudere captures `C<ch>991030` zijn fade `030` met waardecode `99` |
| Dimmer TOGGLE on/off | Confirmed | `T<ch>991000` — aan naar **laatste niveau**, uit naar off; hub + gateway API `TOGGLE` |
| Dimmer hold ramp (start/stop) | Confirmed | `D<ch>001003` start, `D<ch>001000` stop — module ramp + auto-richting; gateway `DIM_START`/`DIM_STOP` |
| Dimmer status read | Confirmed | `I0154<C><VV>` (kanaal + waarde-code; live test 2026-06-03) |
| Input hub poll | Confirmed | `I0000` |
| Input idle status reply | Confirmed | 14-byte `I\x02R…E` |
| Input button event (`B-…E`) | Confirmed encode/decode | Sprint 5, `gateway/payloads/input.py` |
| Input press → hub action mapping | Open (config model TBD) | [2026-05-22_sprint5_input_physical_completion.md](2026-05-22_sprint5_input_physical_completion.md) |
| Scene trigger on wire | Not reversed | — |
| Module discovery (UDP/10001) | Documented, no mirror replies | RE Wizards |
| Provisioning (WebConfig wizards) | Documented, not in code | RE Wizards |

## Dimmer: welk commando wanneer?

Hub-absoluut en knop/ramp delen UDP/1001, maar de laatste drie cijfers van `S`/`C` zijn een **fade** (`000`–`255`), niet een aparte dialectvlag. `T`/`D` houden hun eigen staart (`1000` toggle of stop, `1003` hold-start). Kies op **doel**:

| Doel | Gebruik | Wire (hub) | Niet gebruiken |
|------|---------|------------|----------------|
| Aan, meteen (100 %) | **ON** of **DIM** 100, fade 0 | `S<ch>991000` | `T…` als je absoluut 100 % wilt |
| Uit, meteen | **OFF** of **DIM** 0, fade 0 | `C<ch>001000` | `S…00…` |
| Laatste dim-niveau bewaren | **TOGGLE** | `T<ch>991000` | `DIM 100` / `DIM 0` |
| Vast percentage (slider, scene) | **DIM**, optionele `fade` 0–255 | `S<ch><val>1<fade>` (`99` = 100 %, `000` = meteen) | — |
| Lang indrukken dimmen | **DIM_START** / **DIM_STOP** | `D<ch>001003` / `D<ch>001000` | `brightness_step_pct`-loop in HA |

`1003` op `D` is start tegenover stop, geen fade-tijd. Ongeveer 0,2 s per fade-eenheid is een schatting (16 okt 2026); `010` was een uitschieter. De betekenis van het vaste `1` vóór de fade, de exacte schaal en tussenliggende niveaus zijn niet gemeten. De module antwoordt meteen met het eindniveau.

Detail + bewijs: [IPBUILDING_KNOWLEDGE.md](IPBUILDING_KNOWLEDGE.md) §6.6, [2026-05-17_dimmer_I0154xxx_full_decode.md](evidence/2026-05-17_dimmer_I0154xxx_full_decode.md), [2026-06-22_dimmer_p2p_hold_dim_capture.md](evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md). Encoders: `gateway/payloads/dimmer.py`.

## Code references

- `gateway/payloads/` — codecs
- `gateway/udp_bus.py` — UDP transport + poll loop
- `gateway/device_registry.py` — state + input button events from replies
- `gateway/rest_shim.py` — IPBox `:30200` **transition shim** (not product API); `rest_api.py` re-exports for compat
- [README_gateway.md](../README_gateway.md) — canonical gateway code status

## Deprecated naming

Het eerdere document `2026-05-17_ipbuilding_gateway_parity_matrix.md` sprak over “IPBox parity”. Dat is vervangen door dit bestand. IPBox REST is **referentie voor captures**, geen einddoel-API.
