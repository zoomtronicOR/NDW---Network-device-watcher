// Sistem -> "Poslata obaveštenja": notification_log (SMTP / MQTT / webhook),
// including skipped notifications and why (quiet hours, trusted device).

const NF_STATUS_META = {
  SUCCESS: { label: "POSLATO", cls: "ok" },
  FAILED: { label: "NEUSPEŠNO", cls: "bad" },
  SKIPPED: { label: "PRESKOČENO", cls: "info" },
};
const NF_CHANNEL_LABEL = { MQTT: "MQTT", WEBHOOK: "Webhook", SMTP: "E-mail" };
const NF_DEFAULT_SORT = { sort: "timestamp", order: "desc" };

const nfState = {
  page: 1,
  pageSize: 50,
  search: "",
  channel: "",
  status: "",
  eventType: "",
  total: 0,
  ...NF_DEFAULT_SORT,
};
let nfSearchDebounce = null;
let nfLoadedOnce = false;

function nfFiltersActive() {
  return (
    !!nfState.search ||
    !!nfState.channel ||
    !!nfState.status ||
    !!nfState.eventType ||
    nfState.sort !== NF_DEFAULT_SORT.sort ||
    nfState.order !== NF_DEFAULT_SORT.order
  );
}

function renderNotifications(data) {
  const body = document.getElementById("nf-body");
  const s = data.summary || {};
  document.getElementById("notif-summary").innerHTML = `
    <span class="event-badge ok">${s.SUCCESS || 0} poslato</span>
    <span class="event-badge bad">${s.FAILED || 0} neuspešno</span>
    <span class="event-badge info">${s.SKIPPED || 0} preskočeno</span>
    <span class="notif-summary-note">ukupno u evidenciji (čuva se prema Podešavanja &rarr; Istorija)</span>`;

  if (!data.items.length) {
    body.innerHTML =
      '<tr><td colspan="7" style="text-align:center;color:var(--text-faint);padding:24px">Nema obaveštenja koja odgovaraju filteru</td></tr>';
    return;
  }
  body.innerHTML = data.items
    .map((n) => {
      const st = NF_STATUS_META[n.status] || { label: n.status, cls: "info" };
      const ev = EVENT_META[n.event_type] || { label: n.event_type || "-", cls: "info" };
      const device = n.device_mac
        ? `<span class="mono">${escapeHtml(n.device_mac)}</span>${n.device_name ? ` <span style="color:var(--text-faint)">(${escapeHtml(n.device_name)})</span>` : ""}`
        : '<span style="color:var(--text-faint)">-</span>';
      return `
        <tr ${n.device_id ? `data-device-id="${n.device_id}"` : ""}>
          <td>${fmtDateTime(n.timestamp)}</td>
          <td>${escapeHtml(NF_CHANNEL_LABEL[n.channel] || n.channel)}</td>
          <td>${n.event_type ? `<span class="event-badge ${ev.cls}">${escapeHtml(ev.label)}</span>` : "-"}</td>
          <td>${device}</td>
          <td class="notes-cell mono" title="${escapeHtml(n.destination)}">${escapeHtml(n.destination)}</td>
          <td><span class="event-badge ${st.cls}">${st.label}</span></td>
          <td class="notes-cell" title="${escapeHtml(n.error || "")}">${escapeHtml(n.error) || ""}</td>
        </tr>`;
    })
    .join("");
  body.querySelectorAll("tr[data-device-id]").forEach((row) =>
    row.addEventListener("click", () => {
      window.location.href = `/devices.html?device=${row.dataset.deviceId}`;
    })
  );
}

async function loadNotifications() {
  document.getElementById("nf-reset-btn").disabled = !nfFiltersActive();
  const params = { page: nfState.page, page_size: nfState.pageSize, sort: nfState.sort, order: nfState.order };
  if (nfState.search) params.search = nfState.search;
  if (nfState.channel) params.channel = nfState.channel;
  if (nfState.status) params.status = nfState.status;
  if (nfState.eventType) params.event_type = nfState.eventType;
  try {
    const data = await Api.listNotifications(params);
    nfState.total = data.total;
    renderNotifications(data);
    const totalPages = Math.max(1, Math.ceil(nfState.total / nfState.pageSize));
    document.getElementById("nf-page-info").textContent = `Strana ${nfState.page} od ${totalPages} (${nfState.total} zapisa)`;
    document.getElementById("nf-prev").disabled = nfState.page <= 1;
    document.getElementById("nf-next").disabled = nfState.page >= totalPages;
    nfLoadedOnce = true;
  } catch (err) {
    console.error("loadNotifications failed", err);
    document.getElementById("nf-body").innerHTML =
      '<tr><td colspan="7" style="text-align:center;color:var(--bad);padding:24px">Greška pri učitavanju obaveštenja</td></tr>';
  }
}

function nfReset() {
  Object.assign(nfState, { search: "", channel: "", status: "", eventType: "", page: 1, ...NF_DEFAULT_SORT });
  document.getElementById("nf-search").value = "";
  document.getElementById("nf-channel").value = "";
  document.getElementById("nf-status").value = "";
  document.getElementById("nf-type").value = "";
  updateSortIndicators(document.getElementById("nf-head-row"), nfState);
  loadNotifications();
}

function setSystemView(view) {
  Prefs.set("nw_system_view", view);
  document.querySelectorAll("#system-view-toggle .view-toggle-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.getElementById("view-logs").hidden = view !== "logs";
  document.getElementById("view-notif").hidden = view !== "notif";
  if (view === "notif" && !nfLoadedOnce) loadNotifications();
}

(function initNotifications() {
  const typeSel = document.getElementById("nf-type");
  typeSel.innerHTML =
    '<option value="">Svi događaji</option>' +
    ["NEW_DEVICE", "DEVICE_OFFLINE", "DEVICE_RETURNED", "SCAN_DETECTED", "IP_CONFLICT", "VENDOR_MISMATCH", "ANOMALY_BURST_NEW_DEVICES"]
      .map((k) => `<option value="${k}">${(EVENT_META[k] || { label: k }).label}</option>`)
      .join("");

  const onFilter = (key) => (e) => {
    nfState[key] = e.target.value;
    nfState.page = 1;
    loadNotifications();
  };
  document.getElementById("nf-channel").addEventListener("change", onFilter("channel"));
  document.getElementById("nf-status").addEventListener("change", onFilter("status"));
  document.getElementById("nf-type").addEventListener("change", onFilter("eventType"));
  document.getElementById("nf-search").addEventListener("input", (e) => {
    clearTimeout(nfSearchDebounce);
    nfSearchDebounce = setTimeout(() => {
      nfState.search = e.target.value.trim();
      nfState.page = 1;
      loadNotifications();
    }, 300);
  });
  document.getElementById("nf-page-size").addEventListener("change", (e) => {
    nfState.pageSize = Number(e.target.value);
    nfState.page = 1;
    loadNotifications();
  });
  document.getElementById("nf-prev").addEventListener("click", () => {
    if (nfState.page > 1) {
      nfState.page -= 1;
      loadNotifications();
    }
  });
  document.getElementById("nf-next").addEventListener("click", () => {
    nfState.page += 1;
    loadNotifications();
  });
  document.getElementById("nf-reset-btn").addEventListener("click", nfReset);
  bindSortableHeaders(document.getElementById("nf-head-row"), nfState, () => {
    nfState.page = 1;
    loadNotifications();
  });

  document.querySelectorAll("#system-view-toggle .view-toggle-btn").forEach((b) =>
    b.addEventListener("click", () => setSystemView(b.dataset.view))
  );
  setSystemView(Prefs.get("nw_system_view", "logs") === "notif" ? "notif" : "logs");
  setInterval(() => {
    if (!document.getElementById("view-notif").hidden) loadNotifications();
  }, 15000);
})();
