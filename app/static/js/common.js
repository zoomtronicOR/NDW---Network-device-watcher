const EVENT_META = {
  NEW_DEVICE: { label: "NOV UREĐAJ", cls: "new" },
  DEVICE_ONLINE: { label: "ONLINE", cls: "ok" },
  DEVICE_OFFLINE: { label: "OFFLINE", cls: "bad" },
  DEVICE_RETURNED: { label: "VRAĆEN", cls: "ok" },
  IP_CHANGED: { label: "IP PROMENJEN", cls: "warn" },
  HOSTNAME_CHANGED: { label: "HOSTNAME", cls: "info" },
  MANUAL_UPDATE: { label: "IZMENA", cls: "info" },
  ANOMALY_BURST_NEW_DEVICES: { label: "NALET UREĐAJA", cls: "bad" },
  VENDOR_MISMATCH: { label: "VENDOR MISMATCH", cls: "warn" },
  IP_CONFLICT: { label: "IP KONFLIKT", cls: "bad" },
  SCAN_DETECTED: { label: "SKENIRANJE MREŽE", cls: "bad" },
};

const STATUS_META = {
  NEW: { label: "NOV", cls: "new" },
  ONLINE: { label: "ONLINE", cls: "ok" },
  OFFLINE: { label: "OFFLINE", cls: "bad" },
};

function timeAgo(isoString) {
  if (!isoString) return "nikad";
  const diffMs = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 5) return "sada";
  if (s < 60) return `pre ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `pre ${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `pre ${h}h`;
  return `pre ${Math.floor(h / 24)}d`;
}

function fmtDateTime(isoString) {
  if (!isoString) return "-";
  return new Intl.DateTimeFormat("sr-RS", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(isoString));
}

function fmtBytes(bytes, decimals = 1) {
  if (bytes === null || bytes === undefined) return "-";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : decimals)} ${units[i]}`;
}

function fmtDuration(totalSeconds) {
  if (!totalSeconds || totalSeconds < 0) return "-";
  const s = Math.floor(totalSeconds);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const parts = [];
  if (days) parts.push(`${days}d`);
  if (days || hours) parts.push(`${hours}h`);
  parts.push(`${mins}min`);
  return parts.join(" ");
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// --- toast notifications (§9) ---

function ensureToastContainer() {
  let el = document.getElementById("toast-container");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-container";
    document.body.appendChild(el);
  }
  return el;
}

function showToast({ title, lines = [], tone = "info", timeout = 8000 }) {
  const container = ensureToastContainer();
  const toast = document.createElement("div");
  toast.className = `toast toast-${tone}`;
  toast.innerHTML = `
    <button class="toast-close" aria-label="Zatvori">&times;</button>
    <div class="toast-title">${escapeHtml(title)}</div>
    <div class="toast-body">${lines.map((l) => `<div>${escapeHtml(l)}</div>`).join("")}</div>
  `;
  toast.querySelector(".toast-close").addEventListener("click", () => toast.remove());
  container.appendChild(toast);
  if (timeout) setTimeout(() => toast.remove(), timeout);
  return toast;
}

// --- optional sound signal (§9) ---

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start();
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) {
    /* Web Audio unavailable, or blocked until the user interacts with the page -- skip silently */
  }
}

// --- event details (shared by Istorija table and Dashboard feed) ---

function parseEventDetails(event) {
  if (!event || !event.details) return null;
  try {
    return JSON.parse(event.details);
  } catch (e) {
    return { _raw: event.details };
  }
}

const MANUAL_FIELD_LABELS = { custom_name: "naziv", device_type: "tip", notes: "beleška", is_trusted: "poverljiv" };

function formatEventDetails(event) {
  switch (event.event_type) {
    case "NEW_DEVICE":
      return "Prvi put viđen na mreži";
    case "DEVICE_OFFLINE":
      return "Više se ne odaziva na mreži";
    case "DEVICE_RETURNED":
      return "Ponovo prisutan na mreži";
  }
  const d = parseEventDetails(event);
  if (!d) return "";
  if (d._raw) return escapeHtml(d._raw);
  switch (event.event_type) {
    case "IP_CHANGED":
      return `IP: ${escapeHtml(d.old_ip) || "-"} &rarr; ${escapeHtml(d.new_ip) || "-"}`;
    case "HOSTNAME_CHANGED":
      return `Hostname: ${escapeHtml(d.old_hostname) || "-"} &rarr; ${escapeHtml(d.new_hostname) || "-"}`;
    case "VENDOR_MISMATCH":
      return `Vendor: ${escapeHtml(d.old_vendor) || "-"} &rarr; ${escapeHtml(d.new_vendor) || "-"}`;
    case "IP_CONFLICT":
      return `IP ${escapeHtml(d.ip)} istovremeno koristi i: ${(d.conflicting_macs || []).map(escapeHtml).join(", ")}`;
    case "ANOMALY_BURST_NEW_DEVICES":
      return `${d.count} novih uređaja u ${d.window_minutes} min`;
    case "SCAN_DETECTED":
      return d.known_scanner
        ? `Poznati skener se ponaša neuobičajeno: ${escapeHtml(d.reason)}`
        : `ARP skeniranje: ${d.target_count} različitih adresa za ${d.window_seconds}s`;
    case "MANUAL_UPDATE":
      return Object.entries(d)
        .map(([k, v]) => {
          const val = typeof v === "boolean" ? (v ? "da" : "ne") : v;
          return `${escapeHtml(MANUAL_FIELD_LABELS[k] || k)}: ${escapeHtml(val) || "-"}`;
        })
        .join(", ");
    default:
      return escapeHtml(JSON.stringify(d));
  }
}

// --- device types + icons (§24) ---
// Labels match the vocabulary already used in the DB (and the auto classifier).

const DEVICE_TYPES = [
  "Telefon", "Tablet", "Laptop", "Computer", "TV", "TV Box", "IPTV", "Camera", "IOT", "Smart Watch",
  "Router", "Access point", "Switch", "Server", "NAS", "Štampač", "Konzola", "VPN", "Aplikacija",
];

const _ICON_PATHS = {
  phone: '<rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>',
  tablet: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>',
  laptop: '<rect x="4" y="4" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  tv: '<rect x="2" y="7" width="20" height="15" rx="2"/><polyline points="17 2 12 7 7 2"/>',
  cast: '<path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/><line x1="2" y1="20" x2="2.01" y2="20"/>',
  camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  watch: '<circle cx="12" cy="12" r="7"/><polyline points="12 9 12 12 13.5 13.5"/><path d="M16.5 17.4l-.4 3.8a2 2 0 0 1-2 1.8H9.8a2 2 0 0 1-2-1.8l-.3-3.8m0-10.8l.3-3.8A2 2 0 0 1 9.8 1h4.4a2 2 0 0 1 2 1.8l.3 3.8"/>',
  router: '<rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 17h.01M10 17h.01"/><path d="M16 13l2-7M8 13L6 6"/>',
  wifi: '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
  switch: '<rect x="2" y="8" width="20" height="8" rx="2"/><path d="M6 12h.01M10 12h.01M14 12h.01M18 12h.01"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>',
  drive: '<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>',
  printer: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  gamepad: '<line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><line x1="15" y1="13" x2="15.01" y2="13"/><line x1="18" y1="11" x2="18.01" y2="11"/><rect x="2" y="6" width="20" height="12" rx="2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  package: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
  unknown: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
};

const _TYPE_ICON = [
  [/^(telefon|phone|mobil)/, "phone"],
  [/^tablet/, "tablet"],
  [/^laptop/, "laptop"],
  [/^(computer|pc|računar|racunar|desktop)/, "monitor"],
  [/^tv box|^stb/, "cast"],
  [/^(tv|iptv|televizor)/, "tv"],
  [/^(camera|kamera)/, "camera"],
  [/^(iot|smart|sensor|senzor|utičnica|sijalica)/, "zap"],
  [/watch|sat$/, "watch"],
  [/^router|^gateway/, "router"],
  [/^access point|^ap$/, "wifi"],
  [/^switch/, "switch"],
  [/^server|^vm|^lxc/, "server"],
  [/^nas/, "drive"],
  [/^(štampač|stampac|printer)/, "printer"],
  [/^(konzola|console)/, "gamepad"],
  [/^vpn/, "shield"],
  [/^(aplikacija|app)/, "package"],
];

function deviceTypeIcon(type, size = 15) {
  const t = (type || "").trim().toLowerCase();
  const key = (_TYPE_ICON.find(([re]) => re.test(t)) || [null, "unknown"])[1];
  return `<svg class="type-icon" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${_ICON_PATHS[key]}</svg>`;
}

// Randomized ("private") MACs used by phones/VMs have no OUI vendor at all.
function isPrivateMac(mac) {
  const first = parseInt(String(mac || "").replace(/[^0-9a-f]/gi, "").slice(0, 2), 16);
  return !Number.isNaN(first) && (first & 0x02) === 0x02;
}

function vendorLabel(device) {
  if (device.vendor) return escapeHtml(device.vendor);
  return isPrivateMac(device.mac_address)
    ? '<span class="muted" title="Nasumična (privatna) MAC adresa — telefoni i virtuelne mašine je koriste, pa proizvođač ne može da se odredi iz MAC-a">privatna MAC</span>'
    : '<span class="muted">nepoznat</span>';
}

// --- per-viewer preferences (localStorage, never required) ---

const Prefs = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* storage disabled -- preference just won't persist */
    }
  },
};

// --- sortable table headers ---
// Any <th data-sort="key"> becomes clickable; state.sort / state.order are
// updated and onChange() is called (server reload or client re-render).

function updateSortIndicators(headRow, state) {
  headRow.querySelectorAll("th[data-sort]").forEach((th) => {
    const active = th.dataset.sort === state.sort;
    th.classList.toggle("sorted", active);
    th.dataset.dir = active ? (state.order === "asc" ? "▲" : "▼") : "";
  });
}

function bindSortableHeaders(headRow, state, onChange) {
  headRow.querySelectorAll("th[data-sort]").forEach((th) => {
    th.classList.add("sortable");
    th.title = "Klikni za sortiranje";
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sort === key) {
        state.order = state.order === "asc" ? "desc" : "asc";
      } else {
        state.sort = key;
        state.order = th.dataset.defaultOrder || "asc";
      }
      updateSortIndicators(headRow, state);
      onChange();
    });
  });
  updateSortIndicators(headRow, state);
}

// Client-side sort for tables that already hold all rows (e.g. Time Machine).
// Empty values always last; numbers and IPv4 addresses compared numerically.
function sortRows(rows, key, order, getter = (r, k) => r[k]) {
  const ipNum = (v) =>
    /^\d+\.\d+\.\d+\.\d+$/.test(v) ? v.split(".").reduce((acc, o) => acc * 256 + Number(o), 0) : null;
  const dir = order === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    let va = getter(a, key);
    let vb = getter(b, key);
    const ea = va === null || va === undefined || va === "";
    const eb = vb === null || vb === undefined || vb === "";
    if (ea || eb) return ea === eb ? 0 : ea ? 1 : -1;
    if (typeof va === "boolean") va = Number(va);
    if (typeof vb === "boolean") vb = Number(vb);
    const ia = typeof va === "string" ? ipNum(va) : null;
    const ib = typeof vb === "string" ? ipNum(vb) : null;
    if (ia !== null && ib !== null) return (ia - ib) * dir;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "sr", { numeric: true, sensitivity: "base" }) * dir;
  });
}

// --- Serbian date/time picker ---
// Browsers render <input type="datetime-local"> in the *browser's* locale
// (e.g. MM/DD/YYYY AM/PM), which a page cannot change. Every such input is
// replaced by this picker: dd.mm.gggg. HH:mm display, Serbian month/day
// names, Monday-first weeks. The original element becomes a hidden input
// that still carries the canonical "YYYY-MM-DDTHH:mm[:ss]" value and fires
// "change", so existing page code keeps working unchanged.

const DateTimePicker = {
  MONTHS: ["Januar", "Februar", "Mart", "April", "Maj", "Jun", "Jul", "Avgust", "Septembar", "Oktobar", "Novembar", "Decembar"],
  DAYS: ["Pon", "Uto", "Sre", "Čet", "Pet", "Sub", "Ned"],

  pad(n) {
    return String(n).padStart(2, "0");
  },

  toCanonical(date, seconds) {
    const p = this.pad;
    const base = `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
    return seconds ? `${base}:${p(date.getSeconds())}` : base;
  },

  toDisplay(date, seconds) {
    const p = this.pad;
    const base = `${p(date.getDate())}.${p(date.getMonth() + 1)}.${date.getFullYear()}. ${p(date.getHours())}:${p(date.getMinutes())}`;
    return seconds ? `${base}:${p(date.getSeconds())}` : base;
  },

  parseDisplay(text) {
    const m = text.trim().match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\.?\s*(?:(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
    if (!m) return null;
    const d = new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
    if (d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[1]) return null;
    return d;
  },

  enhanceAll(root = document) {
    root.querySelectorAll('input[type="datetime-local"]').forEach((el) => this.attach(el));
  },

  attach(original) {
    if (original._dtp) return original._dtp;
    const seconds = original.getAttribute("step") === "1";
    const picker = this;
    const initial = original.value ? new Date(original.value) : null;
    original.type = "hidden";

    const wrap = document.createElement("span");
    wrap.className = "dtp";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "dtp-input";
    input.placeholder = seconds ? "dd.mm.gggg. ss:mm:ss" : "dd.mm.gggg. ss:mm";
    input.autocomplete = "off";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dtp-btn";
    btn.setAttribute("aria-label", "Otvori kalendar");
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>';
    const pop = document.createElement("div");
    pop.className = "dtp-pop";
    pop.hidden = true;

    original.parentNode.insertBefore(wrap, original);
    wrap.appendChild(input);
    wrap.appendChild(btn);
    wrap.appendChild(pop);
    wrap.appendChild(original);

    const ctl = {
      value: null,
      min: null,
      max: null,
      view: initial ? new Date(initial) : new Date(),
      draft: null,
      setValue(date, { silent = false } = {}) {
        this.value = date ? new Date(date) : null;
        input.value = this.value ? picker.toDisplay(this.value, seconds) : "";
        input.classList.remove("dtp-invalid");
        original.value = this.value ? picker.toCanonical(this.value, seconds) : "";
        if (!silent) original.dispatchEvent(new Event("change", { bubbles: true }));
      },
      getValue() {
        return this.value ? new Date(this.value) : null;
      },
      setMin(d) {
        this.min = d ? new Date(d) : null;
      },
      setMax(d) {
        this.max = d ? new Date(d) : null;
      },
    };
    original._dtp = ctl;
    if (initial) ctl.setValue(initial, { silent: true });

    const onOutside = (e) => {
      if (!wrap.contains(e.target)) close();
    };
    function close() {
      pop.hidden = true;
      document.removeEventListener("mousedown", onOutside, true);
    }

    const render = () => {
      const v = ctl.view;
      const draft = ctl.draft || new Date();
      const first = new Date(v.getFullYear(), v.getMonth(), 1);
      const offset = (first.getDay() + 6) % 7; // Monday-first
      const daysInMonth = new Date(v.getFullYear(), v.getMonth() + 1, 0).getDate();
      const today = new Date();
      let cells = "";
      for (let i = 0; i < offset; i++) cells += "<span></span>";
      for (let day = 1; day <= daysInMonth; day++) {
        const d = new Date(v.getFullYear(), v.getMonth(), day);
        const dayEnd = new Date(v.getFullYear(), v.getMonth(), day, 23, 59, 59);
        const disabled = (ctl.min && dayEnd < ctl.min) || (ctl.max && d > ctl.max);
        const cls = [
          "dtp-day",
          ctl.draft && d.toDateString() === ctl.draft.toDateString() ? "selected" : "",
          d.toDateString() === today.toDateString() ? "today" : "",
        ].join(" ");
        cells += `<button type="button" class="${cls}" data-day="${day}" ${disabled ? "disabled" : ""}>${day}</button>`;
      }
      const p = picker.pad;
      pop.innerHTML = `
        <div class="dtp-head">
          <button type="button" class="dtp-nav" data-nav="-1" aria-label="Prethodni mesec">&#8249;</button>
          <span>${picker.MONTHS[v.getMonth()]} ${v.getFullYear()}.</span>
          <button type="button" class="dtp-nav" data-nav="1" aria-label="Sledeći mesec">&#8250;</button>
        </div>
        <div class="dtp-grid">${picker.DAYS.map((d) => `<span class="dtp-dow">${d}</span>`).join("")}${cells}</div>
        <div class="dtp-time">
          <span>Vreme</span>
          <input type="number" min="0" max="23" class="dtp-h" value="${p(draft.getHours())}" />:
          <input type="number" min="0" max="59" class="dtp-m" value="${p(draft.getMinutes())}" />
          ${seconds ? `:<input type="number" min="0" max="59" class="dtp-s" value="${p(draft.getSeconds())}" />` : ""}
        </div>
        <div class="dtp-actions">
          <button type="button" class="btn dtp-now">Sada</button>
          <button type="button" class="btn dtp-clear">Očisti</button>
          <button type="button" class="btn btn-primary dtp-apply">Primeni</button>
        </div>`;
    };

    const readTime = (base) => {
      const d = new Date(base);
      const h = Math.min(23, Math.max(0, Number(pop.querySelector(".dtp-h").value) || 0));
      const m = Math.min(59, Math.max(0, Number(pop.querySelector(".dtp-m").value) || 0));
      const sEl = pop.querySelector(".dtp-s");
      const s = sEl ? Math.min(59, Math.max(0, Number(sEl.value) || 0)) : 0;
      d.setHours(h, m, s, 0);
      return d;
    };

    pop.addEventListener("click", (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.dataset.nav) {
        ctl.view = new Date(ctl.view.getFullYear(), ctl.view.getMonth() + Number(t.dataset.nav), 1);
        render();
      } else if (t.dataset.day) {
        const base = readTime(ctl.draft || new Date());
        base.setFullYear(ctl.view.getFullYear(), ctl.view.getMonth(), Number(t.dataset.day));
        ctl.draft = base;
        render();
      } else if (t.classList.contains("dtp-now")) {
        ctl.draft = new Date();
        ctl.view = new Date(ctl.draft);
        render();
      } else if (t.classList.contains("dtp-clear")) {
        ctl.setValue(null);
        close();
      } else if (t.classList.contains("dtp-apply")) {
        let d = readTime(ctl.draft || new Date());
        if (ctl.min && d < ctl.min) d = new Date(ctl.min);
        if (ctl.max && d > ctl.max) d = new Date(ctl.max);
        ctl.setValue(d);
        close();
      }
    });

    btn.addEventListener("click", () => {
      if (!pop.hidden) return close();
      ctl.draft = ctl.value ? new Date(ctl.value) : new Date();
      ctl.view = new Date(ctl.draft);
      render();
      pop.hidden = false;
      document.addEventListener("mousedown", onOutside, true);
    });

    const commitTyped = () => {
      const text = input.value.trim();
      if (!text) {
        if (ctl.value) ctl.setValue(null);
        return;
      }
      const d = picker.parseDisplay(text);
      if (!d) {
        input.classList.add("dtp-invalid");
        return;
      }
      if (!ctl.value || d.getTime() !== ctl.value.getTime()) ctl.setValue(d);
      else input.classList.remove("dtp-invalid");
    };
    input.addEventListener("change", commitTyped);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") commitTyped();
      if (e.key === "Escape") close();
    });

    return ctl;
  },
};

DateTimePicker.enhanceAll();

// --- app version badge next to the page title ---
// Version lives in app/version.py and is served by GET /api/version; cached
// per tab so the badge doesn't flicker on every navigation.
(function showAppVersion() {
  const title = document.querySelector(".app-title h1");
  if (!title) return;
  const render = (v) => {
    if (!v || title.querySelector(".app-version")) return;
    const badge = document.createElement("span");
    badge.className = "app-version";
    badge.textContent = `v${v}`;
    badge.title = `Network Device Watcher verzija ${v}`;
    title.appendChild(badge);
  };
  let cached = null;
  try {
    cached = sessionStorage.getItem("nw_app_version");
  } catch (e) {
    /* storage disabled */
  }
  if (cached) render(cached);
  fetch("/api/version")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      if (!d || !d.version) return;
      try {
        sessionStorage.setItem("nw_app_version", d.version);
      } catch (e) {
        /* storage disabled */
      }
      const existing = title.querySelector(".app-version");
      if (existing) existing.textContent = `v${d.version}`;
      else render(d.version);
    })
    .catch(() => {});
})();
