// The datetime-local input is replaced by the Serbian picker (common.js).
const picker = () => document.getElementById("tm-datetime")._dtp;
const tableState = { sort: "online", order: "desc" };
let lastDevices = [];

async function loadBounds() {
  try {
    const bounds = await Api.getTimeMachineBounds();
    if (bounds.earliest) picker().setMin(new Date(bounds.earliest));
    picker().setMax(new Date(bounds.latest));
    picker().setValue(new Date(bounds.latest), { silent: true });

    const note = document.getElementById("tm-bounds-note");
    note.textContent = bounds.earliest
      ? `Dostupna istorija od ${fmtDateTime(bounds.earliest)} do sada.`
      : "Još nema evidentiranih uređaja.";
  } catch (err) {
    console.error("loadBounds failed", err);
  }
}

function renderDeviceRow(d) {
  const cls = d.online ? "ok" : "bad";
  const label = d.online ? "ONLINE" : "OFFLINE";
  return `
    <tr>
      <td><span class="status-badge ${cls}">${label}</span></td>
      <td style="font-family:monospace">${escapeHtml(d.mac_address)}</td>
      <td>${escapeHtml(d.ip_address) || "-"}</td>
      <td>${escapeHtml(d.hostname) || "nepoznat"}</td>
      <td>${escapeHtml(d.vendor) || "nepoznat"}</td>
      <td>${escapeHtml(d.custom_name) || "-"}</td>
      <td>${fmtDateTime(d.status_changed_at)}</td>
    </tr>`;
}

function renderMacList(elId, macs) {
  const el = document.getElementById(elId);
  if (!macs.length) {
    el.innerHTML = '<div class="empty">Nema promena</div>';
    return;
  }
  el.innerHTML = macs
    .map(
      (mac) => `
      <div class="event-row">
        <span class="event-badge info">MAC</span>
        <div class="event-body"><div style="font-family:monospace">${escapeHtml(mac)}</div></div>
      </div>`
    )
    .join("");
}

function renderDeviceTable() {
  const tbody = document.getElementById("tm-table-body");
  const rows = sortRows(lastDevices, tableState.sort, tableState.order);
  tbody.innerHTML = rows.length
    ? rows.map(renderDeviceRow).join("")
    : '<tr><td colspan="7" style="text-align:center;color:var(--text-faint);padding:24px">Još nije bilo uređaja u tom trenutku</td></tr>';
}

async function showState() {
  const when = picker().getValue();
  if (!when) return;

  const btn = document.getElementById("tm-go");
  btn.disabled = true;
  btn.textContent = "Učitavanje...";
  try {
    const at = when.toISOString();
    const data = await Api.getTimeMachineState(at);

    document.getElementById("tm-empty").style.display = "none";
    document.getElementById("tm-results").style.display = "";

    document.getElementById("tm-online").textContent = data.online_count;
    document.getElementById("tm-offline").textContent = data.offline_count;
    document.getElementById("tm-appeared").textContent = data.appeared_since.length;
    document.getElementById("tm-disappeared").textContent = data.disappeared_since.length;

    const hasDiff = data.appeared_since.length > 0 || data.disappeared_since.length > 0;
    document.getElementById("tm-diff-panels").style.display = hasDiff ? "" : "none";
    renderMacList("tm-appeared-list", data.appeared_since);
    renderMacList("tm-disappeared-list", data.disappeared_since);

    lastDevices = data.devices;
    renderDeviceTable();
  } catch (err) {
    console.error("showState failed", err);
    alert("Greška pri učitavanju stanja mreže.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Prikaži";
  }
}

function applyPreset(offsetMs) {
  picker().setValue(new Date(Date.now() - offsetMs), { silent: true });
}

bindSortableHeaders(document.getElementById("tm-head-row"), tableState, renderDeviceTable);

document.getElementById("tm-go").addEventListener("click", showState);
document.getElementById("tm-preset-now").addEventListener("click", () => applyPreset(0));
document.getElementById("tm-preset-1h").addEventListener("click", () => applyPreset(60 * 60 * 1000));
document.getElementById("tm-preset-24h").addEventListener("click", () => applyPreset(24 * 60 * 60 * 1000));
document.getElementById("tm-preset-7d").addEventListener("click", () => applyPreset(7 * 24 * 60 * 60 * 1000));

loadBounds();
