const THEME_PRESETS = {
  dark: { bg: "#0b1120", bgElevated: "#111827", text: "#e5e7eb", textDim: "#94a3b8", primary: "#22d3ee", secondary: "#818cf8", isDark: true },
  light: { bg: "#eef2f6", bgElevated: "#ffffff", text: "#0f172a", textDim: "#475569", primary: "#0e7490", secondary: "#6366f1", isDark: false },
  blue: { bg: "#0a1628", bgElevated: "#0f2138", text: "#e0e7ff", textDim: "#93a5c9", primary: "#3b82f6", secondary: "#60a5fa", isDark: true },
  green: { bg: "#0a1a12", bgElevated: "#0f2418", text: "#dcfce7", textDim: "#86a893", primary: "#22c55e", secondary: "#4ade80", isDark: true },
  purple: { bg: "#160a28", bgElevated: "#1e0f38", text: "#ede9fe", textDim: "#a595c9", primary: "#a855f7", secondary: "#c084fc", isDark: true },
  high_contrast: { bg: "#000000", bgElevated: "#000000", text: "#ffffff", textDim: "#ffffff", primary: "#ffff00", secondary: "#00ffff", isDark: true },
};

const APPEARANCE_CACHE_KEY = "nw_appearance";

function applyAppearance(settings) {
  if (!settings) return;
  const root = document.documentElement;

  const basePreset = THEME_PRESETS[settings.theme] || THEME_PRESETS.dark;
  const palette =
    settings.theme === "custom"
      ? {
          ...THEME_PRESETS.dark,
          text: settings.text_color || THEME_PRESETS.dark.text,
          primary: settings.primary_color || THEME_PRESETS.dark.primary,
          secondary: settings.secondary_color || THEME_PRESETS.dark.secondary,
        }
      : basePreset;

  root.style.setProperty("--bg", palette.bg);
  root.style.setProperty("--bg-elevated", palette.bgElevated);
  root.style.setProperty("--text", palette.text);
  root.style.setProperty("--text-dim", palette.textDim);
  root.style.setProperty("--primary", palette.primary);
  root.style.setProperty("--secondary", palette.secondary);

  const radius = Number(settings.border_radius) || 14;
  root.style.setProperty("--radius", `${radius}px`);
  root.style.setProperty("--radius-sm", `${Math.max(radius - 6, 4)}px`);

  const opacity = settings.card_opacity != null ? settings.card_opacity : 0.04;
  const overlay = palette.isDark ? "255,255,255" : "15,23,42";

  let cardBg;
  let backdropFilter = "none";
  if (settings.card_style === "solid") {
    cardBg = palette.bgElevated;
  } else if (settings.card_style === "glass") {
    cardBg = `rgba(${overlay}, ${opacity})`;
    backdropFilter = `blur(${Number(settings.card_blur) || 0}px)`;
  } else {
    cardBg = `rgba(${overlay}, ${opacity})`;
  }

  root.style.setProperty("--card-bg", cardBg);
  root.style.setProperty("--card-border", `rgba(${overlay}, ${palette.isDark ? 0.08 : 0.12})`);
  root.style.setProperty("--card-backdrop-filter", backdropFilter);

  if (document.body) {
    applyBackgroundImage(settings);
  } else {
    document.addEventListener("DOMContentLoaded", () => applyBackgroundImage(settings));
  }
}

function ensureBackgroundLayers() {
  if (!document.getElementById("bg-overlay")) {
    const overlay = document.createElement("div");
    overlay.id = "bg-overlay";
    document.body.prepend(overlay);
  }
  if (!document.getElementById("bg-layer")) {
    const layer = document.createElement("div");
    layer.id = "bg-layer";
    document.body.prepend(layer);
  }
}

function applyBackgroundImage(settings) {
  ensureBackgroundLayers();
  const layer = document.getElementById("bg-layer");
  const overlay = document.getElementById("bg-overlay");

  if (settings.background_enabled && settings.background_image) {
    document.body.classList.add("has-bg-image");
    layer.style.backgroundImage = `url("${settings.background_image}")`;
    layer.style.backgroundPosition = settings.background_position || "center";
    layer.style.backgroundSize = settings.background_size || "cover";
    layer.style.backgroundRepeat = settings.background_repeat || "no-repeat";
    layer.style.opacity = settings.background_opacity != null ? settings.background_opacity : 1;
    layer.style.filter = `blur(${Number(settings.background_blur) || 0}px) brightness(${Number(settings.background_brightness) || 100}%) saturate(${Number(settings.background_saturation) || 100}%)`;
    overlay.style.background = `rgba(0, 0, 0, ${settings.overlay_opacity != null ? settings.overlay_opacity : 0})`;
  } else {
    document.body.classList.remove("has-bg-image");
    layer.style.backgroundImage = "none";
    overlay.style.background = "transparent";
  }
}

(function applyCachedAppearance() {
  try {
    const cached = localStorage.getItem(APPEARANCE_CACHE_KEY);
    if (cached) applyAppearance(JSON.parse(cached));
  } catch (e) {
    /* no cache yet, or storage unavailable -- CSS defaults render instead */
  }
})();

fetch("/api/settings/appearance", { headers: { Accept: "application/json" } })
  .then((res) => (res.ok ? res.json() : null))
  .then((settings) => {
    if (!settings) return;
    applyAppearance(settings);
    try {
      localStorage.setItem(APPEARANCE_CACHE_KEY, JSON.stringify(settings));
    } catch (e) {
      /* per-viewer cache only; safe to skip */
    }
  })
  .catch(() => {
    /* appearance API unreachable -- keep whatever was cached/default */
  });

window.NWTheme = { apply: applyAppearance, presets: THEME_PRESETS };
