# WebUI — "Actief"-checkbox als groene ronde toggle

**Datum:** 2026-07-13
**Type:** Design spec (UI-only, ingress webUI)
**Status:** Approved (2026-07-13)
**Scope:** `gateway/webui.py` — enkel de `Actief`-kolom in de device-tabel per module.

---

## 1. Doel

De `Actief`-checkbox in de webUI-devicetabel ([gateway/webui.py](gateway/webui.py)) is een kale browser-checkbox en oogt minder verzorgd dan de nieuwe module-brede "Enabled"-slider (zie eerdere sessie). Doel: visueel consistenter maken zonder de betekenis of het save-gedrag te wijzigen.

## 2. Waarom geen volwaardige slider

Een toggle-switch (track + schuivende knop) draagt in UI-conventies de betekenis "klik = direct effect" (lichtschakelaar-metafoor). `Actief` valt hier echter — net als Naam/Room/Type/Max Watt — onder het rij-brede batched-save-model: wijzigingen worden pas naar `PATCH /api/v1/devices/{id}` gestuurd bij klikken op **Save**. Een slider zou die verwachting doorbreken (gebruiker verwacht instant effect, krijgt dat niet).

Een radiobutton-achtige indicator (rond, gevuld = aan) hoort in formulier-conventies juist bij "markering die pas effect heeft na indienen" — dat sluit aan bij het bestaande gedrag. Een *echte* `<input type="radio">` is hier semantisch fout (radio's horen bij een keuze-groep; `Actief` is een onafhankelijke aan/uit-waarde per rij), dus dit wordt een **checkbox die eruitziet als een radiobutton**.

## 3. Design

Eén CSS-regel-set, geen extra HTML-elementen (geen wrapper-`<label>`/`<span>` zoals bij de sliderstijl):

```css
input[type=checkbox].active-toggle {
  appearance: none;
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-radius: 50%;
  cursor: pointer;
  vertical-align: middle;
}
input[type=checkbox].active-toggle:checked {
  background: var(--ok);
  border-color: var(--ok);
}
```

`buildActiveCell()` krijgt enkel een extra `class: "active-toggle"` op de bestaande `<input type="checkbox">`. Verder ongewijzigd:

- `state.active` blijft dezelfde `<input>`-referentie.
- `currentValue()`/`buildPatch()` blijven ongewijzigd (lezen `.checked` zoals vandaag).
- Save-gedrag ongewijzigd: onderdeel van de rij-brede patch, pas verstuurd bij klikken op **Save**.

De module-brede "Enabled"-slider (`buildDisabledSwitch()`/`buildModuleActions()`) blijft een aparte, ongewijzigde component — andere UI-context (module-samenvatting, nog niet geïmplementeerd), geen gedeelde helper nodig.

## 4. Niet in scope

- Geen wijziging aan de PATCH-endpoint of backend.
- Geen wijziging aan save-timing van andere velden.
- Geen hergebruik/samenvoeging met de module-toggle-component.
