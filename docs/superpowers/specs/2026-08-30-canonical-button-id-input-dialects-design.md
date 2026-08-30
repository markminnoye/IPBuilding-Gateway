# Canonical button id + input dialect map — design spec

**Date:** 2026-08-30
**Status:** approved
**Repos:** IPBuilding Gateway (add-on **1.7.0**) + `ha-ipbuilding-gateway` (companion **≥ 1.9.0**)
**Context:** Nolf 2026-08-29 debug log — 1.6.7 fixed relay/dimmer status, buttons still `undecoded RX from 10.10.1.55`
**Predecessor:** [`2026-08-25-nolf-dialect-decode-design.md`](2026-08-25-nolf-dialect-decode-design.md) listed *"Mapping `input.nolf.binary`"* as an explicit non-goal. This spec does that mapping, and adds a second defect found while doing it.

---

## 1. Problem

Jan Nolf's pushbuttons do not reach Home Assistant. Two **independent** defects sit in series; fixing either one alone leaves the buttons dead.

### Defect 1 — the wire decoder rejects the frame

`_INPUT_EVENT_RE` in `gateway/payloads/input.py` hard-requires `0x2d` at offset 1. Jan's IP040x interfaces send `0x01`. The frame is otherwise byte-for-byte the lab layout. Byte offsets are 0-based throughout this spec, so offset 0 is `B` (`0x42`).

| | lab (works) | Nolf (rejected) |
|---|---|---|
| Frame | `42 2d 2f8185190000df 03 01 00 45` | `42 01 dac46c100000c3 01 01 00 45` |
| Offset 1 (type) | `0x2d` | `0x01` |
| Length | 13 | 13 |
| Marker | `0x03` / `0x02` | `0x01` (regex already accepts any byte) |

The idle reply is rejected for the same class of reason — a differing family byte:

| | lab | Nolf |
|---|---|---|
| Frame | `I \x02 R <3 status> <7×00> E` | `49 02 28 00×9 45` |
| Family byte | `0x52` (`R`) | `0x28` |
| Length | 14 | 13 |

Evidence from the 2026-08-29 log — all 20 `undecoded RX from 10.10.1.55` frames are accounted for:

| Payload | Count | Meaning |
|---|---|---|
| `49022800000000000000000045` | 12 | idle reply (defect 1b) |
| `4201{id}01{01\|00}0045` | 8 | 4 buttons × press + release (defect 1a) |

### Defect 2 — the configured id can never match the wire id

Even with the decoder fixed, `pushbutton_by_id()` returns `None`. Three sources produce three different id strings for the same physical button:

| Source | Example | Length |
|---|---|---|
| UDP `B…E` wire | `dac46c100000c3` | 14 hex |
| HTTP `getButtons` | `2ddac46c100000c3` | 16 hex |
| `.IPA` autonomy dump → `devices.json` | `dac46cc330` | 10 hex |

Jan's `devices.json` is 60/60 in the 10-hex form; the lab `devices.json` is 32/32 in the 14-hex form. Neither can be looked up by the other's key.

Left unfixed, learn-on-press appends a 61st nameless button per press, and the automation bound to the existing entity stays silent.

### Root cause of defect 2 — the IPA parser is misaligned

`gateway/ipa_parser.py` documents the record layout as alternating "button row" / "target row" and `parse_ipa_text()` therefore pairs consecutive 7-field records. Every record actually has the **same** shape. Verified against `resources_and_docs/reference/samples/10.10.1.55.IPA`:

```
field 0..3   4 hex bytes           button id  (canonical form)
field 4      2-char decimal ASCII   target module IP last octet
field 5      ASCII digit            target channel, tens digit
field 6      ASCII digit or FF      target channel, units digit; FF = absent
```

Channel = `d5 × 10 + d6`, or `d5` alone when field 6 is `FF`.

Verification, 33 records in the sample:

| Check | Result |
|---|---|
| Records with 7 fields | 33 (parser reported 16 "buttons") |
| `field[0:4]` present as a canonical id in Jan's `devices.json` | 33 / 33 |
| Channel within its module's range under the layout above | 33 / 33 |
| Target octets found | `30`, `32`, `42` — exactly Jan's three actuator modules |
| Channels on relay `.30` (24 ch) | 2–23 |
| Channels on dimmer `.42` (4 ch) | 0–2 |

Three consequences, all matching observed symptoms:

1. `button_id` is read as **5** bytes and swallows the target octet → the 10-hex form, i.e. defect 2.
2. Half the records are consumed as "target rows" → ~17 of 33 buttons silently dropped.
3. Each button is assigned the **next** button's target → wrong `targets`, and therefore wrong channel activation in `build_devices_json_from_ipa()`.

The repo sample is a subset of Jan's installation (33 of his 60 buttons); the 27 remaining ids come from a larger IPA file we do not have. That does not affect the layout finding.

---

## 2. The canonical id

The four bytes the IPA stores natively — `serial, serial, serial/model, serial` — are the identifier. The other two formats are the same four bytes in different packaging:

| Source | Packaging | Canonical extraction |
|---|---|---|
| `.IPA` | id as-is, then target octet | first 4 bytes |
| UDP wire (7 bytes) | `id[0:3]` + `model2 00 00` + `id[3]` | bytes 0,1,2,6 |
| `getButtons` (8 bytes) | type byte + the 7-byte wire form | strip type byte, then bytes 0,1,2,6 |

This is **not** a lossy intersection chosen for convenience — it is the manufacturer's own key, as stored in the module EEPROM autonomy table.

### Uniqueness

| Dataset | Buttons | Unique canonical ids | Collisions |
|---|---|---|---|
| lab `devices.json` (14-hex) | 32 | 32 | none |
| Nolf `devices.json` (10-hex) | 60 | 60 | none |
| Combined | 92 | 92 | none |

Byte 2 carries little entropy (6 distinct values per dataset — it is partly a model/batch code), but bytes 0, 1 and 6 vary freely and no collision occurs across all 92 known buttons.

### Why the type byte is not part of the identity

The IPA does not store it, and `getButtons` places it *before* the id as a separate prefix — which the current code already strips. Type is metadata about the device class, not about which device. It travels alongside the id instead (§4).

### Why the wire form cannot be the canonical form

Reconstructing the 14-hex wire id from an IPA entry requires the model/batch byte at wire position 3, which appears **only** on the wire and varies per button within one module (lab: `0x19` ×27, `0x2c` ×3, `0x14` ×2). Of Jan's 60 buttons we have seen 4 on the wire; the other 56 would only get a wire id once someone physically pressed them.

### Implementation

New leaf module `gateway/button_id.py`, importing nothing from `gateway.*` so it can be used by the portable `payloads/` layer without an import cycle:

```python
def canonical_button_id(raw: str) -> str | None:
    """Return the 8-hex canonical id, or None when the input is not a known form."""
```

Accepted inputs, dispatched on length after lowercasing and stripping whitespace:

| Length | Form | Action |
|---|---|---|
| 16 | `getButtons`, type prefix + wire | strip 2 leading chars, then treat as 14 |
| 14 | wire | `s[0:6] + s[12:14]` |
| 10 | legacy IPA-derived config | `s[0:8]` |
| 8 | already canonical | unchanged |
| other | unknown | `None` |

Non-hex input returns `None`. Returning `None` rather than raising lets the config loader report a per-button problem and continue (§6).

`normalize_button_hardware_id()` in `gateway/module_metadata.py` is **deleted**, not aliased — the whole point is that one id form exists. Call sites to update: `module_metadata.py:276`, `device_config.py:298`, `gateway_api.py:1084,1382,1387`.

`InstallationConfig.pushbutton_by_id()` additionally canonicalises its **argument** instead of only lowercasing it. One line there covers every lookup boundary at once — REST path parameters such as `GET /api/v1/devices/{device_id}` (`gateway_api.py:566`), `apply_pushbutton_patch()`, and the hold-threshold lookup — so a client that still sends a 14- or 16-hex id keeps working without a second normalisation call anywhere.

---

## 3. Wire decoder

`gateway/payloads/input.py`:

```python
_INPUT_EVENT_RE = re.compile(
    rb"^B(?P<type>.)(?P<id>.{7})(?P<marker>.)(?P<edge>\x01|\x00)\x00E$"
)
_INPUT_REPLY_RE = re.compile(
    rb"^I\x02(?P<family>.)(?P<status>.{3})\x00{6,7}E$"
)

_BUTTON_TYPE_DIALECT = {
    0x2D: "input.lab.button_event",
    0x01: "input.nolf.button_event",
}
```

The reply regex covers both the 14-byte lab frame (`family` = `0x52`, 7 trailing zeros) and the 13-byte Nolf frame (`family` = `0x28`, 6 trailing zeros).

`decode_input_payload()` returns for a button event:

| Key | Value |
|---|---|
| `family` | `input_button_event` |
| `action` | `press` / `release` |
| `id_hex` | canonical, 8 hex |
| `id_wire_hex` | full 7-byte id, for logs and diagnostics |
| `type_hex` | the type byte |
| `dialect_id` | mapped value, or `input.unknown.button_event` |
| `marker_hex`, `length` | unchanged |

`device_registry.py:340` currently concatenates `id_core_hex + id_suffix_hex`; it becomes `parsed["id_hex"]`. `decode_input_event()` uses the same field. `id_core_hex` / `id_suffix_hex` disappear from the return dict.

**Bounded blast radius.** `DeviceRegistry.handle_packet()` dispatches strictly on the module type registered for the source IP, so `decode_input_payload()` only ever sees frames from an input module. Loosening the type byte cannot make a relay or dimmer frame decode as a button press.

### Unknown type bytes are routed, not blocked

A detector on the IP1100 does functionally no more than a pushbutton: same `B…E` shape, same press/release edges. Knowledge doc §2C documents `/detectors.html` with `getDetectors` / `detScanToAdd` / `saveDetector`, and `DetectorConfig` already exists as a schema placeholder with no UDP decode.

| Type byte | Origin | Handling |
|---|---|---|
| `0x2d` | IP040x lab, also the `getButtons` prefix | `button_event` → HA |
| `0x01` | IP040x Nolf, older generation | `button_event` → HA |
| any other | unknown: detector, or a third generation | `button_event` → HA, plus the net below |

Unknown hardware therefore works on first press. The risk is not that it works but that it works **silently under the wrong label**, and that is answered with visibility rather than by blocking the route (§4). Promoting a byte to a known dialect is afterwards one line in `_BUTTON_TYPE_DIALECT`.

**Accepted residual risk:** a detector and a pushbutton sharing one canonical id would collide. No evidence of this exists (92/92 unique), and the per-type warning surfaces it as two type bytes on one id if it ever happens.

---

## 4. Observability

Three layers, so an unknown device is never invisible.

1. **Gateway, once per unknown type byte:** `WARNING` with `type_hex`, `id_hex`, `id_wire_hex`, `action` and `module_ip`. Deduplicated on the type byte, not on the id — one line per new device class, not per press.
2. **WebSocket:** `type_hex` and `dialect_id` in the `device_added` payload for a learned button.
3. **Companion:** the existing persistent-notification path gets a second text variant. On a known dialect it stays *"Nieuwe IPBuilding drukknop"*; on `input.unknown.button_event` it becomes *"Onbekend IPBuilding inputtype"* with the type byte in the body, so the operator can report it.

Separately, `_log_undecoded()` in `device_registry.py` is DEBUG-only today. It becomes a **once-per-signature** `WARNING`, keyed on `(module_ip, length, first byte, last byte)`. Frames that match neither `B…E` nor the idle reply — such as the `F`-frame seen while the IPBox was still master — then appear at default log level instead of only when the operator has raised the level to debug.

This matters because Jan's log was readable only because he had debug enabled. At the default `INFO` level a detector module today produces no entity, no event and no log line at all.

---

## 5. IPA parser

Rewrite `parse_ipa_text()` to return a **flat list** of 7-field records instead of pairs, and `parse_ipa_file()` to read each record per §1:

```python
button_id = canonical_button_id("".join(fields[0:4]))   # 8 hex
target_ip = f"10.10.1.{int(fields[4])}"
channel   = <d5×10 + d6, or d5 when d6 is FF>
```

`IpaButtonEntry.targets` becomes at most **one** `IpaAutonomyTarget`; it stays a list so `build_devices_json_from_ipa()` and the schema do not change shape. The parser's "func1 ch / func2 ch" reading of fields 5–6 was an artefact of the pairing bug — those two fields are the digits of a single channel number. `func1` / `func2` are real in the **`getButtons` REST model** (knowledge §2C, §12.7), but nothing in the sample shows how or whether the IPA encodes a second function; possibly as a second record, possibly not at all. The parser must not assume either way.

`IpaButtonEntry.button_id`'s docstring changes from *"14 lowercase hex chars (wire form, no 2D prefix)"* to the canonical 8.

Records that do not have 7 fields, or whose octet/channel fields do not parse, are **skipped with a WARNING** naming the record index — today they are dropped in silence.

Consequence to accept: re-importing an IPA now yields roughly twice as many buttons and different `targets`. That is the bug being fixed, but it means a re-import is not idempotent against a config produced by the old parser. `merge_devices_json()` already matches on lowercase id and will not clobber operator fields, and after §7 both sides are canonical, so the previously-dropped buttons are appended and the surviving ones keep their names.

---

## 6. Config validation

There is no id validation on load today, so a typo produces a button that silently never responds. `InstallationConfig._parse()` gains, per pushbutton:

- id is not 8 lowercase hex → skip the entry, `WARNING` with the module IP, the raw value, and a pointer to `scripts/migrate_button_ids.py`. 10-hex and 14-hex config ids are **not** converted on load.
- Duplicate 8-hex id → `raise InstallationError` (unchanged).

The check byte cannot help here: testing 252 sum/XOR formulas over every subset of the six core bytes plus five CRC-8 variants gave at best 4 hits on 32 lab buttons, against ~0.1 expected by chance. Byte 6 is entropy, not redundancy. Shape and uniqueness are the only checks available.

---

## 7. Migration

### Gateway — `devices.json`

Migration is an **operator action**, not an automatic rewrite at startup.

On load, only **8-hex** pushbutton ids are accepted. 10-hex / 14-hex / other forms are skipped with a `WARNING` that names `scripts/migrate_button_ids.py`. The file on disk is never rewritten at startup. The script is the backed-up rewrite (`.bak` first, idempotent). It lives under `scripts/` and is **not** in the add-on image — run it on a downloaded backup, then restore.

Beta: only two installations exist. There is no in-memory compatibility layer for old config ids. Convert the file (or ship a converted file) before starting 1.7.0.

### Companion — entity and device registry

The companion has no `async_migrate_entry` today and `ConfigFlow.VERSION` is `1`. Both are new: bump to `VERSION = 2` and add the handler, migrating the entity and device registries.

| Registry | From | To |
|---|---|---|
| Entity `unique_id` | `event_<10 or 14 hex>` | `event_<8 hex>` |
| Device `identifiers` | `(DOMAIN, <10 or 14 hex>)` | `(DOMAIN, <8 hex>)` |

**`entity_id` is deliberately not touched.** Home Assistant assigns `entity_id` once at first registration and keeps it when `unique_id` changes, so `event.badkamer`, its friendly name, its area and every automation and blueprint bound to it survive the upgrade untouched. Without this migration the same entities would be orphaned and re-created under new ids — which is what makes the migration mandatory rather than optional.

The 8-hex form must be computed with the same length dispatch as §2; the companion cannot import from the gateway, so this is a small duplicated helper. That duplication is accepted: the alternative is a shared package for one function.

### Release ordering

Two components ship separately and an operator can update them in either order, so neither may assume the other has been updated. Without care, a new gateway plus an old companion would orphan every button entity and re-create it under the short id — precisely the breakage the migration exists to prevent.

The fix is to make the companion **id-form agnostic on input**: it applies `canonical_button_id()` to every id it receives from the gateway, in the devices snapshot, in `_handle_button_device_added()` and in `_notify_button()`'s `button:<id>` routing key. It then keys its entities on the canonical form regardless of which gateway version is talking, and both update orders converge:

| Order | Behaviour |
|---|---|
| Companion first | migrates its registry to 8-hex, canonicalises the old gateway's 14-hex events → lab buttons keep working |
| Gateway first | serves 8-hex; the old companion breaks until the companion is updated → **the add-on changelog must state the companion minimum version** |
| Together | clean |

The gateway-first row is the one real hazard, and it is handled with documentation plus a version floor rather than code, since the gateway cannot repair an old companion. Target versions: add-on **1.7.0** and companion **≥ 1.9.0**, both minor bumps carrying a breaking id change. The duplicated `canonical_button_id()` helper in the companion is accepted (no shared package). IPA `targets` stay as parsed; no separate autonomy-import issue.

### Outcome per installation

| Installation | Before | After |
|---|---|---|
| Lab (14-hex config, working buttons) | works | works, ids shorten, entity_ids and automations unchanged |
| Nolf (10-hex config, dead buttons) | 60 entities that never fire | same 60 entities, now matched on press |
| Fresh install | — | canonical from the first write |

Note for Nolf specifically: because his configured ids will match after migration, `pushbutton_by_id()` succeeds, learn-on-press is skipped, and he gets **no** "new button" notification. His buttons simply start working under the names already in his config.

---

## 8. Non-goals

- **Detector entities as a distinct HA platform.** Detectors arrive as `event` entities via the button path. A dedicated platform needs `getDetectors` evidence we do not have.
- **Decoding the `F`-frame** seen in the earlier Nolf log while the IPBox was master. It gets a warning (§4), not a decoder.
- **Autonomy provisioning.** The IPA `targets` are parsed correctly and exposed, but the gateway still does not write EEPROM autonomy (Fase 8) and button→action logic stays in Home Assistant.
- **Resolving how the IPA encodes a second function.** The parser reads one target per record and stops there; it neither claims nor denies that `func2` appears elsewhere in the file.
- **ESP32 payload port.** Follow-up after Jan's field validation, per the A4 manual-sync decision.
- **`devices.json` schema changes** beyond id length.

---

## 9. Documentation to update

| File | Change |
|---|---|
| `gateway/ipa_parser.py` docstring | the record layout is wrong today; replace with §1 |
| `resources_and_docs/IPBUILDING_KNOWLEDGE.md` §12.3–12.5 | add the verified IPA record layout — it is an RE finding, currently documented nowhere |
| `resources_and_docs/reference/veldbus_dialect_registry.md` | replace the `input.nolf.binary` placeholder with the three button dialects and the two idle-reply families |
| `docs/api/websocket.md` | `type_hex` and `dialect_id` on `device_added` |
| `resources_and_docs/RE_STATE.md` | the input wire is no longer lab-only; two type bytes and two idle-reply families confirmed |
| `ipbuilding_gateway/CHANGELOG.md` | breaking: button ids are 8 hex; old config ids skipped until `scripts/migrate_button_ids.py`; **companion ≥ 1.9.0 required** |
| companion `README` / changelog | the entity migration, and that automations keyed on `entity_id` are unaffected |

---

## 10. Test plan

### Unit — gateway

| Area | Case |
|---|---|
| `canonical_button_id` | all four lengths; the 4 confirmed wire↔IPA pairs; non-hex → `None`; odd length → `None`; uppercase and whitespace |
| Button decode | Nolf `4201dac46c100000c301010045` → press, `id_hex` `dac46cc3`, dialect `input.nolf.button_event` |
| Button decode | lab `422d2f8185190000df03010045` → press, `id_hex` `2f8185df`, dialect `input.lab.button_event` |
| Button decode | synthetic unknown type → routed, dialect `input.unknown.button_event`, warning fired once over repeated presses |
| Idle reply | Nolf 13-byte `49022800000000000000000045` and lab 14-byte, both decode; family byte exposed |
| Regression | `_INPUT_EVENT_RE` still rejects a bad edge byte and a wrong length |
| IPA parser | sample file → 33 buttons; all ids canonical; octets `{30,32,42}`; channels in range; the 3 previously-mismatched ids now resolve |
| IPA parser | malformed record skipped with a warning, parse continues |
| Config load | 8-hex accepted; 10-hex / 14-hex / garbage skipped with a warning; exact duplicate 8-hex still raises |
| Migration script | non-canonical file → `.bak` written, file rewritten, second run a no-op; loader does **not** convert or rewrite on start |

Existing tests carrying literal 14-hex ids must be updated: `test_input_payloads`, `test_module_metadata`, `test_installation`, `test_installation_serialization`, `test_device_config`, `test_learn_unknown_buttons`, `test_button_timing`, `test_gateway_api_modules`, `test_gateway_api_devices_patch`, `test_import_ipbox`, `test_migrate_buttons_to_nested`.

### Unit — companion

| Area | Case |
|---|---|
| `async_migrate_entry` | registry seeded with 10-hex and 14-hex entries → `unique_id` and device `identifiers` updated, `entity_id` and friendly name unchanged; running twice is a no-op |
| Backward compatibility | a `button_event` carrying a 14-hex id reaches the entity registered under the 8-hex form (old gateway, new companion) |
| Forward compatibility | the same for an 8-hex id (new gateway) |
| Unknown dialect | `device_added` with `dialect_id: input.unknown.button_event` produces the "onbekend inputtype" notification text including the type byte |

### Field validation — Jan

The two defects must be separated in the checklist, exactly as the 1.6.5 spec learned to do:

| Observation after a press | Meaning |
|---|---|
| No `undecoded RX` from `.55`, and `Input … button … press` at INFO | defect 1 fixed |
| Gateway `/api/v1/devices` shows the button; HA `event.*` fires | defect 2 fixed |
| Decodes, but no HA event | companion migration or entity sync |
| `Unknown input type byte 0x..` warning, button works anyway | a third generation or a detector — add one line to the dialect map |
| Still `undecoded RX` | a frame that is neither `B…E` nor an idle reply; the new per-signature warning names its length and delimiters |

Ask for a fresh debug log plus the outcome of one press per module, at the **default** log level — if the fix works, `INFO` is now enough to confirm it. The lab regression is the 32-button `devices.json` after migration.

---

## 11. Open questions — decided

1. **Rewriting `devices.json` on load.** **Operator action via script. No in-memory compat.** Loader accepts 8-hex only; `scripts/migrate_button_ids.py` rewrites the file.
2. **Duplicated canonical helper in the companion.** **Accepted.** Same length-dispatch helper, no shared package.
3. **IPA `targets` scope.** **Leave as is.** Parsed correctly and exposed; no separate autonomy-import issue.
