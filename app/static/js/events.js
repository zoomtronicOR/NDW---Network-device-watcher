const state = {
  page: 1,
  pageSize: 50,
  search: "",
  eventType: "",
  start: "",
  end: "",
  total: 0,
  sort: "timestamp",
  order: "desc",
};

const DEFAULT_SORT = { sort: "timestamp", order: "desc" };

let searchDebounce = null;

function populateEventTypeFilter() {
  const select = document.getElementById("type-filter");
  select.innerHTML =
    '<option value="">Svi tipovi</option>' +
    Object.entries(EVENT_META)
      .map(([key, meta]) => `<option value="${key}">${meta.label}</option>`)
      .join("");
}

// Details formatting is shared with the Dashboard feed (common.js).
const formatDetails = formatEventDetails;

function filtersActive() {
  return (
    !!state.search ||
    !!state.eventType ||
    !!state.start ||
    !!state.end ||
    state.sort !== DEFAULT_SORT.sort ||
    state.order !== DEFAULT_SORT.order
  );
}

function updateResetButton() {
  document.getElementById("reset-filters-btn").disabled = !filtersActive();
}

function resetFilters() {
  Object.assign(state, { search: "", eventType: "", start: "", end: "", page: 1, ...DEFAULT_SORT });
  document.getElementById("search-input").value = "";
  document.getElementById("type-filter").value = "";
  ["start-filter", "end-filter"].forEach((id) => {
    const el = document.getElementById(id);
    if (el._dtp) el._dtp.setValue(null, { silent: true });
    else el.value = "";
  });
  updateSortIndicators(document.getElementById("events-head-row"), state);
  loadEvents();
}

function renderTable(items) {
  const tbody = document.getElementById("table-body");
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-faint);padding:24px">Nema događaja koji odgovaraju filteru</td></tr>';
    return;
  }

  tbody.innerHTML = items
    .map((e) => {
      const meta = EVENT_META[e.event_type] || { label: e.event_type, cls: "info" };
      const deviceLabel = e.device_mac
        ? `<span style="font-family:monospace">${escapeHtml(e.device_mac)}</span>${e.device_name ? ` <span style="color:var(--text-faint)">(${escapeHtml(e.device_name)})</span>` : ""}`
        : `<span style="color:var(--text-faint)">#${e.device_id}</span>`;
      return `
        <tr data-device-id="${e.device_id}">
          <td>${fmtDateTime(e.timestamp)}</td>
          <td><span class="event-badge ${meta.cls}">${meta.label}</span></td>
          <td>${deviceLabel}</td>
          <td>${escapeHtml(e.device_vendor) || "-"}</td>
          <td>${escapeHtml(e.ip_address) || "-"}</td>
          <td class="notes-cell">${formatDetails(e)}</td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr[data-device-id]").forEach((row) => {
    row.addEventListener("click", () => {
      window.location.href = `/devices.html?device=${row.dataset.deviceId}`;
    });
  });
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
  document.getElementById("page-info").textContent = `Strana ${state.page} od ${totalPages} (${state.total} događaja)`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= totalPages;
}

async function loadEvents() {
  updateResetButton();
  const params = { page: state.page, page_size: state.pageSize, sort: state.sort, order: state.order };
  if (state.search) params.search = state.search;
  if (state.eventType) params.event_type = state.eventType;
  if (state.start) params.start = new Date(state.start).toISOString();
  if (state.end) params.end = new Date(state.end).toISOString();

  try {
    const data = await Api.listEvents(params);
    state.total = data.total;
    renderTable(data.items);
    renderPagination();
  } catch (err) {
    console.error("loadEvents failed", err);
    document.getElementById("table-body").innerHTML =
      '<tr><td colspan="6" style="text-align:center;color:var(--bad);padding:24px">Greška pri učitavanju događaja</td></tr>';
  }
}

function initToolbar() {
  bindSortableHeaders(document.getElementById("events-head-row"), state, () => {
    state.page = 1;
    loadEvents();
  });
  document.getElementById("reset-filters-btn").addEventListener("click", resetFilters);

  document.getElementById("search-input").addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.search = e.target.value.trim();
      state.page = 1;
      loadEvents();
    }, 300);
  });

  document.getElementById("type-filter").addEventListener("change", (e) => {
    state.eventType = e.target.value;
    state.page = 1;
    loadEvents();
  });

  document.getElementById("start-filter").addEventListener("change", (e) => {
    state.start = e.target.value;
    state.page = 1;
    loadEvents();
  });

  document.getElementById("end-filter").addEventListener("change", (e) => {
    state.end = e.target.value;
    state.page = 1;
    loadEvents();
  });

  document.getElementById("page-size").addEventListener("change", (e) => {
    state.pageSize = Number(e.target.value);
    state.page = 1;
    loadEvents();
  });

  document.getElementById("prev-page").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadEvents();
    }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    state.page += 1;
    loadEvents();
  });
}

populateEventTypeFilter();
initToolbar();
// Deep link from the dashboard stat cards, e.g. /events.html?type=IP_CONFLICT
(function applyUrlFilter() {
  const type = new URLSearchParams(window.location.search).get("type");
  if (type && EVENT_META[type]) {
    state.eventType = type;
    document.getElementById("type-filter").value = type;
  }
})();
loadEvents();
setInterval(loadEvents, 15000);
window.addEventListener("nw:refresh", loadEvents);
