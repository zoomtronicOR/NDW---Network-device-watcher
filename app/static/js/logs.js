const LEVEL_META = {
  DEBUG: { cls: "info" },
  INFO: { cls: "ok" },
  WARNING: { cls: "warn" },
  ERROR: { cls: "bad" },
};

const state = {
  page: 1,
  pageSize: 100,
  search: "",
  level: "",
  source: "all",
  start: "",
  total: 0,
  sort: "timestamp",
  order: "desc",
};

const DEFAULT_SORT = { sort: "timestamp", order: "desc" };

function filtersActive() {
  return (
    !!state.search ||
    !!state.level ||
    state.source !== "all" ||
    !!state.start ||
    state.sort !== DEFAULT_SORT.sort ||
    state.order !== DEFAULT_SORT.order
  );
}

function resetFilters() {
  Object.assign(state, { search: "", level: "", source: "all", start: "", page: 1, ...DEFAULT_SORT });
  document.getElementById("search-input").value = "";
  document.getElementById("level-filter").value = "";
  document.getElementById("source-filter").value = "all";
  const start = document.getElementById("start-filter");
  if (start._dtp) start._dtp.setValue(null, { silent: true });
  else start.value = "";
  updateSortIndicators(headRow(), state);
  loadLogs();
}

function headRow() {
  return document.querySelector("table.device-table thead tr");
}

let searchDebounce = null;

function renderTable(items) {
  const tbody = document.getElementById("table-body");
  if (items.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="4" style="text-align:center;color:var(--text-faint);padding:24px">Nema logova koji odgovaraju filteru</td></tr>';
    return;
  }

  tbody.innerHTML = items
    .map((e) => {
      const meta = LEVEL_META[e.level] || { cls: "info" };
      return `
        <tr>
          <td style="white-space:nowrap">${fmtDateTime(e.timestamp)}</td>
          <td><span class="event-badge ${meta.cls}">${e.level}</span></td>
          <td>${escapeHtml(e.source)}</td>
          <td style="white-space:pre-wrap;word-break:break-word;font-family:'Cascadia Code',Consolas,monospace;font-size:11.5px">${escapeHtml(e.message)}</td>
        </tr>`;
    })
    .join("");
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
  document.getElementById("page-info").textContent = `Strana ${state.page} od ${totalPages} (${state.total} zapisa)`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= totalPages;
}

function currentParams() {
  const params = { page: state.page, page_size: state.pageSize, source: state.source, sort: state.sort, order: state.order };
  if (state.search) params.search = state.search;
  if (state.level) params.level = state.level;
  if (state.start) params.since = new Date(state.start).toISOString();
  return params;
}

function updateDownloadLink() {
  const params = currentParams();
  delete params.page;
  delete params.page_size;
  delete params.sort;
  delete params.order;
  document.getElementById("download-btn").href = `/api/logs/download?${new URLSearchParams(params).toString()}`;
}

async function loadLogs() {
  document.getElementById("reset-filters-btn").disabled = !filtersActive();
  try {
    const data = await Api.listLogs(currentParams());
    state.total = data.total;
    renderTable(data.items);
    renderPagination();
    updateDownloadLink();
  } catch (err) {
    console.error("loadLogs failed", err);
    document.getElementById("table-body").innerHTML =
      '<tr><td colspan="4" style="text-align:center;color:var(--bad);padding:24px">Greška pri učitavanju logova</td></tr>';
  }
}

document.getElementById("search-input").addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.search = e.target.value.trim();
    state.page = 1;
    loadLogs();
  }, 300);
});

document.getElementById("level-filter").addEventListener("change", (e) => {
  state.level = e.target.value;
  state.page = 1;
  loadLogs();
});

document.getElementById("source-filter").addEventListener("change", (e) => {
  state.source = e.target.value;
  state.page = 1;
  loadLogs();
});

document.getElementById("start-filter").addEventListener("change", (e) => {
  state.start = e.target.value;
  state.page = 1;
  loadLogs();
});

document.getElementById("page-size").addEventListener("change", (e) => {
  state.pageSize = Number(e.target.value);
  state.page = 1;
  loadLogs();
});

document.getElementById("prev-page").addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadLogs();
  }
});
document.getElementById("next-page").addEventListener("click", () => {
  state.page += 1;
  loadLogs();
});

bindSortableHeaders(headRow(), state, () => {
  state.page = 1;
  loadLogs();
});
document.getElementById("reset-filters-btn").addEventListener("click", resetFilters);

loadLogs();
setInterval(loadLogs, 15000);
