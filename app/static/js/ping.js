const DEFAULT_REFRESH_MS = 10000;
const VIEW_STORAGE_KEY = "nw_ping_view";
const PING_RANGES = [
  [1, "1h"],
  [6, "6h"],
  [12, "12h"],
  [24, "24h"],
  [168, "7 dana"],
  [240, "10 dana"],
];
let currentRange = (() => {
  const h = Number(Prefs.get("nw_ping_range", 1));
  return PING_RANGES.some(([v]) => v === h) ? h : 1;
})();
let pingBands = [];
let refreshTimer = null;
let currentView = loadViewPref();

function loadViewPref() {
  try {
    const v = localStorage.getItem(VIEW_STORAGE_KEY);
    if (v === "cards" || v === "meters") return v;
  } catch (err) {
    /* ignore, e.g. storage disabled */
  }
  return "cards";
}

function setView(view) {
  currentView = view;
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, view);
  } catch (err) {
    /* ignore, e.g. storage disabled */
  }
  document.querySelectorAll(".view-toggle-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  document.getElementById("ping-grid").hidden = view !== "cards";
  document.getElementById("ping-meter-list").hidden = view !== "meters";
  // The period only applies to the cards' charts; meters show the latest sample.
  const range = document.getElementById("ping-range");
  if (range) range.style.visibility = view === "cards" ? "" : "hidden";
  const note = document.getElementById("ping-range-note");
  if (note) note.style.visibility = view === "cards" ? "" : "hidden";
}

function colorForRtt(rttMs, bands) {
  for (const band of bands) {
    if (band.max_ms == null || rttMs <= band.max_ms) return band.color;
  }
  return (bands[bands.length - 1] && bands[bands.length - 1].color) || "#22d3ee";
}

function renderCard(series) {
  const t = series.target;
  const latest = series.latest;
  const unreachable = !latest || !latest.reachable;
  const color = unreachable ? "#F87171" : colorForRtt(latest.rtt_avg, pingBands);

  const card = document.createElement("div");
  card.className = `ping-card${unreachable ? " unreachable" : ""}`;
  card.innerHTML = `
    <div class="ping-card-header">
      <div class="ping-address">${escapeHtml(t.address)}</div>
      <div class="ping-label">${escapeHtml(t.label) || ""}</div>
    </div>
    <div class="ping-stats">
      <div class="stat"><span class="val">${latest && !unreachable ? latest.rtt_avg.toFixed(1) : "—"}</span><span class="lbl">ms (avg)</span></div>
      <div class="stat"><span class="val">${latest ? latest.packet_loss_pct.toFixed(0) : "-"}</span><span class="lbl">% loss</span></div>
      <div class="stat"><span class="val">${latest && latest.rtt_min != null ? latest.rtt_min.toFixed(1) : "-"}</span><span class="lbl">min ms</span></div>
      <div class="stat"><span class="val">${latest && latest.rtt_max != null ? latest.rtt_max.toFixed(1) : "-"}</span><span class="lbl">max ms</span></div>
      <div class="stat"><span class="val">${latest ? fmtDateTime(latest.timestamp).split(" ")[1] || fmtDateTime(latest.timestamp) : "-"}</span><span class="lbl">poslednji</span></div>
    </div>
    <div class="ping-chart-wrap" id="ping-chart-${t.id}"></div>
  `;
  return card;
}

// Scale (in ms) the horizontal meter track covers. Sized off the highest
// finite band threshold so the last ("and above") band still gets a
// visible-width red zone at the right edge of the track.
function meterScaleMax(bands) {
  const finite = bands.filter((b) => b.max_ms != null).map((b) => b.max_ms);
  const lastFinite = finite.length ? Math.max(...finite) : 300;
  return lastFinite * 1.4;
}

function renderMeterRow(series, scaleMax) {
  const t = series.target;
  const latest = series.latest;
  const unreachable = !latest || !latest.reachable;
  const rtt = latest && !unreachable ? latest.rtt_avg : null;
  const color = unreachable ? "#F87171" : colorForRtt(rtt, pingBands);

  let prevMax = 0;
  const segmentsHtml = pingBands
    .map((band) => {
      const bandMax = band.max_ms == null ? scaleMax : Math.min(band.max_ms, scaleMax);
      const widthPct = Math.max(0, ((bandMax - prevMax) / scaleMax) * 100);
      prevMax = bandMax;
      return `<div class="ping-meter-segment" style="width:${widthPct}%;background:${band.color}"></div>`;
    })
    .join("");

  const cursorPct = unreachable ? 100 : Math.max(0, Math.min(100, (rtt / scaleMax) * 100));
  const cursorLabel = unreachable ? "nedostupno" : `${rtt.toFixed(0)} ms`;

  const row = document.createElement("div");
  row.className = `ping-meter-row${unreachable ? " unreachable" : ""}`;
  row.innerHTML = `
    <div class="ping-meter-info">
      <div class="ping-address">${escapeHtml(t.address)}</div>
      <div class="ping-label">${escapeHtml(t.label) || ""}</div>
    </div>
    <div class="ping-meter-track-wrap">
      <div class="ping-meter-track">
        ${segmentsHtml}
      </div>
      <div class="ping-meter-cursor" style="left:${cursorPct}%;background:${color};border-color:${color}">
        <span class="ping-meter-cursor-label" style="background:${color}">${cursorLabel}</span>
      </div>
      <div class="ping-meter-scale"><span>0 ms</span><span>${Math.round(scaleMax)} ms</span></div>
    </div>
    <div class="ping-meter-loss">
      <span class="val">${latest ? latest.packet_loss_pct.toFixed(0) : "-"}%</span>
      <span class="lbl">gubitak</span>
    </div>
  `;
  return row;
}

async function loadPing() {
  let refreshMs = DEFAULT_REFRESH_MS;
  try {
    const [settings, series] = await Promise.all([Api.getPingSettings(), Api.getPingSeries(currentRange)]);
    pingBands = settings.color_bands || [];
    if (settings.interval_seconds) refreshMs = Math.max(2000, settings.interval_seconds * 1000);
    // Long ranges are server-side buckets of minutes/hours: no point
    // re-querying them every few seconds.
    if (currentRange > 1) refreshMs = Math.max(refreshMs, currentRange >= 24 ? 60000 : 20000);
    const nowMs = Date.now();
    const xDomain = [new Date(nowMs - currentRange * 3600e3).toISOString(), new Date(nowMs).toISOString()];
    const bucketMin = (currentRange * 60) / 200;
    document.getElementById("ping-range-note").textContent =
      bucketMin >= 1
        ? `Svaka tačka = prosek za ~${bucketMin >= 60 ? `${+(bucketMin / 60).toFixed(1)}h` : `${Math.round(bucketMin)} min`}`
        : "";

    const grid = document.getElementById("ping-grid");
    const meterList = document.getElementById("ping-meter-list");
    if (series.length === 0) {
      const emptyHtml =
        '<div class="panel" style="text-align:center;color:var(--text-faint);padding:40px">Nema ping destinacija. Dodaj ih u Podešavanja &rarr; Ping.</div>';
      grid.innerHTML = `<div style="grid-column:1/-1">${emptyHtml}</div>`;
      meterList.innerHTML = emptyHtml;
      return;
    }

    grid.innerHTML = "";
    series.forEach((s) => {
      const card = renderCard(s);
      grid.appendChild(card);
      const unreachable = !s.latest || !s.latest.reachable;
      const color = unreachable ? "#F87171" : colorForRtt(s.latest.rtt_avg, pingBands);
      Charts.pingChart(document.getElementById(`ping-chart-${s.target.id}`), s.history, { color, xDomain });
    });

    const scaleMax = meterScaleMax(pingBands);
    meterList.innerHTML = "";
    series.forEach((s) => {
      meterList.appendChild(renderMeterRow(s, scaleMax));
    });
  } catch (err) {
    console.error("loadPing failed", err);
  } finally {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(loadPing, refreshMs);
  }
}

function initRangeChips() {
  const wrap = document.getElementById("ping-range");
  wrap.innerHTML = PING_RANGES.map(([h, l]) => `<button type="button" class="range-chip" data-hours="${h}">${l}</button>`).join("");
  const sync = () => wrap.querySelectorAll(".range-chip").forEach((b) => b.classList.toggle("active", Number(b.dataset.hours) === currentRange));
  wrap.addEventListener("click", (e) => {
    const b = e.target.closest(".range-chip");
    if (!b) return;
    currentRange = Number(b.dataset.hours);
    Prefs.set("nw_ping_range", currentRange);
    sync();
    loadPing();
  });
  sync();
}

function initViewToggle() {
  document.querySelectorAll(".view-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  setView(currentView);
}

initViewToggle();
initRangeChips();
loadPing();
