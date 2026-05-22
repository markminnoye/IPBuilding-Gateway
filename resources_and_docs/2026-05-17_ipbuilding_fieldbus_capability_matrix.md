# IPBuilding field bus capability matrix

Last updated: 2026-05-22

**Doel:** wat een **eigen centrale** op UDP/1001 vandaag al kan — **zonder** IPBox REST te hoeven nabootsen.

Northbound en centrale-architectuur: [docs/superpowers/specs/2026-05-18-gateway-architecture-design.md](../docs/superpowers/specs/2026-05-18-gateway-architecture-design.md).

| Capability | Veld-bus status | Evidence |
|------------|-----------------|----------|
| Relay ON/OFF | Confirmed encode/decode | Sprint 1, `gateway/payloads/relay.py` |
| Relay pulse + echo reply | Confirmed | `P0000` / `P000000000` |
| Relay status read | Confirmed | `I<channel><state>` |
| Dimmer DIM 0–100 (command) | Confirmed | `S<ch><val>1030` |
| Dimmer OFF | Confirmed | `C<ch>991030` |
| Dimmer status read | Confirmed | `I0154xxx` |
| Input hub poll | Confirmed | `I0000` |
| Input idle status reply | Confirmed | 14-byte `I\x02R…E` |
| Input button event (`B-…E`) | Confirmed encode/decode | Sprint 5, `gateway/payloads/input.py` |
| Input press → hub action mapping | Open (config model TBD) | [2026-05-22_sprint5_input_physical_completion.md](2026-05-22_sprint5_input_physical_completion.md) |
| Scene trigger on wire | Not reversed | — |
| Module discovery (UDP/10001) | Documented, no mirror replies | RE Wizards |
| Provisioning (WebConfig wizards) | Documented, not in code | RE Wizards |

## Code references

- `gateway/payloads/` — codecs
- `gateway/udp_bus.py` — UDP transport
- `gateway/rest_api.py` — **experimental only** (RE stimulus helper, not product API)

## Deprecated naming

Het eerdere document `2026-05-17_ipbuilding_gateway_parity_matrix.md` sprak over “IPBox parity”. Dat is vervangen door dit bestand. IPBox REST is **referentie voor captures**, geen einddoel-API.
