const Charts = {
  palette: ["#22d3ee", "#818cf8", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#38bdf8", "#fb923c"],

  // Selectable palettes for donut / bar-list cards (per-viewer choice, see dashboard.js).
  palettes: {
    default: { label: "Podrazumevana", colors: ["#22d3ee", "#818cf8", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#38bdf8", "#fb923c"] },
    ocean: { label: "Okean", colors: ["#0ea5e9", "#22d3ee", "#2dd4bf", "#38bdf8", "#6366f1", "#14b8a6", "#7dd3fc", "#a5b4fc"] },
    warm: { label: "Topla", colors: ["#f97316", "#fbbf24", "#f87171", "#fb7185", "#facc15", "#f59e0b", "#ef4444", "#fdba74"] },
    forest: { label: "Šuma", colors: ["#22c55e", "#84cc16", "#10b981", "#a3e635", "#14b8a6", "#65a30d", "#4ade80", "#bef264"] },
    pastel: { label: "Pastelna", colors: ["#a5f3fc", "#c7d2fe", "#bbf7d0", "#fde68a", "#fecaca", "#ddd6fe", "#bae6fd", "#fed7aa"] },
    vivid: { label: "Kontrastna", colors: ["#e11d48", "#2563eb", "#16a34a", "#f59e0b", "#9333ea", "#0891b2", "#ea580c", "#4f46e5"] },
  },

  // Single-series color choices offered in the ⋮ menu.
  swatches: ["#22d3ee", "#818cf8", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#38bdf8", "#fb923c", "#f472b6", "#e5e7eb"],

  svg(tag, attrs) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    return el;
  },

  text(x, y, content, attrs = {}) {
    const t = this.svg("text", { x, y, class: "chart-axis-label", ...attrs });
    t.textContent = content;
    return t;
  },

  clear(container) {
    container.innerHTML = "";
  },

  // ---------- axis helpers ----------

  // "Nice" linear ticks: steps of 1/2/5 x 10^n, integer-only when asked
  // (device counts), always starting at 0 and ending at or above `max`.
  linearTicks(max, { target = 4, integer = false } = {}) {
    if (!(max > 0)) max = integer ? 1 : 1;
    const raw = max / target;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    let step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    if (integer) step = Math.max(1, Math.ceil(step));
    const top = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = 0; v <= top + step / 1000; v += step) ticks.push(+v.toFixed(6));
    return { ticks, top: top || step };
  },

  // Time ticks aligned to local wall-clock boundaries (whole hours, midnight...).
  timeTicks(t0, t1, target = 6) {
    const MIN = 60e3;
    const H = 60 * MIN;
    const D = 24 * H;
    const steps = [MIN, 5 * MIN, 10 * MIN, 15 * MIN, 30 * MIN, H, 2 * H, 3 * H, 6 * H, 12 * H, D, 2 * D, 7 * D, 14 * D, 30 * D];
    const span = t1 - t0;
    const step = steps.find((s) => span / s <= target) || steps[steps.length - 1];

    const start = new Date(t0);
    if (step >= D) {
      start.setHours(0, 0, 0, 0);
    } else if (step >= H) {
      start.setMinutes(0, 0, 0);
      start.setHours(Math.floor(start.getHours() / (step / H)) * (step / H));
    } else {
      start.setSeconds(0, 0);
      start.setMinutes(Math.floor(start.getMinutes() / (step / MIN)) * (step / MIN));
    }
    const ticks = [];
    const cur = new Date(start);
    while (cur.getTime() <= t1) {
      if (cur.getTime() >= t0) ticks.push(cur.getTime());
      if (step >= D) cur.setDate(cur.getDate() + step / D);
      else cur.setTime(cur.getTime() + step);
      if (ticks.length > 60) break;
    }
    return { ticks, step };
  },

  fmtTimeTick(ms, step) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    const dayLabel = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`;
    if (step >= 24 * 3600e3) return dayLabel;
    const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    return d.getHours() === 0 && d.getMinutes() === 0 ? dayLabel : hm;
  },

  fmtFull(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}. ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },

  fmtNumber(v) {
    if (Math.abs(v) >= 1000) return `${+(v / 1000).toFixed(1)}k`;
    return Number.isInteger(v) ? String(v) : String(+v.toFixed(2));
  },

  // Draws gridlines + Y labels + optional unit caption. Returns padL used.
  drawYAxis(svgEl, ticks, top, { width, height, padT, padB, padR, unit }) {
    const labels = ticks.map((v) => this.fmtNumber(v));
    const longest = Math.max(...labels.map((l) => l.length), unit ? unit.length - 1 : 0);
    const padL = 14 + longest * 6.2;
    const plotH = height - padT - padB;
    ticks.forEach((v, i) => {
      const y = height - padB - (v / top) * plotH;
      svgEl.appendChild(
        this.svg("line", { x1: padL, x2: width - padR, y1: y, y2: y, class: i === 0 ? "chart-axis-line" : "chart-grid" })
      );
      svgEl.appendChild(this.text(padL - 6, y + 3.5, labels[i], { "text-anchor": "end" }));
    });
    if (unit) svgEl.appendChild(this.text(4, padT - 12, unit, { "text-anchor": "start", class: "chart-axis-label chart-axis-unit" }));
    return padL;
  },

  drawTimeXAxis(svgEl, t0, t1, sx, { height, padB, padL, width, padR }) {
    const plotW = width - padL - padR;
    const { ticks, step } = this.timeTicks(t0, t1, Math.max(3, Math.floor(plotW / 85)));
    ticks.forEach((t) => {
      const x = sx(t);
      svgEl.appendChild(this.svg("line", { x1: x, x2: x, y1: height - padB, y2: height - padB + 4, class: "chart-axis-line" }));
      const anchor = x - padL < 18 ? "start" : width - padR - x < 18 ? "end" : "middle";
      svgEl.appendChild(this.text(x, height - padB + 15, this.fmtTimeTick(t, step), { "text-anchor": anchor }));
    });
  },

  gradient(svgEl, color, top = 0.35, bottom = 0.02) {
    const gradId = `grad-${Math.random().toString(36).slice(2)}`;
    const defs = this.svg("defs", {});
    const grad = this.svg("linearGradient", { id: gradId, x1: 0, y1: 0, x2: 0, y2: 1 });
    grad.appendChild(this.svg("stop", { offset: "0%", "stop-color": color, "stop-opacity": top }));
    grad.appendChild(this.svg("stop", { offset: "100%", "stop-color": color, "stop-opacity": bottom }));
    defs.appendChild(grad);
    svgEl.appendChild(defs);
    return gradId;
  },

  attachHover(container, svgEl, { width, padT, padB, height, xs, onIndex }) {
    const hoverLine = this.svg("line", {
      x1: 0, y1: padT, x2: 0, y2: height - padB,
      class: "chart-hover-line", opacity: 0, "pointer-events": "none",
    });
    const hoverDot = this.svg("circle", { r: 4, "stroke-width": 1.5, class: "chart-hover-dot", opacity: 0, "pointer-events": "none" });
    svgEl.appendChild(hoverLine);
    svgEl.appendChild(hoverDot);
    const overlay = this.svg("rect", { x: 0, y: 0, width, height, fill: "transparent" });
    overlay.style.cursor = "crosshair";
    svgEl.appendChild(overlay);

    container.style.position = "relative";
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    container.appendChild(tooltip);

    const nearest = (clientX) => {
      const rect = svgEl.getBoundingClientRect();
      const vx = ((clientX - rect.left) / rect.width) * width;
      let best = 0;
      let bestDist = Infinity;
      xs.forEach((x, i) => {
        const d = Math.abs(x - vx);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      });
      return best;
    };
    overlay.addEventListener("mousemove", (evt) => {
      const i = nearest(evt.clientX);
      const r = onIndex(i);
      if (!r) return;
      hoverLine.setAttribute("x1", r.x);
      hoverLine.setAttribute("x2", r.x);
      hoverLine.setAttribute("opacity", 1);
      hoverDot.setAttribute("cx", r.x);
      hoverDot.setAttribute("cy", r.y);
      hoverDot.setAttribute("fill", r.color);
      hoverDot.setAttribute("opacity", 1);
      tooltip.innerHTML = r.html;
      tooltip.style.display = "block";
      const leftPct = (r.x / width) * 100;
      tooltip.classList.toggle("ct-align-right", leftPct > 60);
      tooltip.classList.toggle("ct-align-left", leftPct < 15);
      tooltip.style.left = `${leftPct}%`;
    });
    overlay.addEventListener("mouseleave", () => {
      hoverLine.setAttribute("opacity", 0);
      hoverDot.setAttribute("opacity", 0);
      tooltip.style.display = "none";
    });
  },

  viewHeight(container, height, width, fixedPixelHeight) {
    if (!fixedPixelHeight) return height;
    // Keep uniform X/Y scaling (no preserveAspectRatio="none" -- that squashed
    // the axis text) while landing on the requested on-screen pixel height.
    const containerWidth = container.getBoundingClientRect().width || width;
    return (height * width) / containerWidth;
  },

  // ---------- unified series chart (dashboard) ----------

  // `mode` ('area' | 'line' | 'bar') is the switchable display theme; `xType`
  // ('time' | 'category') picks continuous-time vs. one-slot-per-day layout.
  // For time series, `xDomain` [startIso, endIso] pins the axis to the
  // selected range even when the data starts later.
  seriesChart(container, points, {
    mode = "area",
    xType = "time",
    color = "#22d3ee",
    valueKey = "online",
    labelKey = "date",
    label = "",
    unit = "",
    height = 200,
    fixedPixelHeight = false,
    xDomain = null,
  } = {}) {
    this.clear(container);
    const minPoints = xType === "time" ? 2 : 1;
    if (!points || points.length < minPoints) {
      container.innerHTML = '<div class="empty">Nema dovoljno podataka</div>';
      return;
    }

    const width = 640;
    const padR = 12;
    const padT = unit ? 26 : 14;
    const padB = 24;
    height = this.viewHeight(container, height, width, fixedPixelHeight);

    const ys = points.map((p) => p[valueKey]);
    const { ticks, top } = this.linearTicks(Math.max(...ys, 1), { target: height < 150 ? 3 : 4, integer: true });

    const svgEl = this.svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart-svg" });
    svgEl.style.width = "100%";
    svgEl.style.height = "auto";
    const gradId = this.gradient(svgEl, color);

    const padL = this.drawYAxis(svgEl, ticks, top, { width, height, padT, padB, padR, unit });
    const plotW = width - padL - padR;
    const sy = (y) => height - padB - (y / top) * (height - padT - padB);

    let sxi;
    let xsTime = null;
    if (xType === "time") {
      xsTime = points.map((p) => new Date(p.timestamp).getTime());
      const t0 = xDomain ? new Date(xDomain[0]).getTime() : Math.min(...xsTime);
      const t1 = xDomain ? new Date(xDomain[1]).getTime() : Math.max(...xsTime);
      const sxt = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * plotW;
      sxi = (i) => sxt(xsTime[i]);
      this.drawTimeXAxis(svgEl, t0, t1, sxt, { height, padB, padL, width, padR });
    } else {
      const slot = plotW / points.length;
      sxi = (i) => padL + i * slot + slot / 2;
      const maxLabels = Math.max(3, Math.floor(plotW / 48));
      const showEvery = Math.ceil(points.length / maxLabels);
      points.forEach((p, i) => {
        if ((points.length - 1 - i) % showEvery !== 0) return;
        const raw = p[labelKey] || "";
        const parts = raw.split("-");
        const lbl = parts.length === 3 ? `${parts[2]}.${parts[1]}.` : raw;
        svgEl.appendChild(this.text(sxi(i), height - padB + 15, lbl, { "text-anchor": "middle" }));
      });
    }

    if (mode === "bar") {
      const slotW = xType === "time" ? plotW / Math.max(points.length, 1) : plotW / points.length;
      const barW = Math.max(2, Math.min(26, slotW * 0.62));
      points.forEach((p, i) => {
        const h = ((height - padT - padB) * ys[i]) / top;
        if (h <= 0) return;
        svgEl.appendChild(
          this.svg("rect", { x: sxi(i) - barW / 2, y: height - padB - h, width: barW, height: Math.max(h, 1), fill: color, rx: 2 })
        );
      });
    } else {
      let linePath = `M ${sxi(0)} ${sy(ys[0])}`;
      for (let i = 1; i < points.length; i++) {
        linePath += xType === "time" ? ` L ${sxi(i)} ${sy(ys[i - 1])} L ${sxi(i)} ${sy(ys[i])}` : ` L ${sxi(i)} ${sy(ys[i])}`;
      }
      if (mode === "area") {
        const areaPath = `${linePath} L ${sxi(points.length - 1)} ${height - padB} L ${sxi(0)} ${height - padB} Z`;
        svgEl.appendChild(this.svg("path", { d: areaPath, fill: `url(#${gradId})`, stroke: "none" }));
      }
      svgEl.appendChild(this.svg("path", { d: linePath, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round" }));
      if (xType === "category" && points.length <= 45) {
        points.forEach((p, i) => svgEl.appendChild(this.svg("circle", { cx: sxi(i), cy: sy(ys[i]), r: 2.5, fill: color })));
      }
    }

    const valLabel = label || valueKey;
    this.attachHover(container, svgEl, {
      width, padT, padB, height,
      xs: points.map((_, i) => sxi(i)),
      onIndex: (i) => {
        const timeLabel = xType === "time" ? this.fmtFull(xsTime[i]) : (() => {
          const parts = (points[i][labelKey] || "").split("-");
          return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}.` : points[i][labelKey];
        })();
        return {
          x: sxi(i),
          y: sy(ys[i]),
          color,
          html: `<div class="ct-val">${ys[i]} ${escapeHtml(valLabel)}</div><div class="ct-time">${escapeHtml(timeLabel)}</div>`,
        };
      },
    });

    container.appendChild(svgEl);
  },

  // ---------- donut / bar list ----------

  donut(container, items, { size = 150, thickness = 22, colors = null } = {}) {
    const palette = colors || this.palette;
    this.clear(container);
    const total = items.reduce((s, i) => s + i.count, 0);
    if (!items.length || total === 0) {
      container.innerHTML = '<div class="empty">Nema podataka</div>';
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "donut-wrap";

    const r = (size - thickness) / 2;
    const cx = size / 2;
    const cy = size / 2;
    const circumference = 2 * Math.PI * r;

    const svgEl = this.svg("svg", { viewBox: `0 0 ${size} ${size}`, width: size, height: size });
    svgEl.appendChild(this.svg("circle", { cx, cy, r, fill: "none", class: "chart-grid", "stroke-width": thickness }));

    const center = this.svg("text", { x: cx, y: cy + 2, "text-anchor": "middle", class: "donut-total" });
    center.textContent = total;
    const centerLbl = this.svg("text", { x: cx, y: cy + 16, "text-anchor": "middle", class: "chart-axis-label" });
    centerLbl.textContent = "ukupno";

    container.style.position = "relative";
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    container.appendChild(tooltip);

    const showTooltip = (item, frac, evt) => {
      const rect = container.getBoundingClientRect();
      const leftPct = ((evt.clientX - rect.left) / rect.width) * 100;
      tooltip.innerHTML = `<div class="ct-val">${escapeHtml(item.label)}: ${item.count}</div><div class="ct-time">${Math.round(frac * 100)}%</div>`;
      tooltip.style.display = "block";
      tooltip.classList.toggle("ct-align-right", leftPct > 60);
      tooltip.style.left = `${leftPct}%`;
    };
    const hideTooltip = () => {
      tooltip.style.display = "none";
    };

    let offset = 0;
    items.forEach((item, i) => {
      const frac = item.count / total;
      const seg = frac * circumference;
      const circle = this.svg("circle", {
        cx, cy, r,
        fill: "none",
        stroke: palette[i % palette.length],
        "stroke-width": thickness,
        "stroke-dasharray": `${seg} ${circumference - seg}`,
        "stroke-dashoffset": -offset,
        transform: `rotate(-90 ${cx} ${cy})`,
      });
      circle.style.cursor = "pointer";
      circle.addEventListener("mousemove", (evt) => showTooltip(item, frac, evt));
      circle.addEventListener("mouseleave", hideTooltip);
      svgEl.appendChild(circle);
      offset += seg;
    });
    svgEl.appendChild(center);
    svgEl.appendChild(centerLbl);

    const legend = document.createElement("div");
    legend.className = items.length > 4 ? "legend-list legend-list-2col" : "legend-list";
    items.forEach((item, i) => {
      const frac = item.count / total;
      const row = document.createElement("div");
      row.className = "legend-row";
      row.style.cursor = "pointer";
      row.innerHTML = `
        <span class="swatch" style="background:${palette[i % palette.length]}"></span>
        <span class="name">${escapeHtml(item.label)}</span>
        <span class="count">${item.count}</span>
      `;
      row.addEventListener("mousemove", (evt) => showTooltip(item, frac, evt));
      row.addEventListener("mouseleave", hideTooltip);
      legend.appendChild(row);
    });

    wrap.appendChild(svgEl);
    wrap.appendChild(legend);
    container.appendChild(wrap);
  },

  hbarList(container, items, { colors = null } = {}) {
    const palette = colors || this.palette;
    this.clear(container);
    if (!items || items.length === 0) {
      container.innerHTML = '<div class="empty">Nema podataka</div>';
      return;
    }
    const max = Math.max(...items.map((i) => i.count), 1);
    const list = document.createElement("div");
    list.className = "legend-list";
    items.forEach((item, i) => {
      const row = document.createElement("div");
      row.className = "legend-row";
      const pct = Math.round((item.count / max) * 100);
      const c = palette[i % palette.length];
      row.innerHTML = `
        <span class="swatch" style="background:${c}"></span>
        <span class="name">${escapeHtml(item.label)}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${pct}%;background:${c}"></span></span>
        <span class="count">${item.count}</span>
      `;
      list.appendChild(row);
    });
    container.appendChild(list);
  },

  // ---------- ping RTT chart (Ping tab) ----------

  // `points` are raw samples or server-side time buckets (samples /
  // unreachable_samples set). `color` paints the line (latency-band color,
  // forced red when the target is unreachable right now). Gaps where the
  // target was down are left as gaps, with red markers on the baseline.
  pingChart(container, points, { color = "#22d3ee", height = 150, xDomain = null } = {}) {
    this.clear(container);
    const ok = points.filter((p) => p.reachable && p.rtt_avg != null);
    if (points.length < 2 || ok.length === 0) {
      container.innerHTML = '<div class="empty">Nema dovoljno podataka za izabrani period</div>';
      return;
    }

    const width = 420;
    const padR = 8;
    const padT = 24;
    const padB = 22;

    // Robust Y scale: one 4000 ms spike used to flatten everything else into
    // the baseline. If the max is far above the 95th percentile, scale to the
    // typical range and mark the clipped spikes with ▲ at the top edge.
    const rtts = ok.map((p) => p.rtt_avg).sort((a, b) => a - b);
    const rttMax = rtts[rtts.length - 1];
    const p95 = rtts[Math.floor((rtts.length - 1) * 0.95)];
    const clip = rtts.length >= 10 && p95 > 0 && rttMax > p95 * 4;
    const { ticks, top } = this.linearTicks((clip ? p95 * 3 : rttMax) * 1.1, { target: 3 });

    const svgEl = this.svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart-svg" });
    svgEl.style.width = "100%";
    svgEl.style.height = "auto";
    const gradId = this.gradient(svgEl, color, 0.4, 0.03);

    const padL = this.drawYAxis(svgEl, ticks, top, { width, height, padT, padB, padR, unit: "ms" });
    const xs = points.map((p) => new Date(p.timestamp).getTime());
    const t0 = xDomain ? new Date(xDomain[0]).getTime() : xs[0];
    const t1 = xDomain ? new Date(xDomain[1]).getTime() : xs[xs.length - 1];
    const sxt = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * (width - padL - padR);
    const sx = (i) => sxt(xs[i]);
    const sy = (v) => height - padB - (Math.min(v, top) / top) * (height - padT - padB);
    this.drawTimeXAxis(svgEl, t0, t1, sxt, { height, padB, padL, width, padR });

    // Break the line where a sample/bucket was down, or where there's a time
    // gap much larger than the typical spacing (pinger stopped, target added).
    const gaps = xs.slice(1).map((x, i) => x - xs[i]).sort((a, b) => a - b);
    const typical = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0;
    const segments = [];
    let seg = [];
    points.forEach((p, i) => {
      const up = p.reachable && p.rtt_avg != null;
      const jump = i > 0 && typical > 0 && xs[i] - xs[i - 1] > typical * 4;
      if (!up || jump) {
        if (seg.length) segments.push(seg);
        seg = [];
      }
      if (up) seg.push(i);
    });
    if (seg.length) segments.push(seg);

    segments.forEach((s) => {
      const line = s.map((i, k) => `${k ? "L" : "M"} ${sx(i)} ${sy(points[i].rtt_avg)}`).join(" ");
      const area = `${line} L ${sx(s[s.length - 1])} ${height - padB} L ${sx(s[0])} ${height - padB} Z`;
      svgEl.appendChild(this.svg("path", { d: area, fill: `url(#${gradId})`, stroke: "none" }));
      svgEl.appendChild(this.svg("path", { d: line, fill: "none", stroke: color, "stroke-width": 1.8, "stroke-linejoin": "round" }));
      if (s.length === 1) svgEl.appendChild(this.svg("circle", { cx: sx(s[0]), cy: sy(points[s[0]].rtt_avg), r: 2, fill: color }));
    });

    if (clip) {
      points.forEach((p, i) => {
        if (p.reachable && p.rtt_avg != null && p.rtt_avg > top) {
          const x = sx(i);
          const y = padT;
          const tri = this.svg("path", { d: `M ${x - 3.5} ${y + 5} L ${x + 3.5} ${y + 5} L ${x} ${y - 1} Z`, fill: "#fbbf24" });
          const title = this.svg("title", {});
          title.textContent = `${p.rtt_avg.toFixed(0)} ms (van skale)`;
          tri.appendChild(title);
          svgEl.appendChild(tri);
        }
      });
    }

    points.forEach((p, i) => {
      const fullyDown = !p.reachable;
      const partlyDown = p.unreachable_samples > 0 || p.packet_loss_pct > 0;
      if (fullyDown || partlyDown) {
        svgEl.appendChild(
          this.svg("circle", { cx: sx(i), cy: height - padB, r: fullyDown ? 3 : 2, fill: fullyDown ? "#f87171" : "#fbbf24" })
        );
      }
    });

    this.attachHover(container, svgEl, {
      width, padT, padB, height,
      xs: points.map((_, i) => sx(i)),
      onIndex: (i) => {
        const p = points[i];
        const up = p.reachable && p.rtt_avg != null;
        const extra = [];
        if (up && p.rtt_min != null && p.rtt_max != null) extra.push(`min ${p.rtt_min.toFixed(1)} / max ${p.rtt_max.toFixed(1)} ms`);
        if (p.packet_loss_pct > 0) extra.push(`gubitak ${p.packet_loss_pct.toFixed(0)}%`);
        if (p.samples > 1) extra.push(`${p.samples} merenja`);
        return {
          x: sx(i),
          y: up ? sy(p.rtt_avg) : height - padB,
          color: up ? color : "#f87171",
          html: `${up ? `<div class="ct-val">${p.rtt_avg.toFixed(1)} ms</div>` : '<div class="ct-val ct-bad">nedostupno</div>'}
            ${extra.length ? `<div class="ct-time">${extra.join(" · ")}</div>` : ""}
            <div class="ct-time">${this.fmtFull(xs[i])}</div>`,
        };
      },
    });

    container.appendChild(svgEl);
  },
};
