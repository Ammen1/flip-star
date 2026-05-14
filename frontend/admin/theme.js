// Admin Panel Theme - Professional Bright Design
export const adminTheme = {
  // Colors
  colors: {
    primary: '#2563EB',      // Royal Blue
    primaryDark: '#1D4ED8',  // Darker Blue
    primaryLight: '#3B82F6', // Lighter Blue
    secondary: '#7C3AED',    // Violet
    success: '#10B981',      // Emerald
    warning: '#8fc441',      // Amber
    error: '#EF4444',        // Red
    info: '#3B82F6',         // Blue
    
    // Backgrounds
    background: '#000000',   // Pure black
    surface: '#000000',      // Pure black
    card: '#000000',         // Pure black
    hover: '#1A1A1A',        // Dark gray
    
    // Text
    textPrimary: '#FFFFFF',  // Pure white
    textSecondary: '#FFFFFF', // Pure white
    textMuted: '#CCCCCC',    // Light gray
    textLight: '#FFFFFF',    // White
    
    // Borders & Shadows
    border: '#333333',       // Dark gray border
    borderLight: '#262626',  // Medium dark gray border
    shadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
    shadowLg: '0 4px 6px -1px rgba(0, 0, 0, 0.7), 0 2px 4px -1px rgba(0, 0, 0, 0.6)',
  },
  
  // Typography
  typography: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: {
      xs: '12px',
      sm: '13px',
      base: '14px',
      lg: '16px',
      xl: '18px',
      '2xl': '20px',
      '3xl': '24px',
      '4xl': '30px',
    },
    fontWeight: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
  },
  
  // Spacing
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '20px',
    '2xl': '24px',
    '3xl': '32px',
  },
  
  // Border Radius
  borderRadius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    full: '9999px',
  },
  
  // Shadows
  shadows: {
    sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
    md: '0 1px 3px rgba(0, 0, 0, 0.1)',
    lg: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    xl: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
  },
  
  // Transitions
  transitions: {
    fast: '150ms ease-in-out',
    base: '200ms ease-in-out',
    slow: '300ms ease-in-out',
  },

  // Component-specific styles
  components: {
    button: {
      primary: {
        background: '#2563EB',
        color: '#FFFFFF',
        hover: '#1D4ED8',
      },
      secondary: {
        background: '#1A1A1A',
        color: '#FFFFFF',
        border: '#333333',
        hover: '#262626',
      },
      danger: {
        background: '#EF4444',
        color: '#FFFFFF',
        hover: '#DC2626',
      },
    },
    card: {
      background: '#000000',
      border: '#333333',
      shadow: '0 1px 3px rgba(0, 0, 0, 0.8)',
    },
    input: {
      background: '#000000',
      border: '#333333',
      focus: '#2563EB',
      error: '#EF4444',
    },
  },
};

// Helper function to get theme value
export const useAdminTheme = () => adminTheme;

// CSS variables derived from the theme (for use in a wrapper element's style prop)
export const adminThemeCssVars = {
  '--admin-primary': adminTheme.colors.primary,
  '--admin-primary-dark': adminTheme.colors.primaryDark,
  '--admin-primary-light': adminTheme.colors.primaryLight,
  '--admin-secondary': adminTheme.colors.secondary,
  '--admin-success': adminTheme.colors.success,
  '--admin-warning': adminTheme.colors.warning,
  '--admin-error': adminTheme.colors.error,
  '--admin-info': adminTheme.colors.info,
  '--admin-background': adminTheme.colors.background,
  '--admin-surface': adminTheme.colors.surface,
  '--admin-card': adminTheme.colors.card,
  '--admin-hover': adminTheme.colors.hover,
  '--admin-text-primary': adminTheme.colors.textPrimary,
  '--admin-text-secondary': adminTheme.colors.textSecondary,
  '--admin-text-muted': adminTheme.colors.textMuted,
  '--admin-text-light': adminTheme.colors.textLight,
  '--admin-border': adminTheme.colors.border,
  '--admin-border-light': adminTheme.colors.borderLight,
  '--admin-font-family': adminTheme.typography.fontFamily,
};
