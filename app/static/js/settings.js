function setResult(elId, success, message) {
  const el = document.getElementById(elId);
  el.style.color = success ? "var(--ok)" : "var(--bad)";
  el.textContent = message;
}

async function loadMqttSettings() {
  try {
    const s = await Api.getMqttSettings();
    document.getElementById("mqtt-enabled").checked = s.enabled;
    document.getElementById("mqtt-host").value = s.host || "";
    document.getElementById("mqtt-port").value = s.port;
    document.getElementById("mqtt-username").value = s.username || "";
    document.getElementById("mqtt-client-id").value = s.client_id;
    document.getElementById("mqtt-base-topic").value = s.base_topic;
    document.getElementById("mqtt-qos").value = String(s.qos);
    document.getElementById("mqtt-tls").checked = s.tls_enabled;
    document.getElementById("mqtt-retain").checked = s.retain;
    document.getElementById("ha-enabled").checked = s.ha_discovery_enabled;
    document.getElementById("ha-prefix").value = s.ha_discovery_prefix;
    document.getElementById("mqtt-password-note").textContent = s.password_set
      ? "Lozinka je sačuvana (šifrovano). Ostavi prazno da je zadržiš, ili unesi novu da je zameniš."
      : "Lozinka nije podešena.";
  } catch (err) {
    console.error("loadMqttSettings failed", err);
    setResult("mqtt-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveMqttSettings() {
  const payload = {
    enabled: document.getElementById("mqtt-enabled").checked,
    host: document.getElementById("mqtt-host").value.trim() || null,
    port: Number(document.getElementById("mqtt-port").value) || 1883,
    username: document.getElementById("mqtt-username").value.trim() || null,
    tls_enabled: document.getElementById("mqtt-tls").checked,
    client_id: document.getElementById("mqtt-client-id").value.trim() || "networkwatcher",
    base_topic: document.getElementById("mqtt-base-topic").value.trim() || "networkwatcher",
    qos: Number(document.getElementById("mqtt-qos").value),
    retain: document.getElementById("mqtt-retain").checked,
    ha_discovery_enabled: document.getElementById("ha-enabled").checked,
    ha_discovery_prefix: document.getElementById("ha-prefix").value.trim() || "homeassistant",
  };
  const passwordInput = document.getElementById("mqtt-password").value;
  if (passwordInput) payload.password = passwordInput;

  const btn = document.getElementById("mqtt-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateMqttSettings(payload);
    document.getElementById("mqtt-password").value = "";
    setResult("mqtt-result", true, "Podešavanja sačuvana.");
    await loadMqttSettings();
  } catch (err) {
    console.error("saveMqttSettings failed", err);
    setResult("mqtt-result", false, "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

async function testMqtt() {
  const btn = document.getElementById("mqtt-test-btn");
  btn.disabled = true;
  btn.textContent = "Testiranje...";
  setResult("mqtt-result", true, "Povezivanje na broker...");
  try {
    const result = await Api.testMqtt();
    setResult("mqtt-result", result.success, result.message);
  } catch (err) {
    console.error("testMqtt failed", err);
    setResult("mqtt-result", false, "Greška pri testiranju konekcije.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Test MQTT";
  }
}

document.getElementById("mqtt-save-btn").addEventListener("click", saveMqttSettings);
document.getElementById("mqtt-test-btn").addEventListener("click", testMqtt);

async function loadSmtpSettings() {
  try {
    const s = await Api.getSmtpSettings();
    document.getElementById("smtp-enabled").checked = s.enabled;
    document.getElementById("smtp-host").value = s.host || "";
    document.getElementById("smtp-port").value = s.port;
    document.getElementById("smtp-username").value = s.username || "";
    document.getElementById("smtp-security").value = s.security;
    document.getElementById("smtp-from").value = s.from_address || "";
    document.getElementById("smtp-recipients").value = (s.recipients || []).join(", ");
    document.getElementById("smtp-subject-prefix").value = s.subject_prefix;
    document.getElementById("smtp-password-note").textContent = s.password_set
      ? "Lozinka je sačuvana (šifrovano). Ostavi prazno da je zadržiš, ili unesi novu da je zameniš."
      : "Lozinka nije podešena.";
  } catch (err) {
    console.error("loadSmtpSettings failed", err);
    setResult("smtp-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveSmtpSettings() {
  const recipients = document
    .getElementById("smtp-recipients")
    .value.split(",")
    .map((r) => r.trim())
    .filter(Boolean);

  const payload = {
    enabled: document.getElementById("smtp-enabled").checked,
    host: document.getElementById("smtp-host").value.trim() || null,
    port: Number(document.getElementById("smtp-port").value) || 587,
    username: document.getElementById("smtp-username").value.trim() || null,
    security: document.getElementById("smtp-security").value,
    from_address: document.getElementById("smtp-from").value.trim() || null,
    recipients: recipients,
    subject_prefix: document.getElementById("smtp-subject-prefix").value.trim() || "[Network Watcher]",
  };
  const passwordInput = document.getElementById("smtp-password").value;
  if (passwordInput) payload.password = passwordInput;

  const btn = document.getElementById("smtp-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateSmtpSettings(payload);
    document.getElementById("smtp-password").value = "";
    setResult("smtp-result", true, "Podešavanja sačuvana.");
    await loadSmtpSettings();
  } catch (err) {
    console.error("saveSmtpSettings failed", err);
    setResult("smtp-result", false, "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

async function testSmtp() {
  const btn = document.getElementById("smtp-test-btn");
  btn.disabled = true;
  btn.textContent = "Slanje...";
  setResult("smtp-result", true, "Slanje test poruke...");
  try {
    const result = await Api.testSmtp();
    setResult("smtp-result", result.success, result.message);
  } catch (err) {
    console.error("testSmtp failed", err);
    setResult("smtp-result", false, "Greška pri testiranju konekcije.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Test Email";
  }
}

document.getElementById("smtp-save-btn").addEventListener("click", saveSmtpSettings);
document.getElementById("smtp-test-btn").addEventListener("click", testSmtp);

async function loadQuietHours() {
  try {
    const s = await Api.getNotificationSettings();
    document.getElementById("qh-enabled").checked = s.quiet_hours_enabled;
    document.getElementById("qh-start").value = s.quiet_hours_start;
    document.getElementById("qh-end").value = s.quiet_hours_end;
    document.getElementById("qh-timezone").value = s.timezone || "Europe/Belgrade";
  } catch (err) {
    console.error("loadQuietHours failed", err);
  }
}

async function saveQuietHours() {
  const payload = {
    quiet_hours_enabled: document.getElementById("qh-enabled").checked,
    quiet_hours_start: document.getElementById("qh-start").value.trim() || "23:00",
    quiet_hours_end: document.getElementById("qh-end").value.trim() || "07:00",
    timezone: document.getElementById("qh-timezone").value.trim() || "Europe/Belgrade",
  };
  const btn = document.getElementById("qh-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateNotificationSettings(payload);
    setResult("qh-result", true, "Tiha zona sačuvana.");
  } catch (err) {
    console.error("saveQuietHours failed", err);
    setResult("qh-result", false, err.message || "Greška pri čuvanju.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj tihu zonu";
  }
}

document.getElementById("qh-save-btn").addEventListener("click", saveQuietHours);

async function loadScannerSettings() {
  try {
    const s = await Api.getScannerSettings();
    document.getElementById("sc-interval").value = s.scan_interval_seconds;
    document.getElementById("sc-offline-threshold").value = s.offline_threshold;
    document.getElementById("sc-offline-grace").value = s.offline_grace_seconds;
    document.getElementById("sc-interface").value = s.interface || "";
    document.getElementById("sc-settle").value = s.settle_seconds;
    document.getElementById("sc-ranges").value = (s.network_ranges || []).join("\n");
    document.getElementById("sc-resolve-hostnames").checked = s.resolve_hostnames;
  } catch (err) {
    console.error("loadScannerSettings failed", err);
    setResult("sc-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveScannerSettings() {
  const ranges = document
    .getElementById("sc-ranges")
    .value.split("\n")
    .map((r) => r.trim())
    .filter(Boolean);

  const payload = {
    scan_interval_seconds: Number(document.getElementById("sc-interval").value) || 30,
    offline_threshold: Number(document.getElementById("sc-offline-threshold").value) || 3,
    offline_grace_seconds: Math.max(0, Number(document.getElementById("sc-offline-grace").value) || 0),
    interface: document.getElementById("sc-interface").value.trim() || null,
    settle_seconds: Number(document.getElementById("sc-settle").value) || 1.5,
    network_ranges: ranges,
    resolve_hostnames: document.getElementById("sc-resolve-hostnames").checked,
  };

  const btn = document.getElementById("sc-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateScannerSettings(payload);
    setResult("sc-result", true, "Podešavanja sačuvana. Scanner ih učitava na sledećem ciklusu.");
  } catch (err) {
    console.error("saveScannerSettings failed", err);
    setResult("sc-result", false, err.message || "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

document.getElementById("sc-save-btn").addEventListener("click", saveScannerSettings);

function renderScanDetectionStatus(s) {
  const el = document.getElementById("sd-status");
  const fresh = s.last_heartbeat_at && Date.now() - new Date(s.last_heartbeat_at).getTime() < 120000;
  el.className = `sd-status ${fresh ? "ok" : "bad"}`;
  el.innerHTML = fresh
    ? `<span class="led on"></span> Sniffer radi &middot; poslednji signal ${timeAgo(s.last_heartbeat_at)} &middot; ${s.packets_seen ?? 0} ARP paketa od pokretanja`
    : `<span class="led off"></span> Sniffer servis se ne javlja${s.last_heartbeat_at ? ` (poslednji signal ${timeAgo(s.last_heartbeat_at)})` : ""} - proveri <code>systemctl status networkwatcher-sniffer</code>`;
}

function renderKnownScanners(list) {
  const el = document.getElementById("sd-known-list");
  if (!list.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `<div class="known-scanners">${list
    .map((k) => {
      const title = `${escapeHtml(k.name || "nepoznat uređaj")} <span class="mono muted">${escapeHtml(k.mac)}</span>`;
      let state;
      if (!k.observed) state = '<span class="muted">još nije viđen da skenira</span>';
      else if (k.learning)
        state = `<span class="auto-tag">uči</span> do ${fmtDateTime(k.learning_until)} &middot; upozorenja kreću posle toga`;
      else
        state = `<span class="led on"></span> naučeno: ~${k.requests_per_hour ?? "-"} ARP upita/h, obično ${k.typical_targets ?? "-"} adresa po prolazu (najviše ${k.max_targets ?? "-"}), IP: ${(k.ips || []).map(escapeHtml).join(", ") || "-"}`;
      return `<div class="known-scanner-row"><div>${title}</div><div class="known-scanner-state">${state}</div></div>`;
    })
    .join("")}</div>`;
}

async function loadScanDetectionSettings() {
  try {
    const s = await Api.getScanDetectionSettings();
    document.getElementById("sd-enabled").checked = s.enabled;
    document.getElementById("sd-threshold").value = s.threshold_hosts;
    document.getElementById("sd-window").value = s.window_seconds;
    document.getElementById("sd-conflict").checked = s.ip_conflict_enabled;
    document.getElementById("sd-cooldown").value = s.cooldown_seconds;
    document.getElementById("sd-conflict-window").value = s.conflict_window_seconds;
    document.getElementById("sd-ignore").value = (s.ignore_macs || []).join("\n");
    renderScanDetectionStatus(s);
    renderKnownScanners(s.known_scanners || []);
  } catch (err) {
    console.error("loadScanDetectionSettings failed", err);
    setResult("sd-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveScanDetectionSettings() {
  const payload = {
    enabled: document.getElementById("sd-enabled").checked,
    threshold_hosts: Number(document.getElementById("sd-threshold").value) || 30,
    window_seconds: Number(document.getElementById("sd-window").value) || 60,
    ip_conflict_enabled: document.getElementById("sd-conflict").checked,
    cooldown_seconds: Number(document.getElementById("sd-cooldown").value) || 600,
    conflict_window_seconds: Number(document.getElementById("sd-conflict-window").value) || 600,
    ignore_macs: document
      .getElementById("sd-ignore")
      .value.split(/[\n,;]+/)
      .map((m) => m.trim())
      .filter(Boolean),
  };
  const btn = document.getElementById("sd-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    const s = await Api.updateScanDetectionSettings(payload);
    document.getElementById("sd-ignore").value = (s.ignore_macs || []).join("\n");
    setResult("sd-result", true, "Sačuvano. Sniffer učitava nova podešavanja u roku od 30s.");
  } catch (err) {
    console.error("saveScanDetectionSettings failed", err);
    setResult("sd-result", false, err.message || "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

document.getElementById("sd-save-btn").addEventListener("click", saveScanDetectionSettings);

const HIST_PRESETS = new Set([7, 30, 90, 365]);

function setHistoryPresetUI(retentionDays) {
  const presetSelect = document.getElementById("hist-retention-preset");
  const customWrap = document.getElementById("hist-custom-days-wrap");
  if (retentionDays == null) {
    presetSelect.value = "unlimited";
    customWrap.style.display = "none";
  } else if (HIST_PRESETS.has(retentionDays)) {
    presetSelect.value = String(retentionDays);
    customWrap.style.display = "none";
  } else {
    presetSelect.value = "custom";
    document.getElementById("hist-custom-days").value = retentionDays;
    customWrap.style.display = "";
  }
}

document.getElementById("hist-retention-preset").addEventListener("change", (e) => {
  document.getElementById("hist-custom-days-wrap").style.display = e.target.value === "custom" ? "" : "none";
});

const PING_HIST_PRESETS = new Set([1, 3, 7, 10, 30, 90]);

function setPingRetentionUI(days) {
  const sel = document.getElementById("hist-ping-preset");
  const wrap = document.getElementById("hist-ping-custom-wrap");
  if (days == null) {
    sel.value = "unlimited";
    wrap.style.display = "none";
  } else if (PING_HIST_PRESETS.has(days)) {
    sel.value = String(days);
    wrap.style.display = "none";
  } else {
    sel.value = "custom";
    document.getElementById("hist-ping-custom-days").value = days;
    wrap.style.display = "";
  }
  updatePingRetentionNote();
}

function updatePingRetentionNote() {
  const v = document.getElementById("hist-ping-preset").value;
  const days = v === "custom" ? Number(document.getElementById("hist-ping-custom-days").value) : Number(v);
  const note = document.getElementById("hist-ping-note");
  note.textContent =
    v !== "unlimited" && days > 0 && days < 10
      ? `Ping tab nudi prikaz do 10 dana - sa ${days} dana čuvanja duži periodi će biti delimično prazni.`
      : v === "unlimited"
      ? "Ping merenja se nikad ne brišu - tabela raste neograničeno (pratiti zauzeće diska)."
      : "";
}

document.getElementById("hist-ping-preset").addEventListener("change", (e) => {
  document.getElementById("hist-ping-custom-wrap").style.display = e.target.value === "custom" ? "" : "none";
  updatePingRetentionNote();
});
document.getElementById("hist-ping-custom-days").addEventListener("input", updatePingRetentionNote);

async function loadHistorySettings() {
  try {
    const s = await Api.getHistorySettings();
    setHistoryPresetUI(s.retention_days);
    setPingRetentionUI(s.ping_retention_days);
  } catch (err) {
    console.error("loadHistorySettings failed", err);
    setResult("hist-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveHistorySettings() {
  const preset = document.getElementById("hist-retention-preset").value;
  let retentionDays;
  if (preset === "unlimited") {
    retentionDays = null;
  } else if (preset === "custom") {
    retentionDays = Number(document.getElementById("hist-custom-days").value) || 0;
    if (retentionDays <= 0) {
      setResult("hist-result", false, "Unesi ispravan broj dana.");
      return;
    }
  } else {
    retentionDays = Number(preset);
  }

  const pingPreset = document.getElementById("hist-ping-preset").value;
  let pingDays;
  if (pingPreset === "unlimited") {
    pingDays = null;
  } else if (pingPreset === "custom") {
    pingDays = Number(document.getElementById("hist-ping-custom-days").value) || 0;
    if (pingDays <= 0) {
      setResult("hist-result", false, "Unesi ispravan broj dana za ping statistiku.");
      return;
    }
  } else {
    pingDays = Number(pingPreset);
  }

  const btn = document.getElementById("hist-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateHistorySettings({ retention_days: retentionDays, ping_retention_days: pingDays });
    setResult("hist-result", true, "Podešavanja sačuvana.");
  } catch (err) {
    console.error("saveHistorySettings failed", err);
    setResult("hist-result", false, err.message || "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

document.getElementById("hist-save-btn").addEventListener("click", saveHistorySettings);

document.getElementById("hist-cleanup-btn").addEventListener("click", async () => {
  const btn = document.getElementById("hist-cleanup-btn");
  btn.disabled = true;
  btn.textContent = "Čišćenje...";
  try {
    const r = await Api.runHistoryCleanup();
    const total = r.device_events + r.ip_history + r.notification_log + (r.ping_results || 0);
    setResult(
      "hist-cleanup-result",
      true,
      total === 0
        ? "Nema ničega za brisanje."
        : `Obrisano: ${r.device_events} događaja, ${r.ip_history} IP zapisa, ${r.notification_log} log obaveštenja, ${r.ping_results || 0} ping merenja.`
    );
  } catch (err) {
    console.error("runHistoryCleanup failed", err);
    setResult("hist-cleanup-result", false, err.message || "Greška pri čišćenju.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Pokreni čišćenje sada";
  }
});

async function loadWebhookSettings() {
  try {
    const s = await Api.getWebhookSettings();
    document.getElementById("wh-enabled").checked = s.enabled;
    document.getElementById("wh-url").value = s.url || "";
    document.getElementById("wh-headers").value = Object.entries(s.headers || {})
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n");
  } catch (err) {
    console.error("loadWebhookSettings failed", err);
    setResult("wh-result", false, "Greška pri učitavanju podešavanja.");
  }
}

function parseHeaders(text) {
  const headers = {};
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .forEach((line) => {
      const idx = line.indexOf(":");
      if (idx === -1) return;
      headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    });
  return headers;
}

async function saveWebhookSettings() {
  const payload = {
    enabled: document.getElementById("wh-enabled").checked,
    url: document.getElementById("wh-url").value.trim() || null,
    headers: parseHeaders(document.getElementById("wh-headers").value),
  };
  const btn = document.getElementById("wh-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateWebhookSettings(payload);
    setResult("wh-result", true, "Podešavanja sačuvana.");
  } catch (err) {
    console.error("saveWebhookSettings failed", err);
    setResult("wh-result", false, "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

async function testWebhook() {
  const btn = document.getElementById("wh-test-btn");
  btn.disabled = true;
  btn.textContent = "Slanje...";
  setResult("wh-result", true, "Slanje test poziva...");
  try {
    const result = await Api.testWebhook();
    setResult("wh-result", result.success, result.message);
  } catch (err) {
    console.error("testWebhook failed", err);
    setResult("wh-result", false, "Greška pri testiranju webhook-a.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Webhook";
  }
}

document.getElementById("wh-save-btn").addEventListener("click", saveWebhookSettings);
document.getElementById("wh-test-btn").addEventListener("click", testWebhook);

function setOmadaSiteOptions(sites, selectedId, selectedName) {
  const select = document.getElementById("omada-site");
  select.innerHTML = "";
  if (selectedId && !sites.some((s) => s.site_id === selectedId)) {
    sites = [{ site_id: selectedId, name: selectedName || selectedId }, ...sites];
  }
  if (sites.length === 0) {
    select.innerHTML = '<option value="">- klikni "Učitaj lokacije" -</option>';
    return;
  }
  select.innerHTML = sites
    .map((s) => `<option value="${s.site_id}">${escapeHtml(s.name)}</option>`)
    .join("");
  if (selectedId) select.value = selectedId;
}

async function loadOmadaSettings() {
  try {
    const s = await Api.getOmadaSettings();
    document.getElementById("omada-enabled").checked = s.enabled;
    document.getElementById("omada-verify-ssl").checked = s.verify_ssl;
    document.getElementById("omada-url").value = s.controller_url || "";
    document.getElementById("omada-omadac-id").value = s.omadac_id || "";
    document.getElementById("omada-client-id").value = s.client_id || "";
    document.getElementById("omada-secret-hint").textContent = s.client_secret_set
      ? "Client Secret je podešen."
      : "Client Secret nije podešen.";
    setOmadaSiteOptions([], s.site_id, s.site_name);
  } catch (err) {
    console.error("loadOmadaSettings failed", err);
    setResult("omada-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveOmadaSettings() {
  const siteSelect = document.getElementById("omada-site");
  const siteOption = siteSelect.options[siteSelect.selectedIndex];
  const payload = {
    enabled: document.getElementById("omada-enabled").checked,
    verify_ssl: document.getElementById("omada-verify-ssl").checked,
    controller_url: document.getElementById("omada-url").value.trim() || null,
    omadac_id: document.getElementById("omada-omadac-id").value.trim() || null,
    client_id: document.getElementById("omada-client-id").value.trim() || null,
  };
  const secret = document.getElementById("omada-client-secret").value;
  if (secret) payload.client_secret = secret;
  if (siteOption && siteOption.value) {
    payload.site_id = siteOption.value;
    payload.site_name = siteOption.textContent;
  }

  const btn = document.getElementById("omada-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updateOmadaSettings(payload);
    document.getElementById("omada-client-secret").value = "";
    setResult("omada-result", true, "Podešavanja sačuvana. Scanner ih učitava na sledećem ciklusu.");
    loadOmadaSettings();
  } catch (err) {
    console.error("saveOmadaSettings failed", err);
    setResult("omada-result", false, err.message || "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

async function testOmada() {
  const btn = document.getElementById("omada-test-btn");
  btn.disabled = true;
  btn.textContent = "Testiranje...";
  setResult("omada-result", true, "Testiranje konekcije...");
  try {
    const result = await Api.testOmada();
    setResult("omada-result", result.success, result.message);
  } catch (err) {
    console.error("testOmada failed", err);
    setResult("omada-result", false, "Greška pri testiranju konekcije.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Testiraj konekciju";
  }
}

async function loadOmadaSites() {
  const btn = document.getElementById("omada-sites-btn");
  btn.disabled = true;
  btn.textContent = "Učitavanje...";
  try {
    const sites = await Api.getOmadaSites();
    const select = document.getElementById("omada-site");
    const current = select.value;
    setOmadaSiteOptions(sites, current);
    setResult("omada-result", true, `Učitano lokacija: ${sites.length}`);
  } catch (err) {
    console.error("loadOmadaSites failed", err);
    setResult("omada-result", false, err.message || "Greška pri učitavanju lokacija. Sačuvaj podešavanja pre ovoga.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Učitaj lokacije";
  }
}

document.getElementById("omada-save-btn").addEventListener("click", saveOmadaSettings);
document.getElementById("omada-test-btn").addEventListener("click", testOmada);
document.getElementById("omada-sites-btn").addEventListener("click", loadOmadaSites);

document.getElementById("bk-import-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("bk-import-file");
  const file = fileInput.files[0];
  if (!file) {
    setResult("bk-result", false, "Izaberi fajl za uvoz.");
    return;
  }
  const btn = document.getElementById("bk-import-btn");
  btn.disabled = true;
  btn.textContent = "Uvoženje...";
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const result = await Api.importConfig(payload);
    setResult("bk-result", true, `Uvezeno ${result.imported} podešavanja. Osveži stranicu da vidiš nove vrednosti.`);
  } catch (err) {
    console.error("importConfig failed", err);
    setResult("bk-result", false, "Greška pri uvozu - proveri da li je fajl ispravan JSON backup.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Uvezi";
  }
});

// --- Appearance ---

let savedAppearance = null;

function currentAppearanceFromForm() {
  const position = document.getElementById("ap-bg-position").value;
  const size = document.getElementById("ap-bg-size").value;
  return {
    theme: document.getElementById("ap-theme").value,
    primary_color: document.getElementById("ap-primary").value,
    secondary_color: document.getElementById("ap-secondary").value,
    text_color: document.getElementById("ap-text").value,
    card_style: document.getElementById("ap-card-style").value,
    card_opacity: Number(document.getElementById("ap-opacity").value) / 100,
    border_radius: Number(document.getElementById("ap-radius").value) || 14,
    card_blur: Number(document.getElementById("ap-blur").value) || 0,
    background_enabled: document.getElementById("ap-bg-enabled").checked,
    background_opacity: Number(document.getElementById("ap-bg-opacity").value) / 100,
    background_blur: Number(document.getElementById("ap-bg-blur").value) || 0,
    background_brightness: Number(document.getElementById("ap-bg-brightness").value) || 100,
    background_saturation: Number(document.getElementById("ap-bg-saturation").value) || 100,
    overlay_opacity: Number(document.getElementById("ap-bg-overlay").value) / 100,
    background_position:
      position === "custom" ? document.getElementById("ap-bg-position-custom").value.trim() || "center" : position,
    background_size: size === "custom" ? document.getElementById("ap-bg-size-custom").value.trim() || "cover" : size,
    background_repeat: document.getElementById("ap-bg-repeat").value,
  };
}

function previewAppearance() {
  document.getElementById("ap-custom-colors").style.display =
    document.getElementById("ap-theme").value === "custom" ? "" : "none";
  document.getElementById("ap-opacity-value").textContent = document.getElementById("ap-opacity").value;
  document.getElementById("ap-blur-value").textContent = document.getElementById("ap-blur").value;
  document.getElementById("ap-bg-opacity-value").textContent = document.getElementById("ap-bg-opacity").value;
  document.getElementById("ap-bg-blur-value").textContent = document.getElementById("ap-bg-blur").value;
  document.getElementById("ap-bg-brightness-value").textContent = document.getElementById("ap-bg-brightness").value;
  document.getElementById("ap-bg-saturation-value").textContent = document.getElementById("ap-bg-saturation").value;
  document.getElementById("ap-bg-overlay-value").textContent = document.getElementById("ap-bg-overlay").value;
  document.getElementById("ap-bg-position-custom").style.display =
    document.getElementById("ap-bg-position").value === "custom" ? "" : "none";
  document.getElementById("ap-bg-size-custom").style.display =
    document.getElementById("ap-bg-size").value === "custom" ? "" : "none";

  const form = currentAppearanceFromForm();
  form.background_image = savedAppearance ? savedAppearance.background_image : null;
  if (window.NWTheme) window.NWTheme.apply(form);
}

function applyBackgroundToForm(s) {
  document.getElementById("ap-bg-enabled").checked = s.background_enabled;
  document.getElementById("ap-bg-opacity").value = Math.round(s.background_opacity * 100);
  document.getElementById("ap-bg-blur").value = s.background_blur;
  document.getElementById("ap-bg-brightness").value = s.background_brightness;
  document.getElementById("ap-bg-saturation").value = s.background_saturation;
  document.getElementById("ap-bg-overlay").value = Math.round(s.overlay_opacity * 100);

  const knownPositions = ["center", "top", "bottom"];
  if (knownPositions.includes(s.background_position)) {
    document.getElementById("ap-bg-position").value = s.background_position;
  } else {
    document.getElementById("ap-bg-position").value = "custom";
    document.getElementById("ap-bg-position-custom").value = s.background_position;
  }

  const knownSizes = ["cover", "contain"];
  if (knownSizes.includes(s.background_size)) {
    document.getElementById("ap-bg-size").value = s.background_size;
  } else {
    document.getElementById("ap-bg-size").value = "custom";
    document.getElementById("ap-bg-size-custom").value = s.background_size;
  }

  document.getElementById("ap-bg-repeat").value = s.background_repeat;

  const preview = document.getElementById("ap-bg-preview");
  const previewWrap = document.getElementById("ap-bg-preview-wrap");
  const removeBtn = document.getElementById("ap-bg-remove-btn");
  if (s.background_image) {
    preview.src = s.background_image;
    previewWrap.style.display = "";
    removeBtn.style.display = "";
  } else {
    previewWrap.style.display = "none";
    removeBtn.style.display = "none";
  }
}

async function loadAppearanceSettings() {
  try {
    const s = await Api.getAppearanceSettings();
    savedAppearance = s;
    document.getElementById("ap-theme").value = s.theme;
    document.getElementById("ap-primary").value = s.primary_color;
    document.getElementById("ap-secondary").value = s.secondary_color;
    document.getElementById("ap-text").value = s.text_color;
    document.getElementById("ap-card-style").value = s.card_style;
    document.getElementById("ap-radius").value = s.border_radius;
    document.getElementById("ap-opacity").value = Math.round(s.card_opacity * 100);
    document.getElementById("ap-blur").value = s.card_blur;
    applyBackgroundToForm(s);
    previewAppearance();
  } catch (err) {
    console.error("loadAppearanceSettings failed", err);
    setResult("ap-result", false, "Greška pri učitavanju podešavanja.");
  }
}

async function saveAppearanceSettings() {
  const payload = currentAppearanceFromForm();
  const btn = document.getElementById("ap-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    const result = await Api.updateAppearanceSettings(payload);
    savedAppearance = result;
    try {
      localStorage.setItem("nw_appearance", JSON.stringify(result));
    } catch (e) {
      /* per-viewer cache only */
    }
    setResult("ap-result", true, "Izgled sačuvan.");
  } catch (err) {
    console.error("saveAppearanceSettings failed", err);
    setResult("ap-result", false, err.message || "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}

async function uploadBackgroundFile() {
  const fileInput = document.getElementById("ap-bg-file");
  const file = fileInput.files[0];
  if (!file) {
    setResult("ap-result", false, "Izaberi sliku za upload.");
    return;
  }
  const btn = document.getElementById("ap-bg-upload-btn");
  btn.disabled = true;
  btn.textContent = "Otpremanje...";
  try {
    const result = await Api.uploadBackground(file);
    savedAppearance = result;
    applyBackgroundToForm(result);
    fileInput.value = "";
    try {
      localStorage.setItem("nw_appearance", JSON.stringify(result));
    } catch (e) {
      /* per-viewer cache only */
    }
    previewAppearance();
    setResult("ap-result", true, "Slika otpremljena.");
  } catch (err) {
    console.error("uploadBackgroundFile failed", err);
    setResult("ap-result", false, err.message || "Greška pri otpremanju slike.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload";
  }
}

async function removeBackgroundImage() {
  const btn = document.getElementById("ap-bg-remove-btn");
  btn.disabled = true;
  try {
    const result = await Api.removeBackground();
    savedAppearance = result;
    applyBackgroundToForm(result);
    try {
      localStorage.setItem("nw_appearance", JSON.stringify(result));
    } catch (e) {
      /* per-viewer cache only */
    }
    previewAppearance();
    setResult("ap-result", true, "Pozadinska slika uklonjena.");
  } catch (err) {
    console.error("removeBackgroundImage failed", err);
    setResult("ap-result", false, "Greška pri uklanjanju slike.");
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("ap-save-btn").addEventListener("click", saveAppearanceSettings);
document.getElementById("ap-bg-upload-btn").addEventListener("click", uploadBackgroundFile);
document.getElementById("ap-bg-remove-btn").addEventListener("click", removeBackgroundImage);
[
  "ap-theme",
  "ap-primary",
  "ap-secondary",
  "ap-text",
  "ap-card-style",
  "ap-radius",
  "ap-opacity",
  "ap-blur",
  "ap-bg-enabled",
  "ap-bg-opacity",
  "ap-bg-blur",
  "ap-bg-brightness",
  "ap-bg-saturation",
  "ap-bg-overlay",
  "ap-bg-position",
  "ap-bg-position-custom",
  "ap-bg-size",
  "ap-bg-size-custom",
  "ap-bg-repeat",
].forEach((id) => document.getElementById(id).addEventListener("input", previewAppearance));

// --- Reset ---

document.getElementById("reset-confirm-input").addEventListener("input", (e) => {
  document.getElementById("reset-devices-btn").disabled = e.target.value !== "RESET";
});

document.getElementById("reset-devices-btn").addEventListener("click", async () => {
  const btn = document.getElementById("reset-devices-btn");
  btn.disabled = true;
  btn.textContent = "Brisanje...";
  try {
    const result = await Api.resetDevices();
    setResult("reset-result", true, `Obrisano ${result.deleted} uređaja. Sledeće skeniranje popunjava bazu iznova.`);
    document.getElementById("reset-confirm-input").value = "";
  } catch (err) {
    console.error("resetDevices failed", err);
    setResult("reset-result", false, "Greška pri brisanju uređaja.");
  } finally {
    btn.textContent = "Obriši sve uređaje";
    btn.disabled = document.getElementById("reset-confirm-input").value !== "RESET";
  }
});

// --- Ping ---

async function loadPingSettings() {
  try {
    const s = await Api.getPingSettings();
    document.getElementById("pg-interval").value = s.interval_seconds;
    const bands = s.color_bands || [];
    for (let i = 0; i < 3; i++) {
      const band = bands[i] || {};
      document.getElementById(`pg-band-${i}-max`).value = band.max_ms != null ? band.max_ms : "";
      document.getElementById(`pg-band-${i}-color`).value = band.color || "#34D399";
      document.getElementById(`pg-band-${i}-label`).textContent = band.max_ms != null ? band.max_ms : "-";
    }
    document.getElementById("pg-band-3-color").value = (bands[3] && bands[3].color) || "#F87171";
  } catch (err) {
    console.error("loadPingSettings failed", err);
    setResult("pg-result", false, "Greška pri učitavanju podešavanja.");
  }
}

document.getElementById("pg-band-0-max").addEventListener("input", (e) => {
  document.getElementById("pg-band-0-label").textContent = e.target.value || "-";
});
document.getElementById("pg-band-1-max").addEventListener("input", (e) => {
  document.getElementById("pg-band-1-label").textContent = e.target.value || "-";
});
document.getElementById("pg-band-2-max").addEventListener("input", (e) => {
  document.getElementById("pg-band-2-label").textContent = e.target.value || "-";
});

async function savePingSettings() {
  const bands = [];
  for (let i = 0; i < 3; i++) {
    bands.push({
      max_ms: Number(document.getElementById(`pg-band-${i}-max`).value) || 0,
      color: document.getElementById(`pg-band-${i}-color`).value,
    });
  }
  bands.push({ max_ms: null, color: document.getElementById("pg-band-3-color").value });

  const payload = {
    interval_seconds: Number(document.getElementById("pg-interval").value) || 30,
    color_bands: bands,
  };

  const btn = document.getElementById("pg-save-btn");
  btn.disabled = true;
  btn.textContent = "Čuvanje...";
  try {
    await Api.updatePingSettings(payload);
    setResult("pg-result", true, "Podešavanja sačuvana.");
  } catch (err) {
    console.error("savePingSettings failed", err);
    setResult("pg-result", false, "Greška pri čuvanju podešavanja.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sačuvaj podešavanja";
  }
}
document.getElementById("pg-save-btn").addEventListener("click", savePingSettings);

// Ping destinations: drag handle / arrows to reorder (order is used on the
// Ping page too), inline edit of address and name, enable toggle, delete.
let pingTargetsCache = [];

function renderPingTargetRow(t, idx, total) {
  return `
    <div class="target-row" data-id="${t.id}" draggable="true">
      <span class="drag-handle" title="Prevuci da promeniš redosled">&#10303;</span>
      <span class="order-btns">
        <button type="button" class="icon-btn pg-up" title="Pomeri gore" ${idx === 0 ? "disabled" : ""}>&#9650;</button>
        <button type="button" class="icon-btn pg-down" title="Pomeri dole" ${idx === total - 1 ? "disabled" : ""}>&#9660;</button>
      </span>
      <span class="addr">${escapeHtml(t.address)}</span>
      <span class="lbl">${escapeHtml(t.label) || ""}</span>
      <label class="checkbox"><input type="checkbox" class="pg-enabled-toggle" ${t.enabled ? "checked" : ""} /> aktivan</label>
      <button type="button" class="icon-btn pg-edit" title="Izmeni">&#9998;</button>
      <button type="button" class="remove-btn" title="Ukloni">&times;</button>
    </div>`;
}

async function saveOrder(ids) {
  try {
    pingTargetsCache = await Api.reorderPingTargets(ids);
  } catch (err) {
    console.error("reorder failed", err);
    setResult("pg-result", false, "Greška pri čuvanju redosleda.");
  }
  renderPingTargets();
}

function startEditRow(row, t) {
  row.draggable = false;
  row.classList.add("editing");
  row.innerHTML = `
    <input type="text" class="pg-edit-address" value="${escapeHtml(t.address)}" placeholder="IP adresa / hostname" />
    <input type="text" class="pg-edit-label" value="${escapeHtml(t.label) || ""}" placeholder="Naziv (opciono)" />
    <button type="button" class="btn btn-primary pg-edit-save">Sačuvaj</button>
    <button type="button" class="btn pg-edit-cancel">Otkaži</button>`;
  const addr = row.querySelector(".pg-edit-address");
  const lbl = row.querySelector(".pg-edit-label");
  addr.focus();
  const save = async () => {
    const address = addr.value.trim();
    if (!address) {
      addr.classList.add("dtp-invalid");
      return;
    }
    if (address !== t.address && !confirm(`Promena adrese briše dosadašnju ping statistiku za ${t.address}. Nastaviti?`)) return;
    try {
      await Api.updatePingTarget(t.id, { address, label: lbl.value.trim() || null });
      setResult("pg-result", true, "Destinacija izmenjena.");
    } catch (err) {
      console.error("updatePingTarget failed", err);
      setResult("pg-result", false, err.message || "Greška pri izmeni destinacije.");
    }
    loadPingTargets();
  };
  row.querySelector(".pg-edit-save").addEventListener("click", save);
  row.querySelector(".pg-edit-cancel").addEventListener("click", () => renderPingTargets());
  [addr, lbl].forEach((el) =>
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") save();
      if (e.key === "Escape") renderPingTargets();
    })
  );
}

function renderPingTargets() {
  const list = document.getElementById("pg-targets-list");
  const targets = pingTargetsCache;
  if (!targets.length) {
    list.innerHTML = '<div class="empty">Nema dodatih destinacija</div>';
    return;
  }
  list.innerHTML = targets.map((t, i) => renderPingTargetRow(t, i, targets.length)).join("");
  const ids = targets.map((t) => t.id);

  list.querySelectorAll(".target-row").forEach((row, idx) => {
    const id = Number(row.dataset.id);
    const t = targets[idx];
    row.querySelector(".pg-enabled-toggle").addEventListener("change", async (e) => {
      try {
        await Api.updatePingTarget(id, { enabled: e.target.checked });
        t.enabled = e.target.checked;
      } catch (err) {
        console.error("toggle ping target failed", err);
      }
    });
    row.querySelector(".remove-btn").addEventListener("click", async () => {
      try {
        await Api.deletePingTarget(id);
        loadPingTargets();
      } catch (err) {
        console.error("deletePingTarget failed", err);
      }
    });
    row.querySelector(".pg-edit").addEventListener("click", () => startEditRow(row, t));
    row.querySelector(".pg-up").addEventListener("click", () => {
      const next = [...ids];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      saveOrder(next);
    });
    row.querySelector(".pg-down").addEventListener("click", () => {
      const next = [...ids];
      [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
      saveOrder(next);
    });

    // drag & drop
    row.addEventListener("dragstart", (e) => {
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(id));
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      list.querySelectorAll(".drop-before, .drop-after").forEach((r) => r.classList.remove("drop-before", "drop-after"));
    });
    row.addEventListener("dragover", (e) => {
      e.preventDefault();
      const rect = row.getBoundingClientRect();
      const after = e.clientY > rect.top + rect.height / 2;
      row.classList.toggle("drop-after", after);
      row.classList.toggle("drop-before", !after);
    });
    row.addEventListener("dragleave", () => row.classList.remove("drop-before", "drop-after"));
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      const dragged = Number(e.dataTransfer.getData("text/plain"));
      const after = row.classList.contains("drop-after");
      row.classList.remove("drop-before", "drop-after");
      if (!dragged || dragged === id) return;
      const next = ids.filter((x) => x !== dragged);
      const pos = next.indexOf(id) + (after ? 1 : 0);
      next.splice(pos, 0, dragged);
      saveOrder(next);
    });
  });
}

async function loadPingTargets() {
  try {
    pingTargetsCache = await Api.listPingTargets();
    renderPingTargets();
  } catch (err) {
    console.error("loadPingTargets failed", err);
  }
}

document.getElementById("pg-add-btn").addEventListener("click", async () => {
  const address = document.getElementById("pg-new-address").value.trim();
  if (!address) {
    setResult("pg-result", false, "Unesi IP adresu ili hostname.");
    return;
  }
  const label = document.getElementById("pg-new-label").value.trim();
  const btn = document.getElementById("pg-add-btn");
  btn.disabled = true;
  try {
    await Api.createPingTarget({ address, label: label || null });
    document.getElementById("pg-new-address").value = "";
    document.getElementById("pg-new-label").value = "";
    loadPingTargets();
  } catch (err) {
    console.error("createPingTarget failed", err);
    setResult("pg-result", false, "Greška pri dodavanju destinacije.");
  } finally {
    btn.disabled = false;
  }
});

const SUBTAB_PANELS = ["scanner", "ping", "history", "mqtt", "smtp", "webhook", "omada", "appearance", "backup", "reset"];

// Quiet hours only applies to MQTT/SMTP -- shown directly below whichever of those
// two panels is active (not pinned at the top), by physically re-parenting the
// single panel node right after the active settings-row each time.
function repositionQuietHours(subtabName) {
  const qh = document.getElementById("panel-quiet-hours");
  const showQuietHoursOn = ["mqtt", "smtp"];
  if (!showQuietHoursOn.includes(subtabName)) {
    qh.style.display = "none";
    return;
  }
  const targetPanel = document.getElementById(`panel-${subtabName}`);
  if (targetPanel && targetPanel.nextElementSibling !== qh) {
    targetPanel.insertAdjacentElement("afterend", qh);
  }
  qh.style.display = "";
}

document.querySelectorAll(".tab[data-subtab]").forEach((tabEl) => {
  tabEl.addEventListener("click", () => {
    document.querySelectorAll(".tab[data-subtab]").forEach((t) => t.classList.remove("active"));
    tabEl.classList.add("active");
    SUBTAB_PANELS.forEach((name) => {
      const panel = document.getElementById(`panel-${name}`);
      if (panel) panel.style.display = tabEl.dataset.subtab === name ? "" : "none";
    });

    repositionQuietHours(tabEl.dataset.subtab);

    // leaving Appearance without saving reverts the live preview back to the saved values
    if (tabEl.dataset.subtab !== "appearance" && savedAppearance && window.NWTheme) {
      window.NWTheme.apply(savedAppearance);
    }
  });
});

// initial visibility on page load (default active sub-tab is Scanner, which doesn't show it)
{
  const initialTab = document.querySelector(".tab[data-subtab].active");
  repositionQuietHours(initialTab ? initialTab.dataset.subtab : null);
}

loadScannerSettings();
loadScanDetectionSettings();
loadHistorySettings();
loadPingSettings();
loadPingTargets();
loadMqttSettings();
loadSmtpSettings();
loadWebhookSettings();
loadOmadaSettings();
loadAppearanceSettings();
loadQuietHours();
