const REFRESH_MS = 15000;

// Per-viewer chart preferences (display mode, color / palette), persisted in
// localStorage via Prefs -- not canonical data, never required.
const CHART_CARDS = {
  timeline: {
    kind: "series",
    containerId: "chart-online-timeline",
    defaultMode: "area",
    defaultColor: "#22d3ee",
    xType: "time",
    valueKey: "online",
    label: "online",
    unit: "uređaja",
  },
  daily: {
    kind: "series",
    containerId: "chart-new-devices",
    defaultMode: "bar",
    defaultColor: "#818cf8",
    xType: "category",
    valueKey: "count",
    labelKey: "date",
    label: "novih",
    unit: "novih",
    height: 113,
    fixedPixelHeight: true,
  },
  split: { kind: "palette", containerId: "chart-connection-split", render: "donut" },
  types: { kind: "palette", containerId: "chart-device-types", render: "donut" },
  vendors: { kind: "palette", containerId: "chart-top-vendors", render: "hbar" },
};
const MODES = [
  ["area", "Površina"],
  ["line", "Linija"],
  ["bar", "Barovi"],
];
const TIMELINE_RANGES = [
  [1, "1h"],
  [6, "6h"],
  [12, "12h"],
  [24, "24h"],
  [168, "7d"],
  [240, "10d"],
  [720, "30d"],
  [1440, "60d"],
];
const chartData = {};

const prefKey = (key, what) => `nw_chart_${what}_${key}`;
const getMode = (key) => {
  const m = Prefs.get(prefKey(key, "mode"), null);
  return MODES.some(([v]) => v === m) ? m : CHART_CARDS[key].defaultMode;
};
const getColor = (key) => {
  const c = Prefs.get(prefKey(key, "color"), null);
  return /^#[0-9a-f]{6}$/i.test(c || "") ? c : CHART_CARDS[key].defaultColor;
};
const getPalette = (key) => {
  const p = Prefs.get(prefKey(key, "palette"), "default");
  return Charts.palettes[p] ? p : "default";
};
const getTimelineRange = () => {
  const h = Number(Prefs.get("nw_timeline_range", 24));
  return TIMELINE_RANGES.some(([v]) => v === h) ? h : 24;
};

// Older builds stored the mode as a bare string under these keys.
(function migrateOldModePrefs() {
  [["timeline", "nw_chart_mode_timeline"], ["daily", "nw_chart_mode_daily"]].forEach(([key, old]) => {
    try {
      const v = localStorage.getItem(old);
      if (v && !v.startsWith('"')) localStorage.setItem(prefKey(key, "mode"), JSON.stringify(v));
    } catch (e) {
      /* ignore */
    }
  });
})();

function renderChartCard(key) {
  const card = CHART_CARDS[key];
  const el = document.getElementById(card.containerId);
  const data = chartData[key];
  if (!el || !data) return;

  if (card.kind === "series") {
    Charts.seriesChart(el, data.points, {
      mode: getMode(key),
      xType: card.xType,
      color: getColor(key),
      valueKey: card.valueKey,
      labelKey: card.labelKey,
      label: card.label,
      unit: card.unit,
      height: card.height || 200,
      fixedPixelHeight: !!card.fixedPixelHeight,
      xDomain: data.start ? [data.start, data.end] : null,
    });
  } else {
    const colors = Charts.palettes[getPalette(key)].colors;
    if (card.render === "donut") Charts.donut(el, data.items, { colors });
    else Charts.hbarList(el, data.items, { colors });
  }
  syncMenuState(key);
}

// ---------- ⋮ chart menus (built from CHART_CARDS) ----------

function buildChartMenu(menu) {
  const key = menu.dataset.chart;
  const card = CHART_CARDS[key];
  let body = "";
  if (card.kind === "series") {
    body += '<div class="chart-menu-section">Prikaz</div>';
    body += MODES.map(([m, l]) => `<button type="button" class="chart-menu-item" data-mode="${m}">${l}</button>`).join("");
    body += '<div class="chart-menu-section">Boja</div><div class="swatch-grid">';
    body += Charts.swatches
      .map((c) => `<button type="button" class="swatch-btn" data-color="${c}" style="background:${c}" aria-label="Boja ${c}"></button>`)
      .join("");
    body += `<label class="swatch-custom" title="Izaberi bilo koju boju"><input type="color" class="color-custom" /><span>Druga…</span></label></div>`;
  } else {
    body += '<div class="chart-menu-section">Paleta boja</div>';
    body += Object.entries(Charts.palettes)
      .map(
        ([id, p]) => `
        <button type="button" class="chart-menu-item palette-item" data-palette="${id}">
          <span class="palette-preview">${p.colors.slice(0, 6).map((c) => `<i style="background:${c}"></i>`).join("")}</span>
          ${p.label}
        </button>`
      )
      .join("");
  }
  menu.innerHTML = `
    <button type="button" class="chart-menu-btn" aria-label="Izgled grafikona" title="Izgled grafikona">&#8942;</button>
    <div class="chart-menu-dropdown">${body}</div>`;

  const btn = menu.querySelector(".chart-menu-btn");
  const dropdown = menu.querySelector(".chart-menu-dropdown");
  btn.addEventListener("click", (evt) => {
    evt.stopPropagation();
    const wasOpen = dropdown.classList.contains("open");
    closeAllChartMenus();
    dropdown.classList.toggle("open", !wasOpen);
  });
  dropdown.addEventListener("click", (evt) => evt.stopPropagation());
  dropdown.querySelectorAll("[data-mode]").forEach((item) =>
    item.addEventListener("click", () => {
      Prefs.set(prefKey(key, "mode"), item.dataset.mode);
      renderChartCard(key);
    })
  );
  dropdown.querySelectorAll("[data-color]").forEach((item) =>
    item.addEventListener("click", () => {
      Prefs.set(prefKey(key, "color"), item.dataset.color);
      renderChartCard(key);
    })
  );
  const custom = dropdown.querySelector(".color-custom");
  if (custom) {
    custom.addEventListener("input", () => {
      Prefs.set(prefKey(key, "color"), custom.value);
      renderChartCard(key);
    });
  }
  dropdown.querySelectorAll("[data-palette]").forEach((item) =>
    item.addEventListener("click", () => {
      Prefs.set(prefKey(key, "palette"), item.dataset.palette);
      renderChartCard(key);
    })
  );
}

function syncMenuState(key) {
  const menu = document.querySelector(`.chart-menu[data-chart="${key}"]`);
  if (!menu) return;
  const card = CHART_CARDS[key];
  if (card.kind === "series") {
    const mode = getMode(key);
    const color = getColor(key).toLowerCase();
    menu.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    menu.querySelectorAll("[data-color]").forEach((b) => b.classList.toggle("active", b.dataset.color.toLowerCase() === color));
    const custom = menu.querySelector(".color-custom");
    if (custom) custom.value = color;
  } else {
    const pal = getPalette(key);
    menu.querySelectorAll("[data-palette]").forEach((b) => b.classList.toggle("active", b.dataset.palette === pal));
  }
}

function closeAllChartMenus() {
  document.querySelectorAll(".chart-menu-dropdown.open").forEach((d) => d.classList.remove("open"));
}

function initChartMenus() {
  document.querySelectorAll(".chart-menu[data-chart]").forEach(buildChartMenu);
  document.addEventListener("click", closeAllChartMenus);
}

function initTimelineRange() {
  const wrap = document.getElementById("timeline-range");
  wrap.innerHTML = TIMELINE_RANGES.map(
    ([h, l]) => `<button type="button" class="range-chip" data-hours="${h}">${l}</button>`
  ).join("");
  const sync = () =>
    wrap.querySelectorAll(".range-chip").forEach((b) => b.classList.toggle("active", Number(b.dataset.hours) === getTimelineRange()));
  wrap.addEventListener("click", (e) => {
    const b = e.target.closest(".range-chip");
    if (!b) return;
    Prefs.set("nw_timeline_range", Number(b.dataset.hours));
    sync();
    loadTimeline();
  });
  sync();
}

// ---------- stats / status strip ----------

function setStat(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderStatusBar(stats) {
  const items = [
    { label: "Scanner", status: stats.scanner_status },
    { label: "Baza podataka", status: stats.database_status },
    { label: "MQTT", status: stats.mqtt_status },
    { label: "SMTP", status: stats.smtp_status },
    { label: "Webhook", status: stats.webhook_status },
    { label: "Omada", status: stats.omada_status },
    { label: "ARP sniffer", status: stats.sniffer_status },
  ];

  const ledClass = (status) => {
    if (status === "ONLINE" || status === "CONFIGURED") return "on";
    if (status === "DISABLED" || status === "UNKNOWN") return "disabled";
    return "off";
  };
  const valueText = (status) => {
    if (status === "ONLINE") return "Online";
    if (status === "OFFLINE") return "Offline";
    if (status === "CONFIGURED") return "Podešeno";
    if (status === "DISABLED") return "Nije podešeno";
    return "Nepoznato";
  };

  const bar = document.getElementById("status-bar");
  bar.innerHTML = items
    .map(
      (i) => `
      <div class="status-chip">
        <span class="led ${ledClass(i.status)}"></span>
        <span class="label">${i.label}</span>
        <span class="value">${valueText(i.status)}</span>
      </div>`
    )
    .join("");

  bar.innerHTML += `
    <div class="status-chip">
      <span class="led ${stats.scanner_status === "ONLINE" ? "on" : "off"}"></span>
      <span class="label">Poslednji scan</span>
      <span class="value">${timeAgo(stats.last_scan_at)}</span>
    </div>`;
}

function renderLastDevice(device) {
  const el = document.getElementById("last-device");
  if (!device) {
    el.innerHTML = '<div class="empty">Još nema detektovanih uređaja</div>';
    return;
  }
  el.innerHTML = `
    <div class="mac">${escapeHtml(device.mac_address)}</div>
    <div class="row"><span>IP</span><span>${escapeHtml(device.ip_address) || "-"}</span></div>
    <div class="row"><span>Hostname</span><span>${escapeHtml(device.hostname) || "nepoznat"}</span></div>
    <div class="row"><span>Vendor</span><span>${escapeHtml(device.vendor) || "nepoznat"}</span></div>
    <div class="row"><span>Veza</span><span>${escapeHtml(device.connection_type) || "-"}</span></div>
    <div class="row"><span>Prvi put viđen</span><span>${fmtDateTime(device.first_seen)}</span></div>
  `;
}

// ---------- events feed ----------

const CONNECTION_LABEL = { LAN: "LAN", WIFI: "Wi-Fi" };

function renderEventsFeed(data, hours) {
  const el = document.getElementById("events-feed");
  const summary = document.getElementById("feed-summary");
  const label = (document.querySelector(`#feed-range option[value="${hours}"]`) || {}).textContent || `${hours}h`;
  summary.textContent = data.total
    ? `${data.total} događaja u poslednjih ${label}${data.total > data.items.length ? ` · prikazano ${data.items.length} najnovijih` : ""}`
    : "";
  if (!data.items.length) {
    el.innerHTML = `<div class="empty">Nema događaja u poslednjih ${escapeHtml(label)}</div>`;
    return;
  }
  el.innerHTML = data.items
    .map((e) => {
      const meta = EVENT_META[e.event_type] || { label: e.event_type, cls: "info" };
      const name = e.device_name || e.device_vendor || "Nepoznat uređaj";
      const facts = [
        e.device_mac ? `<span class="mono">${escapeHtml(e.device_mac)}</span>` : "",
        e.ip_address ? escapeHtml(e.ip_address) : "",
        e.device_connection_type ? CONNECTION_LABEL[e.device_connection_type] || escapeHtml(e.device_connection_type) : "",
        e.device_name && e.device_vendor ? escapeHtml(e.device_vendor) : "",
      ].filter(Boolean);
      const details = formatEventDetails(e);
      return `
        <a class="event-row event-row-link" href="/devices.html?device=${e.device_id}" title="Otvori detalje uređaja">
          <span class="event-badge ${meta.cls}">${meta.label}</span>
          <div class="event-body">
            <div class="event-title">
              <span class="event-name">${escapeHtml(name)}</span>${e.device_is_trusted ? ' <span class="trusted-dot" title="Poverljiv uređaj">&#10003;</span>' : ""}
              <span class="event-when" title="${fmtDateTime(e.timestamp)}">${timeAgo(e.timestamp)}</span>
            </div>
            <div class="event-meta">${facts.join(" &middot; ")}</div>
            ${details ? `<div class="event-detail">${details}</div>` : ""}
            <div class="event-meta">${fmtDateTime(e.timestamp)}</div>
          </div>
        </a>`;
    })
    .join("");
}

async function loadEventsFeed() {
  const hours = Number(document.getElementById("feed-range").value) || 24;
  try {
    const start = new Date(Date.now() - hours * 3600e3).toISOString();
    const data = await Api.listEvents({ start, page_size: 50, sort: "timestamp", order: "desc" });
    renderEventsFeed(data, hours);
  } catch (err) {
    console.error("loadEventsFeed failed", err);
  }
}

function initFeedRange() {
  const sel = document.getElementById("feed-range");
  const saved = String(Prefs.get("nw_feed_range", 24));
  if ([...sel.options].some((o) => o.value === saved)) sel.value = saved;
  else sel.value = "24";
  sel.addEventListener("change", () => {
    Prefs.set("nw_feed_range", Number(sel.value));
    loadEventsFeed();
  });
}

// ---------- refresh ----------

async function refreshDashboard() {
  try {
    const stats = await Api.stats();

    setStat("stat-total", stats.total_devices);
    setStat("stat-online", stats.online);
    setStat("stat-offline", stats.offline);
    setStat("stat-new", stats.new_devices);
    setStat("stat-wifi", stats.wifi_devices);
    setStat("stat-lan", stats.lan_devices);
    setStat("stat-ip-conflicts", stats.active_ip_conflicts);
    setStat("stat-scans", stats.active_scans_detected);

    renderStatusBar(stats);
    renderLastDevice(stats.last_device);

    document.getElementById("last-refresh").textContent = `Osveženo: ${new Intl.DateTimeFormat("sr-RS", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date())}`;
  } catch (err) {
    console.error("refreshDashboard failed", err);
    document.getElementById("last-refresh").textContent = "Greška pri osvežavanju";
  }
}

async function loadTimeline() {
  try {
    chartData.timeline = await Api.onlineTimeline(getTimelineRange());
    renderChartCard("timeline");
  } catch (err) {
    console.error("loadTimeline failed", err);
  }
}

async function refreshCharts() {
  try {
    const [daily, split, types, vendors] = await Promise.all([
      Api.newDevicesDaily(30),
      Api.connectionSplit(),
      Api.deviceTypes(),
      Api.topVendors(8),
    ]);
    chartData.daily = daily;
    chartData.split = split;
    chartData.types = types;
    chartData.vendors = vendors;
    ["daily", "split", "types", "vendors"].forEach(renderChartCard);
  } catch (err) {
    console.error("refreshCharts failed", err);
  }
  loadTimeline();
}

function tick() {
  refreshDashboard();
  refreshCharts();
  loadEventsFeed();
}

initChartMenus();
initTimelineRange();
initFeedRange();
tick();
setInterval(tick, REFRESH_MS);
window.addEventListener("nw:refresh", tick);

// Re-fit fixed-height charts after a resize (viewBox height depends on width).
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => Object.keys(CHART_CARDS).forEach(renderChartCard), 200);
});
