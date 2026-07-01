# Add-on README presentation — design spec

**Date:** 2026-07-01  
**Status:** Approved  
**Scope:** `ipbuilding_gateway/README.md` (new)

## Problem

The IPBuilding Gateway add-on lacks the About/intro section that other HA add-ons
show in the Supervisor UI. Operators do not see a clear landing page with version
context, companion requirement, and install links.

## Root cause

HA renders the add-on **Info/About** section from `README.md` inside the add-on
folder. We had `DOCS.md`, `CHANGELOG.md`, and `icon.png`, but no `README.md` in
`ipbuilding_gateway/`.

## Solution (approach B)

Add a short `ipbuilding_gateway/README.md`:

| Section | Content |
|---------|---------|
| Title + tagline | What the add-on does |
| Warning callout | Companion required for HA entities |
| About | Field-bus hub role, northbound API |
| Table | Add-on only vs add-on + companion |
| Companion install | HACS my.home-assistant.io badge + manual steps |
| Discovery hint | Settings → Discovered after both installed |
| Install pointer | Defer to **Documentatie** tab (`DOCS.md`) |
| Support | Companion repo, gateway releases, issues |

`DOCS.md` remains the full operator manual. No `config.yaml` or image changes.

## Out of scope

- `logo.png`
- shields.io dynamic badges
- Companion repo changes

## Success criteria

- Store/add-on info page shows About section with companion warning
- HACS link works via my.home-assistant.io redirect
- `DOCS.md` not duplicated; only cross-linked
