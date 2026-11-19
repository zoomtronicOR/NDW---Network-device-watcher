(function () {
  let socket = null;
  let reconnectDelay = 1000;

  function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/api/ws`);

    socket.addEventListener("open", () => {
      reconnectDelay = 1000;
    });

    socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      handleMessage(data);
    });

    socket.addEventListener("close", () => {
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  function handleAnomaly(a) {
    if (!a) return;
    if (a.event_type === "SCAN_DETECTED") {
      showToast({
        title: "⚠ SKENIRANJE MREŽE",
        lines: [
          `Izvor: ${a.name || "nepoznat uređaj"}`,
          `MAC: ${a.mac}`,
          `IP: ${a.ip || "-"}`,
          `Vendor: ${a.vendor || "nepoznat"}`,
          a.reason
            ? `Poznati skener, neuobičajeno: ${a.reason}`
            : `${a.target_count} različitih adresa za ${a.window_seconds}s (ARP sweep)`,
        ],
        tone: "bad",
        timeout: 15000,
      });
      playBeep();
    } else if (a.event_type === "SPECIAL_DEVICE") {
      showToast({
        title: `★ ${a.name || a.mac} je ${a.online ? "ONLINE" : "OFFLINE"}`,
        lines: [`MAC: ${a.mac}`, `IP: ${a.ip || "-"}`],
        tone: a.online ? "new" : "bad",
        timeout: 12000,
      });
      playBeep();
    } else if (a.event_type === "IP_CONFLICT") {
      showToast({
        title: "⚠ IP KONFLIKT",
        lines: [`IP: ${a.ip}`, ...(a.macs || []).map((m) => `MAC: ${m}`)],
        tone: "bad",
        timeout: 15000,
      });
      playBeep();
    }
    window.dispatchEvent(new CustomEvent("nw:refresh", { detail: a }));
  }

  function handleMessage(data) {
    if (data.type === "anomaly") return handleAnomaly(data.anomaly);
    if (data.type !== "scan_complete") return;

    (data.new_devices || []).forEach((d) => {
      showToast({
        title: "⚠ NOVI UREĐAJ",
        lines: [
          `MAC: ${d.mac}`,
          `IP: ${d.ip || "-"}`,
          `Hostname: ${d.hostname || "nepoznat"}`,
          `Vendor: ${d.vendor || "nepoznat"}`,
          `Veza: ${d.connection_type || "-"}`,
        ],
        tone: "new",
        timeout: 12000,
      });
      playBeep();
    });

    if (data.burst_anomaly) {
      showToast({
        title: "⚠ NALET NOVIH UREĐAJA",
        lines: ["Neuobičajeno veliki broj novih uređaja u kratkom periodu."],
        tone: "bad",
        timeout: 12000,
      });
    }

    window.dispatchEvent(new CustomEvent("nw:refresh", { detail: data }));
  }

  connect();
})();
