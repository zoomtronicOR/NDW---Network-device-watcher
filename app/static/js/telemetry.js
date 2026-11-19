const REFRESH_MS = 5000;
let refreshTimer = null;

function gaugeColor(pct) {
  if (pct >= 90) return "var(--bad)";
  if (pct >= 70) return "var(--warn)";
  return "var(--ok)";
}

function gaugeBar(pct) {
  const clamped = Math.max(0, Math.min(100, pct || 0));
  return `
    <div class="tel-gauge-track">
      <div class="tel-gauge-fill" style="width:${clamped}%;background:${gaugeColor(clamped)}"></div>
      <span class="tel-gauge-label">${(pct || 0).toFixed(0)}%</span>
    </div>
  `;
}

function setStat(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderCores(perCore) {
  const wrap = document.getElementById("tel-cores");
  wrap.innerHTML = perCore
    .map(
      (pct, i) => `
      <div class="tel-core-row">
        <span class="tel-core-label">CPU${i}</span>
        ${gaugeBar(pct)}
      </div>
    `
    )
    .join("");
}

function renderKv(id, rows) {
  const el = document.getElementById(id);
  el.innerHTML = rows
    .map(
      ([label, value]) => `
      <div class="tel-kv-row"><span class="tel-kv-label">${escapeHtml(label)}</span><span class="tel-kv-value">${escapeHtml(value)}</span></div>
    `
    )
    .join("");
}

async function loadTelemetry() {
  try {
    const t = await Api.getTelemetry();

    setStat("stat-cpu", `${t.cpu_percent.toFixed(0)}%`);
    setStat("stat-ram", `${t.memory.percent.toFixed(0)}%`);
    setStat("stat-disk", `${t.disk.percent.toFixed(0)}%`);
    setStat("stat-uptime", fmtDuration(t.uptime_seconds));
    setStat("stat-load", t.load_avg["1m"].toFixed(2));
    setStat("stat-swap", `${t.swap.percent.toFixed(0)}%`);

    document.getElementById("tel-cpu-gauge").innerHTML = gaugeBar(t.cpu_percent);
    renderCores(t.cpu_per_core);
    renderKv("tel-cpu-kv", [
      ["Broj jezgara", t.cpu_count],
      ["Load average (1m / 5m / 15m)", `${t.load_avg["1m"].toFixed(2)} / ${t.load_avg["5m"].toFixed(2)} / ${t.load_avg["15m"].toFixed(2)}`],
    ]);

    document.getElementById("tel-ram-gauge").innerHTML = gaugeBar(t.memory.percent);
    document.getElementById("tel-swap-gauge").innerHTML = gaugeBar(t.swap.percent);
    renderKv("tel-ram-kv", [
      ["Ukupno", fmtBytes(t.memory.total)],
      ["Zauzeto", fmtBytes(t.memory.used)],
      ["Dostupno", fmtBytes(t.memory.available)],
      ["Swap", `${fmtBytes(t.swap.used)} / ${fmtBytes(t.swap.total)}`],
    ]);

    document.getElementById("tel-disk-gauge").innerHTML = gaugeBar(t.disk.percent);
    const diskRows = [
      ["Ukupno", fmtBytes(t.disk.total)],
      ["Zauzeto", fmtBytes(t.disk.used)],
      ["Slobodno", fmtBytes(t.disk.free)],
    ];
    if (t.disk_io) {
      diskRows.push(["Pročitano (od boot-a)", fmtBytes(t.disk_io.read_bytes)]);
      diskRows.push(["Upisano (od boot-a)", fmtBytes(t.disk_io.write_bytes)]);
    }
    renderKv("tel-disk-kv", diskRows);

    renderKv("tel-network-kv", [
      ["Poslato", fmtBytes(t.network_io.bytes_sent)],
      ["Primljeno", fmtBytes(t.network_io.bytes_recv)],
      ["Paketa poslato", t.network_io.packets_sent.toLocaleString("sr-RS")],
      ["Paketa primljeno", t.network_io.packets_recv.toLocaleString("sr-RS")],
    ]);

    renderKv("tel-process-kv", [
      ["PID", t.process.pid],
      ["RAM (RSS)", fmtBytes(t.process.rss_bytes)],
      ["CPU", `${t.process.cpu_percent.toFixed(1)}%`],
      ["Threadova", t.process.num_threads],
      ["Pokrenut", fmtDateTime(t.process.create_time)],
    ]);

    const systemRows = [
      ["Hostname", t.hostname],
      ["Platforma", t.platform],
      ["Python", t.python_version],
      ["Sistem pokrenut", fmtDateTime(t.boot_time)],
      ["Uptime", fmtDuration(t.uptime_seconds)],
    ];
    Object.entries(t.temperatures || {}).forEach(([name, val]) => {
      systemRows.push([`Temperatura (${name})`, `${val.toFixed(1)} °C`]);
    });
    renderKv("tel-system-kv", systemRows);

    document.getElementById("tel-updated").textContent = `Ažurirano: ${fmtDateTime(new Date().toISOString())}`;
  } catch (err) {
    console.error("loadTelemetry failed", err);
  } finally {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(loadTelemetry, REFRESH_MS);
  }
}

loadTelemetry();
