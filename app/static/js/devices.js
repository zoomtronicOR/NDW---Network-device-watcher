const COLUMNS = [
  { key: "status", label: "Status", sortable: true, default: true },
  { key: "device_type", label: "Tip", sortable: true, default: true },
  { key: "mac_address", label: "MAC", sortable: true, default: true },
  { key: "ip_address", label: "IP", sortable: true, default: true },
  { key: "hostname", label: "Hostname", sortable: true, default: true },
  { key: "vendor", label: "Vendor", sortable: true, default: true },
  { key: "connection_type", label: "Veza", sortable: true, default: true },
  { key: "wifi_rssi", label: "Signal", sortable: true, default: true, defaultOrder: "desc" },
  { key: "first_seen", label: "Prvi put viđen", sortable: true, default: false, defaultOrder: "desc" },
  { key: "last_seen", label: "Poslednji put viđen", sortable: true, default: true, defaultOrder: "desc" },
  { key: "custom_name", label: "Naziv", sortable: true, default: true },
  { key: "notes", label: "Beleška", sortable: true, default: false },
];

const COLUMNS_STORAGE_KEY = "nw_devices_columns";
const PAGE_SIZE_STORAGE_KEY = "nw_devices_page_size";

function loadPageSizePref() {
  try {
    const raw = localStorage.getItem(PAGE_SIZE_STORAGE_KEY);
    if (raw && [10, 50, 100].includes(Number(raw))) return Number(raw);
  } catch (e) {
    /* localStorage unavailable; fall back to default */
  }
  return 10;
}

const state = {
  page: 1,
  pageSize: loadPageSizePref(),
  sort: "last_seen",
  order: "desc",
  search: "",
  status: "",
  connectionType: "",
  trustedOnly: false,
  total: 0,
  visibleColumns: loadColumnPrefs(),
};

let searchDebounce = null;
let currentDeviceId = null;

// Columns added after a viewer saved their column choice are shown once by
// default instead of silently staying hidden.
const COLUMNS_KNOWN_KEY = "nw_devices_columns_known";

function loadColumnPrefs() {
  try {
    const raw = localStorage.getItem(COLUMNS_STORAGE_KEY);
    if (raw) {
      const set = new Set(JSON.parse(raw));
      const known = new Set(JSON.parse(localStorage.getItem(COLUMNS_KNOWN_KEY) || '["status","mac_address","ip_address","hostname","vendor","connection_type","wifi_rssi","first_seen","last_seen","custom_name","notes"]'));
      COLUMNS.forEach((c) => {
        if (!known.has(c.key) && c.default) set.add(c.key);
      });
      localStorage.setItem(COLUMNS_KNOWN_KEY, JSON.stringify(COLUMNS.map((c) => c.key)));
      return set;
    }
  } catch (e) {
    /* ignore corrupt storage, fall back to defaults */
  }
  return new Set(COLUMNS.filter((c) => c.default).map((c) => c.key));
}

function saveColumnPrefs() {
  try {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...state.visibleColumns]));
  } catch (e) {
    /* localStorage unavailable; visibility just won't persist */
  }
}

function buildColPicker() {
  const panel = document.getElementById("col-picker-panel");
  panel.innerHTML = COLUMNS.map(
    (c) => `
      <label class="checkbox">
        <input type="checkbox" data-col="${c.key}" ${state.visibleColumns.has(c.key) ? "checked" : ""} ${
      c.key === "status" ? "disabled" : ""
    } />
        ${c.label}
      </label>`
  ).join("");
  panel.querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = input.dataset.col;
      if (input.checked) state.visibleColumns.add(key);
      else state.visibleColumns.delete(key);
      saveColumnPrefs();
      renderTableHead();
      loadDevices();
    });
  });
}

function renderTableHead() {
  const tr = document.getElementById("table-head-row");
  tr.innerHTML = COLUMNS.filter((c) => state.visibleColumns.has(c.key))
    .map((c) => {
      const sorted = state.sort === c.key;
      const dir = sorted ? (state.order === "asc" ? "▲" : "▼") : "";
      return `<th data-key="${c.key}" data-sortable="${c.sortable}" class="sortable${sorted ? " sorted" : ""}" data-dir="${dir}" title="Klikni za sortiranje">${c.label}</th>`;
    })
    .join("");

  tr.querySelectorAll("th").forEach((th) => {
    if (th.dataset.sortable !== "true") return;
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.sort === key) {
        state.order = state.order === "asc" ? "desc" : "asc";
      } else {
        state.sort = key;
        state.order = (COLUMNS.find((c) => c.key === key) || {}).defaultOrder || "asc";
      }
      state.page = 1;
      renderTableHead();
      updateResetButton();
      loadDevices();
    });
  });
}

function rssiColor(rssi) {
  if (rssi >= -60) return "var(--ok)";
  if (rssi >= -75) return "var(--warn)";
  return "var(--bad)";
}

function cellValue(device, key) {
  switch (key) {
    case "status": {
      const meta = STATUS_META[device.status] || { label: device.status, cls: "" };
      const trusted = device.is_trusted ? '<span class="trusted-star" title="Poverljiv uređaj">★</span>' : "";
      return `<span class="status-badge ${meta.cls}">${meta.label}</span>${trusted}`;
    }
    case "mac_address":
      return `<span style="font-family:monospace">${escapeHtml(device.mac_address)}</span>`;
    case "ip_address":
      return escapeHtml(device.ip_address) || "-";
    case "device_type":
      return device.device_type
        ? `<span class="type-cell" title="${device.device_type_auto ? "Automatski prepoznat tip" : "Tip uneo korisnik"}">${deviceTypeIcon(device.device_type)}<span>${escapeHtml(device.device_type)}</span>${device.device_type_auto ? '<span class="auto-tag">auto</span>' : ""}</span>`
        : `<span class="type-cell muted">${deviceTypeIcon(null)}<span>-</span></span>`;
    case "hostname":
      return `<span class="hostname-cell">${escapeHtml(device.hostname) || '<span class="muted">nepoznat</span>'}${device.hostname_locked ? ' <span class="manual-tag" title="Ručno unet hostname">ručno</span>' : ""}</span>`;
    case "vendor":
      return `${vendorLabel(device)}${device.vendor_locked ? ' <span class="manual-tag" title="Ručno unet vendor">ručno</span>' : ""}`;
    case "connection_type":
      return escapeHtml(device.connection_type) || "-";
    case "wifi_rssi":
      return device.wifi_rssi != null
        ? `<span style="color:${rssiColor(device.wifi_rssi)};font-weight:600">${device.wifi_rssi} dBm</span>`
        : "-";
    case "first_seen":
      return fmtDateTime(device.first_seen);
    case "last_seen":
      return fmtDateTime(device.last_seen);
    case "custom_name":
      return escapeHtml(device.custom_name) || '<span style="color:var(--text-faint)">-</span>';
    case "notes":
      return `<span class="notes-cell">${escapeHtml(device.notes) || ""}</span>`;
    default:
      return "";
  }
}

function renderTableBody(items) {
  const tbody = document.getElementById("table-body");
  const visibleKeys = COLUMNS.filter((c) => state.visibleColumns.has(c.key)).map((c) => c.key);

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${visibleKeys.length}" style="text-align:center;color:var(--text-faint);padding:24px">Nema uređaja koji odgovaraju filteru</td></tr>`;
    return;
  }

  tbody.innerHTML = items
    .map(
      (device) => `
      <tr data-id="${device.id}">
        ${visibleKeys.map((key) => `<td class="${key === "notes" ? "notes-cell" : key === "hostname" ? "hostname-cell" : ""}">${cellValue(device, key)}</td>`).join("")}
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => openDeviceModal(Number(row.dataset.id)));
  });
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
  document.getElementById("page-info").textContent = `Strana ${state.page} od ${totalPages} (${state.total} uređaja)`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= totalPages;
}

const DEFAULT_SORT = { sort: "last_seen", order: "desc" };

function filtersActive() {
  return (
    !!state.search ||
    !!state.status ||
    !!state.connectionType ||
    state.trustedOnly ||
    state.sort !== DEFAULT_SORT.sort ||
    state.order !== DEFAULT_SORT.order
  );
}

function updateResetButton() {
  const btn = document.getElementById("reset-filters-btn");
  if (btn) btn.disabled = !filtersActive();
}

function resetFilters() {
  state.search = "";
  state.status = "";
  state.connectionType = "";
  state.trustedOnly = false;
  state.sort = DEFAULT_SORT.sort;
  state.order = DEFAULT_SORT.order;
  state.page = 1;
  document.getElementById("search-input").value = "";
  document.getElementById("status-filter").value = "";
  document.getElementById("connection-filter").value = "";
  document.getElementById("trusted-filter").checked = false;
  renderTableHead();
  updateResetButton();
  loadDevices();
}

async function loadDevices() {
  updateResetButton();
  const params = {
    page: state.page,
    page_size: state.pageSize,
    sort: state.sort,
    order: state.order,
  };
  if (state.search) params.search = state.search;
  if (state.status) params.status = state.status;
  if (state.connectionType) params.connection_type = state.connectionType;
  if (state.trustedOnly) params.is_trusted = true;

  try {
    const data = await Api.listDevices(params);
    state.total = data.total;
    renderTableBody(data.items);
    renderPagination();
  } catch (err) {
    console.error("loadDevices failed", err);
    document.getElementById("table-body").innerHTML =
      '<tr><td colspan="8" style="text-align:center;color:var(--bad);padding:24px">Greška pri učitavanju uređaja</td></tr>';
  }

  loadConnectionSummary();
}

async function loadConnectionSummary() {
  try {
    const stats = await Api.stats();
    document.getElementById("connection-summary").innerHTML =
      `LAN: <strong style="color:var(--text)">${stats.lan_devices}</strong> &middot; ` +
      `Wi-Fi: <strong style="color:var(--text)">${stats.wifi_devices}</strong>`;
  } catch (err) {
    console.error("loadConnectionSummary failed", err);
  }
}

// --- detail modal ---

function buildUptimeBar(device, events) {
  const first = new Date(device.first_seen).getTime();
  const now = Date.now();
  const span = Math.max(now - first, 1);

  const chronological = [...events]
    .filter((e) => ["NEW_DEVICE", "DEVICE_OFFLINE", "DEVICE_RETURNED"].includes(e.event_type))
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  const segments = [];
  let segStart = first;
  let segOnline = true;
  for (const ev of chronological) {
    const t = new Date(ev.timestamp).getTime();
    if (ev.event_type === "DEVICE_OFFLINE" && segOnline) {
      segments.push({ start: segStart, end: t, online: true });
      segStart = t;
      segOnline = false;
    } else if (ev.event_type === "DEVICE_RETURNED" && !segOnline) {
      segments.push({ start: segStart, end: t, online: false });
      segStart = t;
      segOnline = true;
    }
  }
  segments.push({ start: segStart, end: now, online: device.is_online });

  return segments
    .map((s) => {
      const pct = Math.max(((s.end - s.start) / span) * 100, 0.5);
      return `<span class="seg ${s.online ? "ok" : "bad"}" style="width:${pct}%" title="${s.online ? "Online" : "Offline"}: ${fmtDateTime(new Date(s.start).toISOString())} - ${fmtDateTime(new Date(s.end).toISOString())}"></span>`;
    })
    .join("");
}

async function openDeviceModal(id) {
  currentDeviceId = id;
  const overlay = document.getElementById("modal-overlay");
  overlay.classList.add("open");
  document.getElementById("modal-body").innerHTML = '<div class="empty">Učitavanje...</div>';

  try {
    const device = await Api.getDevice(id);
    renderDeviceModal(device);
  } catch (err) {
    console.error("openDeviceModal failed", err);
    document.getElementById("modal-body").innerHTML = '<div class="empty">Greška pri učitavanju uređaja</div>';
  }
}

function renderDeviceModal(device) {
  const meta = STATUS_META[device.status] || { label: device.status, cls: "" };

  const extraInfo = [
    ["IPv6", device.ipv6_address],
    ["DHCP hostname", device.dhcp_hostname],
    ["mDNS hostname", device.mdns_hostname],
    ["NetBIOS hostname", device.netbios_hostname],
    ["Wi-Fi SSID", device.wifi_ssid],
    ["Gateway", device.gateway],
    ["VLAN", device.vlan],
    ["Switch port", device.switch_port],
    ["OS fingerprint", device.os_fingerprint],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");

  document.getElementById("modal-body").innerHTML = `
    <div class="modal-header">
      <div>
        <div class="mac">${escapeHtml(device.mac_address)}</div>
        <span class="status-badge ${meta.cls}">${meta.label}</span>
        ${device.is_trusted ? '<span class="trusted-star" title="Poverljiv uređaj">★ Poverljiv</span>' : ""}
      </div>
      <button class="modal-close" id="modal-close-btn">&times;</button>
    </div>

    <div class="modal-section">
      <h3>Osnovne informacije</h3>
      <div class="info-grid">
        <div class="row"><span>IP adresa</span><span>${escapeHtml(device.ip_address) || "-"}</span></div>
        <div class="row"><span>Hostname</span><span>${escapeHtml(device.hostname) || "nepoznat"}${device.hostname_locked ? ' <span class="manual-tag">ručno</span>' : ""}</span></div>
        <div class="row"><span>Vendor</span><span>${vendorLabel(device)}${device.vendor_locked ? ' <span class="manual-tag">ručno</span>' : ""}</span></div>
        <div class="row"><span>Tip</span><span class="type-cell">${deviceTypeIcon(device.device_type)}<span>${escapeHtml(device.device_type) || "nepoznat"}</span>${device.device_type_auto ? '<span class="auto-tag">auto</span>' : ""}</span></div>
        <div class="row"><span>Veza</span><span>${escapeHtml(device.connection_type) || "-"} (${escapeHtml(device.interface) || "-"})</span></div>
        <div class="row"><span>Prvi put viđen</span><span>${fmtDateTime(device.first_seen)}</span></div>
        <div class="row"><span>Poslednji put viđen</span><span>${fmtDateTime(device.last_seen)}</span></div>
        <div class="row"><span>Broj pojavljivanja</span><span>${device.seen_count}</span></div>
        ${
          device.wifi_rssi != null
            ? `<div class="row"><span>Wi-Fi signal</span><span style="color:${rssiColor(device.wifi_rssi)};font-weight:600">${device.wifi_rssi} dBm</span></div>`
            : ""
        }
        ${extraInfo.map(([label, value]) => `<div class="row"><span>${label}</span><span>${escapeHtml(value)}</span></div>`).join("")}
      </div>
    </div>

    <div class="modal-section">
      <h3>Uptime</h3>
      <div class="uptime-bar">${buildUptimeBar(device, device.events)}</div>
      <div class="uptime-caption"><span>${fmtDateTime(device.first_seen)}</span><span>sada</span></div>
    </div>

    <div class="modal-section">
      <h3>Korisnička podešavanja</h3>
      <div class="edit-form">
        <div>
          <label>Naziv</label>
          <input type="text" id="edit-custom-name" value="${escapeHtml(device.custom_name) || ""}" placeholder="npr. Telefon - dnevna soba" />
        </div>
        <div>
          <label>Tip uređaja ${device.device_type_auto ? '<span class="auto-tag" title="Prepoznat automatski; upiši svoj tip da ga zameniš">auto</span>' : ""}</label>
          <input type="text" id="edit-device-type" list="device-type-list" value="${escapeHtml(device.device_type) || ""}" placeholder="npr. Telefon" />
          <datalist id="device-type-list">${DEVICE_TYPES.map((t) => `<option value="${escapeHtml(t)}"></option>`).join("")}</datalist>
        </div>
        <div>
          <label>Hostname ${device.hostname_locked ? '<span class="manual-tag">ručno</span>' : '<span class="auto-tag">auto</span>'}</label>
          <input type="text" id="edit-hostname" value="${escapeHtml(device.hostname) || ""}" placeholder="${escapeHtml(device.dhcp_hostname) || "npr. moj-telefon"}" />
        </div>
        <div>
          <label>Vendor ${device.vendor_locked ? '<span class="manual-tag">ručno</span>' : '<span class="auto-tag">auto</span>'}</label>
          <input type="text" id="edit-vendor" value="${escapeHtml(device.vendor) || ""}" placeholder="npr. Samsung" />
        </div>
        <div class="full field-hint">
          Hostname i vendor se popunjavaju automatski (DNS, Omada, MAC baza proizvođača). Ako upišeš svoju vrednost, ona se zaključava i scanner je više ne menja; obriši polje da se vrati automatsko prepoznavanje.
        </div>
        <div class="full">
          <label>Beleška</label>
          <input type="text" id="edit-notes" value="${escapeHtml(device.notes) || ""}" placeholder="npr. Privatni Android telefon" />
        </div>
        <div class="full">
          <label class="checkbox"><input type="checkbox" id="edit-trusted" ${device.is_trusted ? "checked" : ""} /> Poverljiv uređaj (ne šalji obaveštenja)</label>
        </div>
      </div>
    </div>

    <div class="modal-section">
      <h3>Istorija IP adresa (${device.ip_history.length})</h3>
      ${
        device.ip_history.length
          ? `<div class="info-grid">${device.ip_history
              .map(
                (h) =>
                  `<div class="row"><span>${escapeHtml(h.ip_address)}</span><span>${fmtDateTime(h.first_seen)} &rarr; ${fmtDateTime(h.last_seen)}</span></div>`
              )
              .join("")}</div>`
          : '<div class="empty">Nema istorije</div>'
      }
    </div>

    <div class="modal-section">
      <h3>Događaji (${device.events.length})</h3>
      <div class="events-feed">
        ${
          device.events.length
            ? device.events
                .map((e) => {
                  const em = EVENT_META[e.event_type] || { label: e.event_type, cls: "info" };
                  return `<div class="event-row">
                    <span class="event-badge ${em.cls}">${em.label}</span>
                    <div class="event-body">
                      <div>${e.ip_address ? escapeHtml(e.ip_address) : ""}</div>
                      <div class="event-detail">${formatEventDetails(e)}</div>
                      <div class="event-meta">${fmtDateTime(e.timestamp)}</div>
                    </div>
                  </div>`;
                })
                .join("")
            : '<div class="empty">Nema događaja</div>'
        }
      </div>
    </div>

    <div class="modal-actions">
      <div id="delete-zone">
        <button class="btn btn-danger" id="delete-btn">Obriši uređaj</button>
      </div>
      <button class="btn btn-primary" id="save-btn">Sačuvaj izmene</button>
    </div>
  `;

  document.getElementById("modal-close-btn").addEventListener("click", closeModal);
  document.getElementById("save-btn").addEventListener("click", () => saveDevice(device.id));
  document.getElementById("delete-btn").addEventListener("click", () => confirmDelete(device.id));
}

async function saveDevice(id) {
  const payload = {
    custom_name: document.getElementById("edit-custom-name").value.trim() || null,
    device_type: document.getElementById("edit-device-type").value.trim() || null,
    hostname: document.getElementById("edit-hostname").value.trim() || null,
    vendor: document.getElementById("edit-vendor").value.trim() || null,
    notes: document.getElementById("edit-notes").value.trim() || null,
    is_trusted: document.getElementById("edit-trusted").checked,
  };
  const saveBtn = document.getElementById("save-btn");
  saveBtn.disabled = true;
  saveBtn.textContent = "Čuvanje...";
  try {
    await Api.updateDevice(id, payload);
    closeModal();
    loadDevices();
  } catch (err) {
    console.error("saveDevice failed", err);
    saveBtn.disabled = false;
    saveBtn.textContent = "Sačuvaj izmene";
    alert("Greška pri čuvanju izmena.");
  }
}

function confirmDelete(id) {
  const zone = document.getElementById("delete-zone");
  zone.innerHTML = `
    <span style="font-size:12px;color:var(--text-dim);margin-right:8px">Da li si siguran?</span>
    <button class="btn btn-danger confirm" id="delete-confirm-btn">Da, obriši</button>
    <button class="btn btn-ghost" id="delete-cancel-btn">Otkaži</button>
  `;
  document.getElementById("delete-confirm-btn").addEventListener("click", async () => {
    try {
      await Api.deleteDevice(id);
      closeModal();
      loadDevices();
    } catch (err) {
      console.error("deleteDevice failed", err);
      alert("Greška pri brisanju uređaja.");
    }
  });
  document.getElementById("delete-cancel-btn").addEventListener("click", () => confirmDelete.reset(id));
}
confirmDelete.reset = (id) => {
  document.getElementById("delete-zone").innerHTML = `<button class="btn btn-danger" id="delete-btn">Obriši uređaj</button>`;
  document.getElementById("delete-btn").addEventListener("click", () => confirmDelete(id));
};

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("open");
  currentDeviceId = null;
}

// --- toolbar wiring ---

function initToolbar() {
  document.getElementById("search-input").addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.search = e.target.value.trim();
      state.page = 1;
      loadDevices();
    }, 300);
  });

  document.getElementById("status-filter").addEventListener("change", (e) => {
    state.status = e.target.value;
    state.page = 1;
    loadDevices();
  });

  document.getElementById("connection-filter").addEventListener("change", (e) => {
    state.connectionType = e.target.value;
    state.page = 1;
    loadDevices();
  });

  document.getElementById("trusted-filter").addEventListener("change", (e) => {
    state.trustedOnly = e.target.checked;
    state.page = 1;
    loadDevices();
  });

  document.getElementById("reset-filters-btn").addEventListener("click", resetFilters);

  const pageSizeSelect = document.getElementById("page-size");
  pageSizeSelect.value = state.pageSize;
  pageSizeSelect.addEventListener("change", (e) => {
    state.pageSize = Number(e.target.value);
    state.page = 1;
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(state.pageSize));
    } catch (err) {
      /* localStorage unavailable; selection just won't persist */
    }
    loadDevices();
  });

  document.getElementById("col-picker-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("col-picker-panel").classList.toggle("open");
  });

  document.getElementById("pdf-period").addEventListener("change", (e) => {
    const days = e.target.value;
    document.getElementById("export-pdf-btn").href = days ? `/api/export/pdf?days=${days}` : "/api/export/pdf";
  });
  document.addEventListener("click", () => document.getElementById("col-picker-panel").classList.remove("open"));

  document.getElementById("prev-page").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadDevices();
    }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    state.page += 1;
    loadDevices();
  });

  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "modal-overlay") closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

buildColPicker();
renderTableHead();
initToolbar();
loadDevices();
setInterval(() => {
  if (!document.getElementById("modal-overlay").classList.contains("open")) loadDevices();
}, 15000);

const deepLinkId = new URLSearchParams(window.location.search).get("device");
if (deepLinkId) openDeviceModal(Number(deepLinkId));

function flashRowsByMac(macs) {
  if (!macs || !macs.length) return;
  document.querySelectorAll("#table-body tr[data-id]").forEach((row) => {
    if (macs.some((mac) => row.textContent.includes(mac))) {
      row.classList.add("row-flash");
      setTimeout(() => row.classList.remove("row-flash"), 2200);
    }
  });
}

window.addEventListener("nw:refresh", async (e) => {
  if (document.getElementById("modal-overlay").classList.contains("open")) return;
  await loadDevices();
  const macs = (e.detail.new_devices || []).map((d) => d.mac);
  flashRowsByMac(macs);
});
