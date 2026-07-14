"""Self-contained ingress web UI: HTML+CSS+JS as a single string constant.

Served at GET / by GatewayAPI._get_webui. All fetch() calls inside this
page MUST use relative paths (e.g. "api/v1/devices", never "/api/v1/devices")
because the page is reached through the HA Supervisor ingress proxy at
/api/hassio_ingress/<token>/ — the browser's address bar keeps that prefix,
so a leading "/" would escape it and hit the HA frontend instead of this
add-on.
"""

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPBuilding Gateway</title>
<style>
  :root {
    color-scheme: light dark;
    --border: #d0d0d0;
    --bg-alt: #f5f5f5;
    --ok: #2e7d32;
    --err: #c62828;
  }
  @media (prefers-color-scheme: dark) {
    :root { --border: #444; --bg-alt: #2a2a2a; }
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 1rem;
  }
  h1 { font-size: 1.25rem; margin: 0 0 0.75rem; }
  .toolbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; }
  button {
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--bg-alt);
    border-radius: 4px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  button:hover:not(:disabled) { filter: brightness(0.95); }
  button:disabled { cursor: not-allowed; opacity: 0.5; }
  .btn-icon { display: inline-flex; align-items: center; gap: 0.35rem; }
  .btn-icon-svg { flex: none; width: 15px; height: 15px; fill: currentColor; }
  .btn-scan {
    background: transparent;
    border-color: #b26a00;
    color: #b26a00;
  }
  @media (prefers-color-scheme: dark) {
    .btn-scan { border-color: #d9922e; color: #d9922e; }
  }
  .danger-zone {
    margin-top: 1.5rem;
    padding: 0.85rem 1rem;
    border: 1px solid #b26a00;
    border-radius: 6px;
  }
  .danger-zone h2 { font-size: 1rem; margin: 0 0 0.35rem; color: #b26a00; }
  .danger-note { font-size: 0.8rem; color: #888; margin: 0 0 0.85rem; }
  .danger-action { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
  .danger-action:last-child { margin-bottom: 0; }
  .danger-desc { font-size: 0.78rem; color: #888; margin: 0; flex-basis: 100%; }
  @media (prefers-color-scheme: dark) {
    .danger-zone { border-color: #d9922e; }
    .danger-zone h2 { color: #d9922e; }
  }
  table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
  th, td { border: 1px solid var(--border); padding: 0.3rem 0.5rem; text-align: left; }
  th { background: var(--bg-alt); position: sticky; top: 0; }
  input[type=text], select, input[type=number] {
    width: 100%;
    box-sizing: border-box;
    font-size: 0.85rem;
    padding: 0.15rem 0.25rem;
  }
  input[type=number] { width: 6rem; }
  input[type=checkbox].active-toggle {
    appearance: none;
    position: relative;
    width: 16px;
    height: 16px;
    border: 2px solid var(--border);
    border-radius: 50%;
    cursor: pointer;
    vertical-align: middle;
    background: transparent;
  }
  input[type=checkbox].active-toggle:checked {
    border-color: var(--ok);
  }
  input[type=checkbox].active-toggle:checked::after {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--ok);
  }
  .muted { color: #888; }
  .type-cell { display: flex; align-items: center; gap: 0.35rem; }
  .type-icon { flex: none; width: 16px; height: 16px; fill: #888; }
  /* Icon sits inside the native <select> (padding-left); dropdown stays OS-native. */
  .type-select-native { position: relative; min-width: 6.5rem; }
  .type-select-native .type-icon {
    position: absolute;
    left: 0.35rem;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    z-index: 1;
  }
  .type-select-native select { padding-left: 1.6rem; }
  .status { font-size: 0.78rem; white-space: nowrap; }
  .status.ok { color: var(--ok); }
  .status.err { color: var(--err); }
  .empty { padding: 1rem; color: #888; }

  .module { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 1.25rem; overflow: hidden; }
  .module-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem 1rem;
    background: var(--bg-alt);
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--border);
  }
  .module-title { display: flex; flex-direction: column; gap: 0.1rem; min-width: 0; }
  .module-name-row { display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap; }
  .module-name { font-size: 1.05rem; font-weight: 600; }
  .module-model { font-size: 0.85rem; color: #888; }
  .module-type-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #888;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0.05rem 0.35rem;
  }
  .hub-role-badge {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #555;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.1rem 0.45rem;
    cursor: help;
  }
  .hub-role-badge--slave {
    color: var(--ok);
    border-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 10%, transparent);
  }
  @media (prefers-color-scheme: dark) {
    .hub-role-badge { color: #ccc; }
    .hub-role-badge--slave {
      color: #81c784;
      border-color: #81c784;
      background: color-mix(in srgb, #81c784 12%, transparent);
    }
  }
  .module-sub { font-size: 0.75rem; color: #888; }
  .module-actions {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    justify-content: flex-end;
    gap: 0.5rem;
  }
  .module-action {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    min-width: 3.25rem;
  }
  .module-action-label { font-size: 0.62rem; color: #888; text-align: center; line-height: 1.1; }
  .module-action-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    padding: 0;
    border: none;
    background: transparent;
    border-radius: 4px;
  }
  .module-action-icon { width: 18px; height: 18px; fill: currentColor; }
  .module-action-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .module-action-btn--push { color: #b26a00; }
  @media (prefers-color-scheme: dark) {
    .module-action-btn--push { color: #d9922e; }
  }
  .module-action--enable .switch {
    flex-direction: column;
    gap: 0;
    width: 2rem;
    height: 2rem;
    align-items: center;
    justify-content: center;
  }
  .module-action--enable .switch-label { display: none; }
  .module-action-status { font-size: 0.58rem; min-height: 0.75rem; }
  .module-table { margin: 0; }

  .switch { position: relative; display: inline-flex; align-items: center; gap: 0.4rem; }
  .switch-track {
    position: relative;
    width: 32px;
    height: 18px;
    background: #ccc;
    border-radius: 18px;
    display: inline-block;
    opacity: 0.6;
  }
  .switch-track::before {
    content: "";
    position: absolute;
    left: 2px;
    top: 2px;
    width: 14px;
    height: 14px;
    background: #fff;
    border-radius: 50%;
    transition: transform 0.15s;
  }
  .switch input:checked + .switch-track { background: var(--ok); }
  .switch input:checked + .switch-track::before { transform: translateX(14px); }
  .switch-label { font-size: 0.78rem; color: #888; min-width: 4.5em; }
</style>
</head>
<body>
<h1>IPBuilding Gateway — devices</h1>
<div class="toolbar">
  <button id="reload" class="btn-icon" title="Reload the list on screen. Read-only — no changes saved.">Refresh</button>
  <span id="toolbarStatus" class="status"></span>
</div>
<div id="content">Loading…</div>

<section class="danger-zone">
  <h2>Backup &amp; restore</h2>
  <p class="danger-note">Save or restore your full installation — channel names, rooms, wattages, and which devices are active. Upload and Reset replace what the gateway is using now.</p>
  <div class="danger-action">
    <button id="exportDevices" class="btn-icon" type="button">Download backup</button>
    <span id="exportStatus" class="status"></span>
    <p class="danger-desc">Save your current setup to your computer. Do this before updates, network scans, or other major changes.</p>
  </div>
  <div class="danger-action">
    <button id="importDevices" class="btn-icon" type="button">Restore from backup</button>
    <input id="importFile" type="file" accept=".json,application/json" style="display:none">
    <span id="importStatus" class="status"></span>
    <p class="danger-desc">Replace the running setup with a file you saved earlier. The gateway checks the file first — if anything is invalid, nothing changes.</p>
  </div>
  <div class="danger-action">
    <button id="resetDevices" class="btn-icon btn-scan" type="button">Clear all devices</button>
    <span id="resetStatus" class="status"></span>
    <p class="danger-desc">Remove every module and channel from the gateway. Entities in Home Assistant disappear until you search for modules again. Download a backup first — this cannot be undone.</p>
  </div>
</section>

<section class="danger-zone">
  <h2>Installation &amp; network</h2>
  <p class="danger-note">Talks to your physical modules. Separate from editing the table above.</p>
  <div class="danger-action">
    <button id="discoverModules" class="btn-scan">Search for new modules</button>
    <span id="discoverStatus" class="status"></span>
    <p class="danger-desc">Scans the field-bus network for new modules. Can take a minute. New modules are added disabled — enable them in the table above.</p>
  </div>
</section>

<script>
(function () {
  "use strict";

  var DEVICES_URL = "api/v1/devices";
  var MODULES_URL = "api/v1/modules";
  var STATUS_URL = "api/v1/status";
  var EXPORT_URL = "api/v1/devices/export";
  var IMPORT_URL = "api/v1/devices/import";
  var RESET_URL = "api/v1/devices/reset";
  var SEMANTIC_TYPES = ["light", "fan", "cover", "switch", "plug"];
  var NOT_IMPLEMENTED = "Not yet implemented";
  var HUB_ROLE_TOOLTIP =
    "Slave: buttons via Home Assistant (LED steady). " +
    "Master: buttons local on the input module (LED blinking); relays/dimmers still via HA. " +
    "If the gateway fails, the module falls back to its own stored pairings. " +
    "Change via Settings → Add-ons → IPBuilding Gateway → Configuration (restart required).";
  var gatewayInputModeLabel = "Slave";
  // Exactly the icons the HA companion assigns per semantic_type (source of
  // truth: ha-ipbuilding-gateway/custom_components/ha_ipbuilding_gateway/
  // entity.py _SEMANTIC_ICONS, plus event.py's _attr_icon for buttons), so
  // this page and the companion's entities look the same. Inlined as raw
  // MDI SVG path data (source: Templarian/MaterialDesign-SVG) rather than
  // an icon font/CDN, so the page stays self-contained and light enough to
  // fit the future embedded gateway target (no font file to bundle/serve).
  var ICONS = {
    light: "M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21A1,1 0 0,0 10,22H14A1,1 0 0,0 15,21V20H9V21Z",
    fan: "M12,11A1,1 0 0,0 11,12A1,1 0 0,0 12,13A1,1 0 0,0 13,12A1,1 0 0,0 12,11M12.5,2C17,2 17.11,5.57 14.75,6.75C13.76,7.24 13.32,8.29 13.13,9.22C13.61,9.42 14.03,9.73 14.35,10.13C18.05,8.13 22.03,8.92 22.03,12.5C22.03,17 18.46,17.1 17.28,14.73C16.78,13.74 15.72,13.3 14.79,13.11C14.59,13.59 14.28,14 13.88,14.34C15.87,18.03 15.08,22 11.5,22C7,22 6.91,18.42 9.27,17.24C10.25,16.75 10.69,15.71 10.89,14.79C10.4,14.59 9.97,14.27 9.65,13.87C5.96,15.85 2,15.07 2,11.5C2,7 5.56,6.89 6.74,9.26C7.24,10.25 8.29,10.68 9.22,10.87C9.41,10.39 9.73,9.97 10.14,9.65C8.15,5.96 8.94,2 12.5,2Z",
    cover: "M20 19V3H4V19H2V21H22V19H20M16 9H18V11H16V9M14 11H6V9H14V11M18 7H16V5H18V7M14 5V7H6V5H14M6 19V13H14V14.82C13.55 15.14 13.25 15.66 13.25 16.25C13.25 17.22 14.03 18 15 18S16.75 17.22 16.75 16.25C16.75 15.66 16.45 15.13 16 14.82V13H18V19H6Z",
    switch: "M18.4 1.6C18 1.2 17.5 1 17 1H7C6.5 1 6 1.2 5.6 1.6C5.2 2 5 2.5 5 3V21C5 21.5 5.2 22 5.6 22.4C6 22.8 6.5 23 7 23H17C17.5 23 18 22.8 18.4 22.4C18.8 22 19 21.5 19 21V3C19 2.5 18.8 2 18.4 1.6M16 7C16 7.6 15.6 8 15 8H9C8.4 8 8 7.6 8 7V5C8 4.4 8.4 4 9 4H15C15.6 4 16 4.4 16 5V7Z",
    plug: "M16,7V3H14V7H10V3H8V7H8C7,7 6,8 6,9V14.5L9.5,18V21H14.5V18L18,14.5V9C18,8 17,7 16,7Z",
    button: "M13 5C15.21 5 17 6.79 17 9C17 10.5 16.2 11.77 15 12.46V11.24C15.61 10.69 16 9.89 16 9C16 7.34 14.66 6 13 6S10 7.34 10 9C10 9.89 10.39 10.69 11 11.24V12.46C9.8 11.77 9 10.5 9 9C9 6.79 10.79 5 13 5M20 20.5C19.97 21.32 19.32 21.97 18.5 22H13C12.62 22 12.26 21.85 12 21.57L8 17.37L8.74 16.6C8.93 16.39 9.2 16.28 9.5 16.28H9.7L12 18V9C12 8.45 12.45 8 13 8S14 8.45 14 9V13.47L15.21 13.6L19.15 15.79C19.68 16.03 20 16.56 20 17.14V20.5M20 2H4C2.9 2 2 2.9 2 4V12C2 13.11 2.9 14 4 14H8V12L4 12L4 4H20L20 12H18V14H20V13.96L20.04 14C21.13 14 22 13.09 22 12V4C22 2.9 21.11 2 20 2Z",
    reload: "M2 12C2 16.97 6.03 21 11 21C13.39 21 15.68 20.06 17.4 18.4L15.9 16.9C14.63 18.25 12.86 19 11 19C4.76 19 1.64 11.46 6.05 7.05C10.46 2.64 18 5.77 18 12H15L19 16H19.1L23 12H20C20 7.03 15.97 3 11 3C6.03 3 2 7.03 2 12Z",
    download: "M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z",
    upload: "M9,16V10H5L12,3L19,10H15V16H9Z",
    // Dimmer-on-light special case (see below).
    brightness6: "M12,18V6A6,6 0 0,1 18,12A6,6 0 0,1 12,18M20,15.31L23.31,12L20,8.69V4H15.31L12,0.69L8.69,4H4V8.69L0.69,12L4,15.31V20H8.69L12,23.31L15.31,20H20V15.31Z",
  };

  // Mirrors the HA companion's entity_icon() (entity.py): a dimmer channel
  // typed "light" gets the brightness icon instead of the plain lightbulb,
  // since it's brightness-capable rather than a plain relay-driven light.
  function iconPathFor(semanticType, deviceType) {
    if (semanticType === "light" && deviceType === "dimmer") return ICONS.brightness6;
    return ICONS[semanticType];
  }

  function svgIcon(pathData, className) {
    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", className);
    var path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", pathData || "");
    svg.appendChild(path);
    return svg;
  }

  function buildTypeIcon(type, deviceType) {
    return svgIcon(iconPathFor(type, deviceType), "type-icon");
  }

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function isChannel(device) {
    return device.device_type === "relay" || device.device_type === "dimmer";
  }

  function buildChannelCell(device, moduleType) {
    var hasChannel = typeof device.channel === "number";
    var title = moduleType === "input"
      ? "Physical input port on IP1100 (0–7)"
      : "Channel number on this module";
    return el(
      "td",
      { class: "muted", title: title },
      [document.createTextNode(hasChannel ? String(device.channel) : "—")]
    );
  }

  function channelColumnLabel(moduleType) {
    return moduleType === "input" ? "Port" : "Ch";
  }

  function buildNameCell(device, state) {
    var input = el("input", { type: "text", value: device.name || "" });
    state.name = input;
    return el("td", {}, [input]);
  }

  function buildRoomCell(device, state) {
    var input = el("input", { type: "text", value: device.room || "" });
    state.room = input;
    return el("td", {}, [input]);
  }

  function buildTypeCell(device, state) {
    if (!isChannel(device) || !("semantic_type" in device)) {
      state.semantic_type = null;
      var icon = svgIcon(ICONS.button, "type-icon");
      var label = document.createTextNode(device.device_type || "—");
      return el("td", {}, [el("div", { class: "type-cell muted" }, [icon, label])]);
    }
    // Dimmer hardware is always a brightness-capable light in HA/Matter.
    if (device.device_type === "dimmer") {
      state.semantic_type = null;
      var dimmerIcon = buildTypeIcon("light", "dimmer");
      var dimmerLabel = document.createTextNode("light");
      return el("td", {}, [el("div", { class: "type-cell muted" }, [dimmerIcon, dimmerLabel])]);
    }
    var select = el("select", {});
    SEMANTIC_TYPES.forEach(function (t) {
      var opt = el("option", { value: t, text: t });
      if (t === device.semantic_type) opt.selected = true;
      select.appendChild(opt);
    });
    state.semantic_type = select;
    var wrap = el("div", { class: "type-cell type-select-native" });
    var typeIcon = buildTypeIcon(device.semantic_type, device.device_type);
    select.addEventListener("change", function () {
      typeIcon.querySelector("path").setAttribute(
        "d",
        iconPathFor(select.value, device.device_type) || ""
      );
    });
    wrap.appendChild(typeIcon);
    wrap.appendChild(select);
    return el("td", {}, [wrap]);
  }

  function buildActiveCell(device, state) {
    var input = el("input", { type: "checkbox", class: "active-toggle" });
    // A missing "active" key means the button isn't yet in devices.json's
    // buttons[] (only known via live getButtons metadata) — the companion
    // treats that as enabled-by-default (entity.py: device.get("active",
    // True)), so this must too, or freshly-discovered buttons would
    // wrongly show as disabled.
    input.checked = device.active !== false;
    state.active = input;
    return el("td", {}, [input]);
  }

  function buildWattCell(device, state) {
    if (!isChannel(device) || !("max_watt" in device)) {
      state.max_watt = null;
      return el("td", { class: "muted" }, [document.createTextNode("—")]);
    }
    var input = el("input", { type: "number", min: "0", step: "1", value: device.max_watt });
    state.max_watt = input;
    return el("td", {}, [input]);
  }

  function currentValue(fieldName, inputEl) {
    if (inputEl === null) return undefined;
    if (fieldName === "active") return inputEl.checked;
    if (fieldName === "max_watt") return parseInt(inputEl.value, 10);
    return inputEl.value;
  }

  function buildPatch(device, state) {
    var patch = {};
    var fields = ["name", "room", "semantic_type", "active", "max_watt"];
    fields.forEach(function (f) {
      var inputEl = state[f];
      if (inputEl === null || inputEl === undefined) return;
      var value = currentValue(f, inputEl);
      var original = f === "active" ? device.active !== false : device[f];
      if (value !== original) patch[f] = value;
    });
    return patch;
  }

  function setStatus(span, text, kind) {
    span.textContent = text;
    span.className = "status" + (kind ? " " + kind : "");
  }

  function errorMessage(status, body) {
    if (status === 404) return "Device no longer exists — reload";
    if (status === 503) return "Busy, try again";
    if (body && body.message) return body.message;
    return "Save failed (" + status + ")";
  }

  // Backend message for scan-action errors (503 orchestrator_unavailable,
  // 500 no_installation, ...) means something different per action, so
  // (unlike errorMessage() above) this just surfaces the server's own
  // message rather than guessing a fixed phrase per status code.
  function describeActionError(status, body) {
    if (body && body.message) return body.message;
    return "Failed (" + status + ")";
  }

  function saveRow(device, state, statusSpan, onSaved) {
    var patch = buildPatch(device, state);
    if (Object.keys(patch).length === 0) {
      setStatus(statusSpan, "No changes", "");
      return;
    }
    setStatus(statusSpan, "Saving…", "");
    fetch(DEVICES_URL + "/" + encodeURIComponent(device.id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { status: resp.status, body: body };
        });
      })
      .then(function (result) {
        if (result.status === 200) {
          setStatus(statusSpan, "Saved", "ok");
          onSaved(result.body);
        } else {
          setStatus(statusSpan, errorMessage(result.status, result.body), "err");
        }
      })
      .catch(function () {
        setStatus(statusSpan, "Network error", "err");
      });
  }

  function buildRow(device, moduleType) {
    var state = {};
    var tr = el("tr", { "data-id": device.id, "data-type": device.device_type });

    tr.appendChild(buildChannelCell(device, moduleType));
    tr.appendChild(buildNameCell(device, state));
    tr.appendChild(buildRoomCell(device, state));
    tr.appendChild(buildTypeCell(device, state));
    tr.appendChild(buildActiveCell(device, state));
    tr.appendChild(buildWattCell(device, state));

    var statusSpan = el("span", { class: "status" });
    var saveBtn = el("button", { text: "Save" });
    saveBtn.addEventListener("click", function () {
      saveRow(device, state, statusSpan, function (updated) {
        Object.assign(device, updated);
      });
    });
    tr.appendChild(el("td", {}, [saveBtn, statusSpan]));

    return tr;
  }

  function sortDeviceRows(devices) {
    return devices.slice().sort(function (a, b) {
      var aHasCh = typeof a.channel === "number";
      var bHasCh = typeof b.channel === "number";
      // Relay/dimmer channels and input pushbuttons (physical port) sort by
      // channel number when present; otherwise fall back to room-then-name.
      if (aHasCh && bHasCh) return a.channel - b.channel;
      if (aHasCh !== bHasCh) return aHasCh ? -1 : 1;
      var ar = (a.room || "").toLowerCase();
      var br = (b.room || "").toLowerCase();
      if (ar !== br) return ar < br ? -1 : 1;
      var an = (a.name || "").toLowerCase();
      var bn = (b.name || "").toLowerCase();
      return an < bn ? -1 : an > bn ? 1 : 0;
    });
  }

  // -- Module grouping ------------------------------------------------------
  // Groups the flat /api/v1/devices list by module_id (matches a module's
  // "id", which is its MAC). Devices whose module isn't in /api/v1/modules
  // (e.g. stale/partial data) fall back into a synthetic "unknown" module
  // keyed by module_ip so nothing silently disappears from the page.

  function groupDevicesByModule(devices, modules) {
    var byId = {};
    modules.forEach(function (m) { byId[m.id] = m; });

    var groups = {}; // module.id (or "unknown:<ip>") -> { module, devices }
    devices.forEach(function (device) {
      var mod = byId[device.module_id];
      var key = mod ? mod.id : "unknown:" + (device.module_ip || "?");
      if (!groups[key]) {
        groups[key] = {
          module: mod || {
            id: key,
            ip: device.module_ip || "",
            name: "Unknown module",
            model: "",
            type: "",
            firmware: "",
          },
          devices: [],
        };
      }
      groups[key].devices.push(device);
    });
    return Object.keys(groups)
      .map(function (k) { return groups[k]; })
      .sort(function (a, b) {
        var an = (a.module.name || a.module.ip || "").toLowerCase();
        var bn = (b.module.name || b.module.ip || "").toLowerCase();
        return an < bn ? -1 : an > bn ? 1 : 0;
      });
  }

  function buildHubRoleBadge(label) {
    var text = label || "Slave";
    var cls = "hub-role-badge";
    if (text.toLowerCase() === "slave") cls += " hub-role-badge--slave";
    return el("span", {
      class: cls,
      title: HUB_ROLE_TOOLTIP,
      text: text,
    });
  }

  function buildIconAction(label, iconPath, opts) {
    opts = opts || {};
    var wrap = el("div", { class: "module-action" });
    var btnClass = "module-action-btn";
    if (opts.push) btnClass += " module-action-btn--push";
    var btn = el("button", { type: "button", class: btnClass, title: opts.title || label });
    if (opts.disabled) btn.disabled = true;
    btn.appendChild(svgIcon(iconPath, "module-action-icon"));
    wrap.appendChild(btn);
    wrap.appendChild(el("span", { class: "module-action-label", text: label }));
    var statusSpan = el("span", { class: "module-action-status status" });
    wrap.appendChild(statusSpan);
    return { wrap: wrap, button: btn, status: statusSpan };
  }

  function wireModuleUpdate(module, btn, statusSpan) {
    btn.addEventListener("click", function () {
      if (!module.id) return;
      btn.disabled = true;
      setStatus(statusSpan, "Updating…", "");
      fetch(
        MODULES_URL + "/" + encodeURIComponent(module.id) + "/refresh",
        { method: "POST" }
      )
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (result) {
          if (result.status === 200) {
            setStatus(statusSpan, "Updated", "ok");
            load();
          } else {
            setStatus(statusSpan, describeActionError(result.status, result.body), "err");
          }
        })
        .catch(function () {
          setStatus(statusSpan, "Network error", "err");
        })
        .then(function () {
          btn.disabled = false;
        });
    });
  }

  function buildModuleActions(module) {
    var wrap = el("div", { class: "module-actions" });
    // DOM order left-to-right: Push, Fetch, Update (Update rightmost).
    var push = buildIconAction("Push", ICONS.upload, {
      disabled: true,
      push: true,
      title: NOT_IMPLEMENTED,
    });
    var fetchAct = buildIconAction("Fetch", ICONS.download, {
      disabled: true,
      title: NOT_IMPLEMENTED,
    });
    var update = buildIconAction("Update", ICONS.reload, {
      title: "Re-read this module. No changes saved.",
    });
    if (module.type === "input") {
      update.button.title = "Re-read this module and refresh its button list.";
    }
    wireModuleUpdate(module, update.button, update.status);
    wrap.appendChild(push.wrap);
    wrap.appendChild(fetchAct.wrap);
    wrap.appendChild(update.wrap);
    return wrap;
  }

  function buildModuleHeader(module) {
    var nameRow = el("div", { class: "module-name-row" }, [
      el("span", { class: "module-name", text: module.name || module.ip || "?" }),
    ]);
    if (module.model) {
      nameRow.appendChild(el("span", { class: "module-model", text: module.model }));
    }
    if (module.type) {
      nameRow.appendChild(el("span", { class: "module-type-badge", text: module.type }));
    }
    if (module.type === "input") {
      nameRow.appendChild(buildHubRoleBadge(gatewayInputModeLabel));
    }
    var subParts = [];
    if (module.ip) subParts.push(module.ip);
    if (module.firmware) subParts.push("fw " + module.firmware);
    var title = el("div", { class: "module-title" }, [
      nameRow,
      el("div", { class: "module-sub", text: subParts.join(" · ") }),
    ]);

    return el("div", { class: "module-header" }, [title, buildModuleActions(module)]);
  }

  function buildModuleSection(group) {
    var moduleType = group.module.type || "";
    var section = el("section", { class: "module" }, [buildModuleHeader(group.module)]);
    if (group.devices.length === 0) {
      section.appendChild(el("div", { class: "empty", text: "No devices in this module." }));
      return section;
    }
    var chLabel = channelColumnLabel(moduleType);
    var chTitle = moduleType === "input"
      ? "Physical input port on IP1100 (0–7)"
      : "Output channel on this module";
    var table = el("table", { class: "module-table" }, [
      el("thead", {}, [
        el("tr", {}, [
          el("th", { text: chLabel, title: chTitle }),
          el("th", { text: "Name" }),
          el("th", { text: "Room" }),
          el("th", { text: "Type" }),
          el("th", { text: "Active" }),
          el("th", { text: "Max Watt" }),
          el("th", { text: "" }),
        ]),
      ]),
    ]);
    var tbody = el("tbody", {});
    sortDeviceRows(group.devices).forEach(function (device) {
      tbody.appendChild(buildRow(device, moduleType));
    });
    table.appendChild(tbody);
    section.appendChild(table);
    return section;
  }

  function render(devices, modules) {
    var content = document.getElementById("content");
    content.innerHTML = "";
    if (devices.length === 0) {
      content.appendChild(el("div", { class: "empty", text: "No devices found." }));
      return;
    }
    groupDevicesByModule(devices, modules).forEach(function (group) {
      content.appendChild(buildModuleSection(group));
    });
  }

  function load() {
    var toolbarStatus = document.getElementById("toolbarStatus");
    setStatus(toolbarStatus, "Loading…", "");
    Promise.all([
      fetch(DEVICES_URL).then(function (resp) { return resp.json(); }),
      fetch(MODULES_URL).then(function (resp) { return resp.json(); }),
      fetch(STATUS_URL).then(function (resp) { return resp.json(); }),
    ])
      .then(function (results) {
        var devicesBody = results[0];
        var modulesBody = results[1];
        var statusBody = results[2];
        gatewayInputModeLabel = statusBody.input_mode_label || "Slave";
        render(devicesBody.devices || [], modulesBody.modules || []);
        setStatus(toolbarStatus, "", "");
      })
      .catch(function () {
        setStatus(toolbarStatus, "Could not load devices", "err");
      });
  }

  function wireScanButton(buttonId, statusId, opts) {
    var button = document.getElementById(buttonId);
    var status = document.getElementById(statusId);
    button.addEventListener("click", function () {
      button.disabled = true;
      setStatus(status, opts.runningText, "");
      fetch(opts.url, { method: "POST" })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (result) {
          if (result.status === 200) {
            setStatus(status, opts.summarize(result.body), "ok");
            load();
          } else {
            setStatus(status, describeActionError(result.status, result.body), "err");
          }
        })
        .catch(function () {
          setStatus(status, "Network error", "err");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  wireScanButton("discoverModules", "discoverStatus", {
    url: "api/v1/discover",
    runningText: "Scanning…",
    summarize: function (body) {
      var added = (body.added || []).length;
      var firmwareChanged = (body.firmware_changed || []).length;
      if (!added && !firmwareChanged) return "No changes";
      var parts = [];
      if (added) parts.push(added + " new module" + (added === 1 ? "" : "s"));
      if (firmwareChanged) parts.push(firmwareChanged + " firmware updated");
      return parts.join(", ");
    },
  });

  function wireExportButton() {
    var button = document.getElementById("exportDevices");
    var status = document.getElementById("exportStatus");
    button.addEventListener("click", function () {
      button.disabled = true;
      setStatus(status, "Downloading…", "");
      fetch(EXPORT_URL)
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().then(function (body) {
              throw new Error(describeActionError(resp.status, body));
            });
          }
          return resp.blob();
        })
        .then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url;
          a.download = "devices.json";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          setStatus(status, "Backup saved", "ok");
        })
        .catch(function (err) {
          setStatus(status, err.message || "Network error", "err");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  function wireImportButton() {
    var button = document.getElementById("importDevices");
    var fileInput = document.getElementById("importFile");
    var status = document.getElementById("importStatus");
    button.addEventListener("click", function () {
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      var file = fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      setStatus(status, "Uploading…", "");
      var reader = new FileReader();
      reader.onload = function () {
        fetch(IMPORT_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: reader.result,
        })
          .then(function (resp) {
            return resp.json().then(function (body) {
              return { status: resp.status, body: body };
            });
          })
          .then(function (result) {
            if (result.status === 200) {
              setStatus(
                status,
                "Loaded " + result.body.modules + " module(s), " +
                  result.body.channels + " channel(s)",
                "ok"
              );
              load();
            } else {
              setStatus(status, describeActionError(result.status, result.body), "err");
            }
          })
          .catch(function () {
            setStatus(status, "Network error", "err");
          });
      };
      reader.onerror = function () {
        setStatus(status, "Could not read file", "err");
      };
      reader.readAsText(file);
    });
  }

  function wireResetButton() {
    var button = document.getElementById("resetDevices");
    var status = document.getElementById("resetStatus");
    button.addEventListener("click", function () {
      if (!confirm("This removes all modules and channels from your gateway setup. Download a backup first if you want to keep your names and settings. Continue?")) {
        return;
      }
      button.disabled = true;
      setStatus(status, "Resetting…", "");
      fetch(RESET_URL, { method: "POST" })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (result) {
          if (result.status === 200) {
            setStatus(status, "Configuration cleared", "ok");
            load();
          } else {
            setStatus(status, describeActionError(result.status, result.body), "err");
          }
        })
        .catch(function () {
          setStatus(status, "Network error", "err");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  wireExportButton();
  wireImportButton();
  wireResetButton();

  document.getElementById("reload").prepend(svgIcon(ICONS.reload, "btn-icon-svg"));
  document.getElementById("reload").addEventListener("click", load);
  load();
})();
</script>
</body>
</html>
"""
