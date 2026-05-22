# Brief: documentatie reorganiseren (voor subagent)

Last updated: 2026-05-22

**Doel:** mappenstructuur zonder inhoud te wijzigen; alle links in repo bijwerken.

**Niet doen:** RE-conclusies herschrijven; PCAPs verplaatsen uit `captures/` (blijft gitignored op repo-root).

## Voorgestelde structuur

```
resources_and_docs/
  README.md              ← blijft (index)
  RE_STATE.md            ← blijft canoniek in root van resources_and_docs
  CAPTURES.md
  IPBUILDING_KNOWLEDGE.md
  2026-05-17_ipbuilding_fieldbus_capability_matrix.md
  workflows/
    IPBUILDING_CAPTURE_WORKFLOW.md
    CAPTURE_LIVE_STATUS.md
    SUBAGENT_CAPTURE_EXECUTION_WORKFLOW.md
    *_runbook.yaml
    *playbook*.md
  evidence/
    2026-05-*_*.md       ← alle gedateerde RE-sessie/evidence markdown
  reference/
    IPBOX_REST_API_TEST_CALLS.md
    device-inventory-local-ipbox.md
    RE_WIZARDS*.md
    scan_modules*.md
  archive/
    NEXT_AGENT_STATUS_QUO_*.md
    2026-05-17_ipbuilding_gateway_parity_matrix.md
    2026-05-17_RE_TEST_PLAN_5_SPRINTS.md
  pcap_archive/          ← blijft

docs/
  README.md
  context-policy.md
  superpowers/
    specs/               ← ongewijzigd
    plans/               ← ongewijzigd
```

## Uitvoeringsvolgorde (subagent)

1. Maak mappen aan; `git mv` bestanden (geen copy-delete).
2. Ripgrep op oude paden: `resources_and_docs/2026-05-`, `AGENTS.md`, `.cursor/rules`, `RE_STATE.md` evidence pointers.
3. Update [README.md](README.md) paden.
4. Voeg redirects toe: één regel bovenaan verplaatste bestanden `> Verplaatst naar: …` **alleen** als externe links bestaan; anders alleen linkfix in repo.
5. Geen wijziging aan `captures/` of `gateway/`.

## Acceptatiecriteria

- `RE_STATE.md` blijft vindbaar op hetzelfde pad **of** één duidelijke redirect vanaf oude URL.
- Alle interne markdown-links in repo slagen (handmatig of `rg` check).
- `AGENTS.md` doc-index verwijst naar nieuwe index.
- Geen duplicate inhoud.

## Completed 2026-05-22

Reorganisatie uitgevoerd. Bestanden zijn met `mv` verplaatst (meeste paden waren nog untracked; geen `git mv` mogelijk). **Geen stub-redirects** toegevoegd — alleen repo-interne links bijgewerkt (~82+ padvervangingen in 26+ bestanden).

### Final tree

```
resources_and_docs/
  README.md
  REORGANIZE_BRIEF.md
  RE_STATE.md
  CAPTURES.md
  IPBUILDING_KNOWLEDGE.md
  2026-05-17_ipbuilding_fieldbus_capability_matrix.md
  workflows/          (18: 4 md + 14 yaml)
  evidence/           (15 md)
  reference/          (6 md)
  archive/            (3 md)
  pcap_archive/
  (+ PDFs, images, legacy pcap at root — ongewijzigd)
```

### Root keep list (bewust niet verplaatst)

- Canoniek: `RE_STATE.md`, `CAPTURES.md`, `IPBUILDING_KNOWLEDGE.md`, `README.md`
- Field-bus matrix: `2026-05-17_ipbuilding_fieldbus_capability_matrix.md`
- Binaries: `pcap_archive/`, PDFs, JPEGs, `traffic between controller an IPbox.pcapng`

### Link rules toegepast

- Van `RE_STATE.md` naar evidence: `evidence/2026-05-….md`
- Van `docs/superpowers/` naar resources: `../../resources_and_docs/{workflows|evidence|reference|archive}/…`
- Van `workflows/` naar root: `../RE_STATE.md`, `../CAPTURES.md`

### Verification (post-fix)

- `rg 'resources_and_docs/2026-05-[^/]+\.md'` → alleen **fieldbus matrix** in root (verwacht)
- `rg 'resources_and_docs/IPBUILDING_CAPTURE'` → **geen hits** (alle → `workflows/`)
- `rg 'resources_and_docs/CAPTURE_LIVE'` → **geen hits** (alle → `workflows/`)
