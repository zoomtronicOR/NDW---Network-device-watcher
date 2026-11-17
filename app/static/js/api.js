const Api = {
  async _get(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
    return res.json();
  },
  async _send(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.detail) detail = errBody.detail;
      } catch (e) {
        /* body wasn't JSON; keep the generic status message */
      }
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
  },
  stats: () => Api._get("/api/stats"),
  onlineTimeline: (hours = 24) => Api._get(`/api/charts/online-timeline?hours=${hours}`),
  newDevicesDaily: (days = 30) => Api._get(`/api/charts/new-devices-daily?days=${days}`),
  connectionSplit: () => Api._get("/api/charts/connection-split"),
  deviceTypes: () => Api._get("/api/charts/device-types"),
  topVendors: (limit = 8) => Api._get(`/api/charts/top-vendors?limit=${limit}`),
  listDevices: (params) => Api._get(`/api/devices?${new URLSearchParams(params).toString()}`),
  listEvents: (params) => Api._get(`/api/events?${new URLSearchParams(params).toString()}`),
  getDevice: (id) => Api._get(`/api/devices/${id}`),
  updateDevice: (id, payload) => Api._send("PATCH", `/api/devices/${id}`, payload),
  deleteDevice: (id) => Api._send("DELETE", `/api/devices/${id}`),
  getMqttSettings: () => Api._get("/api/settings/mqtt"),
  updateMqttSettings: (payload) => Api._send("PUT", "/api/settings/mqtt", payload),
  testMqtt: () => Api._send("POST", "/api/test/mqtt"),
  getSmtpSettings: () => Api._get("/api/settings/smtp"),
  updateSmtpSettings: (payload) => Api._send("PUT", "/api/settings/smtp", payload),
  testSmtp: () => Api._send("POST", "/api/test/smtp"),
  getNotificationSettings: () => Api._get("/api/settings/notifications"),
  updateNotificationSettings: (payload) => Api._send("PUT", "/api/settings/notifications", payload),
  getScannerSettings: () => Api._get("/api/settings/scanner"),
  updateScannerSettings: (payload) => Api._send("PUT", "/api/settings/scanner", payload),
  getWebhookSettings: () => Api._get("/api/settings/webhook"),
  updateWebhookSettings: (payload) => Api._send("PUT", "/api/settings/webhook", payload),
  testWebhook: () => Api._send("POST", "/api/test/webhook"),
  getOmadaSettings: () => Api._get("/api/settings/omada"),
  updateOmadaSettings: (payload) => Api._send("PUT", "/api/settings/omada", payload),
  testOmada: () => Api._send("POST", "/api/test/omada"),
  getOmadaSites: () => Api._get("/api/settings/omada/sites"),
  importConfig: (payload) => Api._send("POST", "/api/settings/backup/import", payload),
  getAppearanceSettings: () => Api._get("/api/settings/appearance"),
  updateAppearanceSettings: (payload) => Api._send("PUT", "/api/settings/appearance", payload),
  async uploadBackground(file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/settings/appearance/background", { method: "POST", body: formData });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.detail) detail = errBody.detail;
      } catch (e) {
        /* body wasn't JSON */
      }
      throw new Error(detail);
    }
    return res.json();
  },
  removeBackground: () => Api._send("DELETE", "/api/settings/appearance/background"),
  listLogs: (params) => Api._get(`/api/logs?${new URLSearchParams(params).toString()}`),
  getTimeMachineBounds: () => Api._get("/api/timemachine/bounds"),
  getTimeMachineState: (at) => Api._get(`/api/timemachine/state?at=${encodeURIComponent(at)}`),
  resetDevices: () => Api._send("DELETE", "/api/settings/reset/devices"),
  getPingSeries: (hours = 1) => Api._get(`/api/ping/series?hours=${hours}&buckets=200`),
  getScanDetectionSettings: () => Api._get("/api/settings/scan-detection"),
  updateScanDetectionSettings: (payload) => Api._send("PUT", "/api/settings/scan-detection", payload),
  listPingTargets: () => Api._get("/api/ping/targets"),
  createPingTarget: (payload) => Api._send("POST", "/api/ping/targets", payload),
  updatePingTarget: (id, payload) => Api._send("PATCH", `/api/ping/targets/${id}`, payload),
  deletePingTarget: (id) => Api._send("DELETE", `/api/ping/targets/${id}`),
  getPingSettings: () => Api._get("/api/settings/ping"),
  updatePingSettings: (payload) => Api._send("PUT", "/api/settings/ping", payload),
  getHistorySettings: () => Api._get("/api/settings/history"),
  updateHistorySettings: (payload) => Api._send("PUT", "/api/settings/history", payload),
  runHistoryCleanup: () => Api._send("POST", "/api/settings/history/cleanup-now"),
  getTelemetry: () => Api._get("/api/telemetry"),
  listNotifications: (params) => Api._get(`/api/notifications?${new URLSearchParams(params).toString()}`),
};
