import { createContext, useContext, useState, useEffect, useCallback } from 'react';

// ─── Preset Themes ─────────────────────────────────────────────────────────────
export const PRESET_THEMES = {
  flipstar: {
    name: 'Flipstar Gold',
    emoji: '⭐',
    category: 'Premium',
    gradient: true,
    light: { pri: 'linear-gradient(to bottom, #D4AF37 0%, #F9E08B 50%, #B8860B 100%)', priFallback: '#E2B355', bg: '#FAFAFA', txt: '#1A1A1A', sub: '#78716C', border: '#E5E5E5', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(to bottom, #D4AF37 0%, #F9E08B 50%, #B8860B 100%)', priFallback: '#E2B355', bg: '#0D0D0D', txt: '#FFFFFF', sub: '#C2994B', border: '#262626', cardBg: '#1A1A1A' },
  },
  chrome: {
    name: 'Chrome Steel',
    emoji: '🔘',
    category: 'Metallic',
    gradient: true,
    light: { pri: 'linear-gradient(135deg, #E8E8E8 0%, #C0C0C0 25%, #A8A8A8 50%, #C0C0C0 75%, #E8E8E8 100%)', priFallback: '#C0C0C0', bg: '#F5F5F5', txt: '#1A1A1A', sub: '#666', border: '#D0D0D0', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(135deg, #505050 0%, #808080 25%, #A0A0A0 50%, #808080 75%, #505050 100%)', priFallback: '#808080', bg: '#0A0A0A', txt: '#F5F5F5', sub: '#999', border: '#2A2A2A', cardBg: '#1A1A1A' },
  },
  rainbow: {
    name: 'Rainbow',
    emoji: '🌈',
    category: 'Vibrant',
    gradient: true,
    light: { pri: 'linear-gradient(90deg, #FF0080 0%, #FF8C00 20%, #FFD700 40%, #00FF00 60%, #00CED1 80%, #9370DB 100%)', priFallback: '#FF0080', bg: '#FAFAFA', txt: '#1A1A1A', sub: '#666', border: '#E5E5E5', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(90deg, #FF1493 0%, #FF6347 20%, #FFD700 40%, #32CD32 60%, #1E90FF 80%, #9370DB 100%)', priFallback: '#FF1493', bg: '#0A0A0A', txt: '#F5F5F5', sub: '#999', border: '#2A2A2A', cardBg: '#1A1A1A' },
  },
  copper: {
    name: 'Copper Glow',
    emoji: '🟤',
    category: 'Metallic',
    gradient: true,
    light: { pri: 'linear-gradient(135deg, #B87333 0%, #D4A574 50%, #B87333 100%)', priFallback: '#B87333', bg: '#FFF7ED', txt: '#7C2D12', sub: '#78716C', border: '#FED7AA', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(135deg, #D4A574 0%, #F5C98B 50%, #D4A574 100%)', priFallback: '#D4A574', bg: '#1F1108', txt: '#FFEDD5', sub: '#A8A29E', border: '#4A2A0F', cardBg: '#3A2010' },
  },
  ocean: {
    name: 'Ocean Blue',
    emoji: '🌊',
    category: 'Cool',
    light: { pri: '#0EA5E9', priFallback: '#0EA5E9', bg: '#F0F9FF', txt: '#0C4A6E', sub: '#64748B', border: '#BAE6FD', cardBg: '#FFF' },
    dark: { pri: '#38BDF8', priFallback: '#38BDF8', bg: '#0C1E2E', txt: '#E0F2FE', sub: '#94A3B8', border: '#1E3A5F', cardBg: '#1A2F42' },
  },
  forest: {
    name: 'Forest Green',
    emoji: '🌿',
    category: 'Nature',
    light: { pri: '#10B981', priFallback: '#10B981', bg: '#F0FDF4', txt: '#064E3B', sub: '#6B7280', border: '#BBF7D0', cardBg: '#FFF' },
    dark: { pri: '#34D399', priFallback: '#34D399', bg: '#0A1F14', txt: '#D1FAE5', sub: '#9CA3AF', border: '#1E4A2F', cardBg: '#1A3A28' },
  },
  sunset: {
    name: 'Sunset Orange',
    emoji: '🌅',
    category: 'Warm',
    gradient: true,
    light: { pri: 'linear-gradient(135deg, #FF6B6B 0%, #FF8E53 50%, #FFA500 100%)', priFallback: '#F97316', bg: '#FFF7ED', txt: '#7C2D12', sub: '#78716C', border: '#FED7AA', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(135deg, #FF7F50 0%, #FF6347 50%, #FF4500 100%)', priFallback: '#FB923C', bg: '#1F1108', txt: '#FFEDD5', sub: '#A8A29E', border: '#4A2A0F', cardBg: '#3A2010' },
  },
  royal: {
    name: 'Royal Purple',
    emoji: '👑',
    category: 'Luxury',
    gradient: true,
    light: { pri: 'linear-gradient(135deg, #9333EA 0%, #A855F7 50%, #C084FC 100%)', priFallback: '#9333EA', bg: '#FAF5FF', txt: '#581C87', sub: '#71717A', border: '#E9D5FF', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(135deg, #A855F7 0%, #C084FC 50%, #E9D5FF 100%)', priFallback: '#A855F7', bg: '#1A0A2E', txt: '#F3E8FF', sub: '#A1A1AA', border: '#3A1E5F', cardBg: '#2A1A42' },
  },
  rose: {
    name: 'Rose Gold',
    emoji: '🌸',
    category: 'Elegant',
    gradient: true,
    light: { pri: 'linear-gradient(135deg, #F9A8D4 0%, #EC4899 50%, #DB2777 100%)', priFallback: '#EC4899', bg: '#FFF1F2', txt: '#881337', sub: '#737373', border: '#FBCFE8', cardBg: '#FFF' },
    dark: { pri: 'linear-gradient(135deg, #FBCFE8 0%, #F472B6 50%, #EC4899 100%)', priFallback: '#F472B6', bg: '#1F0A14', txt: '#FCE7F3', sub: '#A3A3A3', border: '#4A1E32', cardBg: '#3A1A28' },
  },
  midnight: {
    name: 'Midnight',
    emoji: '🌙',
    category: 'Dark',
    light: { pri: '#6366F1', priFallback: '#6366F1', bg: '#F5F5F5', txt: '#27272A', sub: '#71717A', border: '#E4E4E7', cardBg: '#FFF' },
    dark: { pri: '#818CF8', priFallback: '#818CF8', bg: '#09090B', txt: '#FAFAFA', sub: '#A1A1AA', border: '#27272A', cardBg: '#18181B' },
  },
  minimal: {
    name: 'Minimal',
    emoji: '⚪',
    category: 'Clean',
    light: { pri: '#18181B', priFallback: '#18181B', bg: '#FFFFFF', txt: '#09090B', sub: '#71717A', border: '#E4E4E7', cardBg: '#FAFAFA' },
    dark: { pri: '#FAFAFA', priFallback: '#FAFAFA', bg: '#09090B', txt: '#FAFAFA', sub: '#A1A1AA', border: '#27272A', cardBg: '#18181B' },
  },
  teal: {
    name: 'Teal Breeze',
    emoji: '💎',
    category: 'Fresh',
    light: { pri: '#14B8A6', priFallback: '#14B8A6', bg: '#F0FDFA', txt: '#134E4A', sub: '#6B7280', border: '#99F6E4', cardBg: '#FFF' },
    dark: { pri: '#2DD4BF', priFallback: '#2DD4BF', bg: '#0A1F1C', txt: '#CCFBF1', sub: '#9CA3AF', border: '#1E4A42', cardBg: '#1A3A34' },
  },
  crimson: {
    name: 'Crimson',
    emoji: '🔴',
    category: 'Bold',
    light: { pri: '#DC2626', priFallback: '#DC2626', bg: '#FEF2F2', txt: '#7F1D1D', sub: '#78716C', border: '#FECACA', cardBg: '#FFF' },
    dark: { pri: '#EF4444', priFallback: '#EF4444', bg: '#1F0A0A', txt: '#FEE2E2', sub: '#A8A29E', border: '#4A1E1E', cardBg: '#3A1A1A' },
  },
};

const STORAGE_KEY = '_platform_theme_v3'; // v3 forces brand dark+gold defaults for all users

function loadStored() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}

// Normalize colors so `pri` is ALWAYS a solid color (safe for CSS `color:` + hex ops).
// Gradient (if any) is exposed as `priGradient` for use on backgrounds.
function normalizeColors(raw) {
  const rawPri = raw.pri || '';
  const isGradient = typeof rawPri === 'string' && rawPri.trim().toLowerCase().startsWith('linear-gradient');
  const solid = raw.priFallback || (isGradient ? '#DA9B2A' : rawPri);
  // Legacy components reference T.dark for gradient endpoints — provide a sensible default
  // so gradients stay valid. Use a dark contrast color that works for both light & dark themes.
  const darkAccent = raw.dark || '#0C1A12';
  return {
    ...raw,
    pri: solid,                                   // solid color — always safe
    priGradient: isGradient ? rawPri : null,      // gradient if present
    priFallback: solid,                           // backwards-compat alias
    dark: darkAccent,                             // legacy fallback for gradient endpoints
  };
}

function applyCSS(c, glassEnabled = false) {
  const r = document.documentElement;
  r.style.setProperty('--color-primary', c.pri);
  r.style.setProperty('--color-primary-gradient', c.priGradient || c.pri);
  r.style.setProperty('--color-primary-fallback', c.pri);
  r.style.setProperty('--color-bg', c.bg);
  r.style.setProperty('--color-txt', c.txt);
  r.style.setProperty('--color-sub', c.sub);
  r.style.setProperty('--color-border', c.border);
  r.style.setProperty('--color-card', c.cardBg);
}

// Helper function to convert hex to rgba
function hexToRgba(hex, alpha) {
  if (hex.startsWith('#')) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return hex; // Return as-is if not hex format
}

// ─── Context ───────────────────────────────────────────────────────────────────
const ThemeContext = createContext();

export const useTheme = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
};

// Legacy adapter: returns a T-shaped object compatible with components that
// historically used a hard-coded `const T = { pri, txt, sub, bg, dark, border, ... }`.
// This keeps those components in sync with the admin-selected theme.
export const useLegacyT = () => {
  const { colors } = useTheme();
  return {
    pri: colors.pri,
    priGradient: colors.priGradient || colors.pri,
    priFallback: colors.priFallback || '#E2B355',
    priD: colors.pri,
    priL: colors.bg,
    txt: colors.txt,
    sub: colors.sub,
    bg: colors.bg,
    card: colors.cardBg,
    cardBg: colors.cardBg,
    dark: colors.dark || '#0C1A12',
    border: colors.border,
    // Non-theme constants kept for backwards compatibility
    red: '#EF4444',
    redL: '#FEE2E2',
    white: '#FFFFFF',
    gold: '#DA9B2A',
    goldL: '#FFFBEB',
    grn: '#10B981',
    secL: '#D1FAE5',
  };
};

export const ThemeProvider = ({ children }) => {
  const stored = loadStored();
  // Brand standard: always start with flipstar dark regardless of stored values
  const [preset, setPreset] = useState('flipstar');
  const [darkMode, setDarkMode] = useState(true);
  const [customPrimary, setCustomPrimary] = useState(stored.customPrimary || null);
  const [glassEnabled, setGlassEnabled] = useState(stored.glassEnabled ?? false);

  const resolveColors = useCallback((p = preset, dm = darkMode, cp = customPrimary) => {
    const base = PRESET_THEMES[p] || PRESET_THEMES.flipstar;
    const c = { ...(dm ? base.dark : base.light) };
    if (cp) {
      c.pri = cp;
      c.priFallback = cp;
    }
    return normalizeColors(c);
  }, [preset, darkMode, customPrimary]);

  const colors = resolveColors();

  const persist = (p, dm, cp, ge) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ preset: p, darkMode: dm, customPrimary: cp, glassEnabled: ge }));
  };

  useEffect(() => {
    applyCSS(resolveColors(), glassEnabled);
  }, [preset, darkMode, customPrimary, glassEnabled]);

  // Listen for storage events from admin panel saves (same-tab via dispatchEvent + cross-tab native)
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key !== STORAGE_KEY) return;
      try {
        const d = JSON.parse(e.newValue || '{}');
        if (d.preset !== undefined) setPreset(d.preset || 'flipstar');
        setDarkMode(d.darkMode ?? false);
        setCustomPrimary(d.customPrimary || null);
        setGlassEnabled(d.glassEnabled ?? false);
      } catch {}
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setThemePreset = useCallback((newPreset) => {
    setPreset(newPreset);
    setCustomPrimary(null);
    persist(newPreset, darkMode, null, glassEnabled);
  }, [darkMode, glassEnabled]);

  const toggleDarkMode = useCallback(() => {
    const nd = !darkMode;
    setDarkMode(nd);
    persist(preset, nd, customPrimary, glassEnabled);
  }, [darkMode, preset, customPrimary, glassEnabled]);

  const setCustomColor = useCallback((color) => {
    setCustomPrimary(color || null);
    persist(preset, darkMode, color || null, glassEnabled);
  }, [preset, darkMode, glassEnabled]);

  const toggleGlassEffect = useCallback(() => {
    const ng = !glassEnabled;
    setGlassEnabled(ng);
    persist(preset, darkMode, customPrimary, ng);
  }, [glassEnabled, preset, darkMode, customPrimary]);

  const applyFromSettings = useCallback((settings) => {
    if (!settings) return;
    // Brand standard: always flipstar dark — backend cannot override theme, dark mode, or primary color
    const p = 'flipstar';
    const dm = true;
    const cp = null; // primary_color_override is ignored — brand gold is enforced
    const ge = settings.glass_effect_enabled ?? glassEnabled;
    setPreset(p);
    setDarkMode(dm);
    setCustomPrimary(cp);
    setGlassEnabled(ge);
    persist(p, dm, cp, ge);
  }, [glassEnabled]);

  return (
    <ThemeContext.Provider value={{
      colors,
      darkMode,
      preset,
      glassEnabled,
      toggleDarkMode,
      setThemePreset,
      setCustomColor,
      toggleGlassEffect,
      applyFromSettings,
      resolveColors,
    }}>
      {children}
    </ThemeContext.Provider>
  );
};




