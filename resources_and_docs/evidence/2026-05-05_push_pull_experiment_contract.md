# Phase 0 Contract — IPBuilding RE (Push vs Pull)

## 1) Scope en neutrale onderzoeksvraag (push vs pull)

Doel van Phase 0 is evidence-driven vaststellen of statuswijzigingen in de IPBuilding-keten primair door push-signalen (eventgedreven frames na stimulus) of door pull/polling (periodieke statusreads) zichtbaar worden op de capture-POV.
We onderzoeken dit over meerdere protocollen (UDP, TCP/REST, module-HTTP), niet alleen ARP.

Neutrale hoofdvraag:

> "Welke waarneembare netwerksporen rond een gedefinieerde stimulus ondersteunen beter een push-verklaring dan een pull-verklaring voor statusovergang?"

Scope:

- In-scope: `IPBox <-> controllers` en zichtbare module/REST-stromen op gekozen mirror-POV.
- Out-of-scope: interne veldbus-elektronica buiten Ethernet-capture.
- ARP is secundair: alleen classificatie/context, nooit primaire causaliteitsclaim.

## 2) Operationele definities (t0, immediate/delayed, H1/H2/H3)

`t0`
Tijdstip van stimulus-anker:

- bij `rest_action`: manifest-event `rest_action` timestamp;
- bij fysieke actie: manifest-event `physical_input` timestamp.
`t0` wordt altijd in UTC en monotonic context gelogd (manifest).

Immediate status
Netwerkindicatie van statusverandering binnen `[t0, t0+2s]`.

Delayed status
Netwerkindicatie van statusverandering binnen `(t0+2s, t0+20s]`.

Hypothesen:

- `H1 (push-dominant)`: na `t0` verschijnt een consistente, stimulus-gekoppelde frame-/payloadverandering zonder afhankelijkheid van periodieke polling.
- `H2 (pull-dominant)`: status wordt pas zichtbaar op/na pollingmomenten; geen stabiel direct eventpatroon rond `t0`.
- `H3 (hybride)`: directe eventindicatie en latere poll-confirmatie; beide dragen aantoonbaar bij.

## 3) Capture POV-lock vereisten + verplichte run-metadata

POV-lock (verplicht):

- Een expliciete capture-interface per run (typisch `en7`), vastgelegd voor start.
- Mirrorbron/-bestemming vastgezet en gedocumenteerd (poortnummers + betrokken hosts).
- Capture start voor eerste stimulus en bevat settle-window pre/post.
- Geen POV-wijziging tijdens run; wijziging betekent nieuwe run-ID.

Verplichte run-metadata (minimum):

- `run_id`, UTC starttijd, operator, host, interface, mirrorbron/-dest.
- Exacte BPF-string (ongewijzigd opgeslagen).
- Runbook-pad + hash/versie, scriptversie (`ipbuilding_capture_run.py`), commando.
- Doelhypothese (`H1`/`H2`/`H3` focus), stimulusplan (IDs, volgorde, pauzes).
- Artefacten: `capture.pcapng`, `manifest.jsonl`, `run.log`, `runbook.yaml`, `README.txt`, plus relevante snapshots (`inventory_pre`, `ip1100_getbuttons_*` indien gebruikt).

## 4) Exacte voorgestelde BPF-strings

Run A — project default (referentiepad, protocolbreed op bekende scope):

```bpf
udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185) or tcp port 30200 or (tcp port 80 and (host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50))
```

Run B — breadth rond hosts (niet-UDP zichtbaarheid, ARP niet leidend):

```bpf
(host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185) and (udp or tcp or icmp or arp)
```

Run C — idle baseline (zelfde scope als A, zonder stimulus):

```bpf
udp and (host 10.10.1.1 or host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50 or host 192.168.0.185) or tcp port 30200 or (tcp port 80 and (host 10.10.1.30 or host 10.10.1.40 or host 10.10.1.50))
```

## 5) Acceptatiegates en confidence rules

Gate `G1` — reproduceerbaarheid:

- Minimaal 2 runs per hypothese-pad met gelijkwaardige uitkomstklasse (`H1`/`H2`/`H3`).
- Geen POV drift, complete metadata aanwezig.

Gate `G2` — temporal evidence:

- Elke claim koppelt aan expliciet `t0`-anker en venster (`immediate`/`delayed`).
- "Immediate" zonder `t0`-anker is ongeldig.

Gate `G3` — protocolbreedte:

- Minstens een run met non-UDP zichtbaarheid (Run B) geanalyseerd.
- ARP-only bevindingen krijgen label "contextueel", niet "causaal".

Gate `G4` — baseline-separatie:

- Idle baseline (Run C) beschikbaar om periodieke achtergrondframes te onderscheiden van stimulusrespons.

Confidence rules:

- High: consistent patroon over >=2 runs, baseline-onderscheid helder, protocolbreed bevestigd.
- Medium: patroon zichtbaar maar deels ambigu (bijvoorbeeld alleen een protocol of beperkte herhaling).
- Low: enkel incidenteel of ARP-only signaal, of ontbrekende baseline/metadata.

## 6) Handoff checklist naar runner agent

- Bevestig run-doel: welke hypothese (`H1`/`H2`/`H3`) wordt primair getest?
- Bevestig POV-lock: interface, mirrorbron/-dest, geen wijzigingen tijdens run.
- Gebruik exacte BPF-string van gekozen runtype (A/B/C) en log die letterlijk.
- Start capture voor eerste stimulus; respecteer settle pre/post windows.
- Log alle stimuli met `t0`-anker in `manifest.jsonl` (UTC + monotonic aanwezig).
- Archiveer verplichte artefacten in sessiemapcontract.
- Voer eerste triage uit: immediate vs delayed observaties, plus baselinevergelijking.
- Rapporteer conclusie als evidence statement: "data ondersteunt Hx met confidence Y", inclusief tegenbewijs/ambiguiteit.

