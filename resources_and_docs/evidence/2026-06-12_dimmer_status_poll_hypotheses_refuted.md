# Dimmer status-poll hypotheses — beide verworpen (2026-06-12)

Last updated: 2026-06-12

**Context:** na het ontdekken van de relay cold-boot sweep (`I<CH>00` → `I000<CH><state>`, zie [2026-06-12_ipbox_boot_relay_sweep.md](2026-06-12_ipbox_boot_relay_sweep.md)), leek het aannemelijk dat de dimmer (`10.10.1.40`) een analoog mechanisme zou hebben — `I9900` is immers letterlijk hetzelfde `I<CH>00`-formaat met `CH=99` ("alle/poll"). Twee hypotheses zijn live getest tegen de fysieke dimmer, met bekende reële kanaaltoestand als validatie (Woonkamer = kanaal 0, ~99%/vol aan; Bureau = kanaal 1, gedimd tussen 10-90%).

## Hypothese 1: `I<CH>00` selecteert een specifiek dimmer-kanaal — VERWORPEN

**Test:** `I0000`, `I0100`, `I0200`, …, `I0700` los en interleaved naar `10.10.1.40:1001`, plus stabiliteitscheck (5× herhaald per payload).

**Resultaat:** elke query — ongeacht kanaalcijfer — gaf exact `I0154099` (kanaal 0, waarde 99). De Bureau-status (kanaal 1, op dat moment zichtbaar gedimd) verscheen **nooit**, ook niet bij expliciete `I0100`-query.

**Extra bevinding (bijvangst):** met niet-numerieke payloads (`IXXXX`, `IZZ99`, `I` + spaties) echoot de dimmer letterlijk byte[1] van de query terug in het kanaalveld, met waarde `00` (bv. `IXXXX` → `I0154X00`). Met geldige cijfers geeft hij altijd de waarde van kanaal 0. Dit wijst erop dat de dimmer geen echte per-kanaal-lookup doet op basis van dit veld — vermoedelijk een simpele parser/echo zonder kanaal-routing.

**Conclusie:** in tegenstelling tot de relay bestaat er **geen** `I<CH>00`-statusquery-mechanisme voor de dimmer. De relay-analogie gaat hier niet op.

## Hypothese 2: `I9900` toont het echte niveau als een kanaal aan staat — VERWORPEN

**Test:** 10× `I9900` gestuurd, elk 1s uit elkaar, terwijl fysiek bevestigd was dat Woonkamer (ch0) vol aan stond en Bureau (ch1) gedimd was.

**Resultaat:** alle 10 replies waren identiek `I0154999` (idle/poll-heartbeat, geen kanaal, geen setpoint) — geen enkele variatie ondanks actieve/gedimde kanalen.

**Conclusie:** `I9900` is een pure liveness-check, nooit een statusdrager, ongeacht de werkelijke dimmer-toestand.

## Samenvatting

| Mechanisme | Relay `.30` | Dimmer `.40` |
|---|---|---|
| Cold-boot per-kanaal sweep | ✅ `I<CH>00` → `I000<CH><state>` | ❌ niet aanwezig |
| On-demand per-kanaal poll | ✅ (zie boven) | ❌ **verworpen** (H1) |
| Generieke poll toont niveau | n.v.t. | ❌ **verworpen** (H2) — `I9900` altijd `999` |
| Enige bron van echt niveau | — | **spontane reply** `I0154<ch><vv>` na S/C/D-commando, of fysieke bediening |

**Praktische consequentie voor de gateway:** het dimmer-niveau kan **niet** actief opgevraagd worden bij startup of on-demand. De gateway moet:
1. Zelf state bijhouden op basis van commando's die het zelf stuurt (S/C/D), en
2. Passief luisteren naar spontane `I0154<ch><vv>`-replies (na fysieke bediening buiten de gateway om) om externe wijzigingen te detecteren.

Bij een cold restart van de gateway is het dimmer-niveau dus **onbekend** totdat er een eerste commando/wijziging plaatsvindt — anders dan bij de relay, waar de boot-sweep een directe state-read geeft. Alternatief te onderzoeken: of de WebConfig-laag (`ImportDimInfo`) live niveaus teruggeeft naast configuratie — nog niet getest.

**Test-methode:** ad-hoc Python UDP-scripts (niet in repo opgenomen), live tegen `10.10.1.40:1001` vanaf het IPBuilding-VLAN, met bekende fysieke kanaaltoestand (Woonkamer aan, Bureau gedimd) als validatie-anker.
