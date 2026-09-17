import { createTheme } from '@mui/material/styles';

// Tokens centrales del sistema de diseño. Todo lo demás (Cards, tablas,
// botones, chips, modales) se apoya en este único archivo para que el
// aspecto visual sea consistente en toda la aplicación sin duplicar estilos
// página por página.
const tokens = {
  primary: { main: '#1D4E89', dark: '#123761', light: '#4E77AE', contrastText: '#FFFFFF' },
  secondary: { main: '#0E9488', dark: '#0B6F66', light: '#4FBFB4', contrastText: '#04211D' },
  background: { default: '#F4F6F9', paper: '#FFFFFF' },
  text: { primary: '#16222E', secondary: '#5B6B7A', disabled: '#9AA7B2' },
  divider: '#E3E8EE',
  success: { main: '#1E8E5A', dark: '#166B44', light: '#57B486', contrastText: '#FFFFFF' },
  warning: { main: '#B7791F', dark: '#8F5F16', light: '#D9A94F', contrastText: '#FFFFFF' },
  error: { main: '#C0362C', dark: '#96271F', light: '#DD7A72', contrastText: '#FFFFFF' },
  info: { main: '#2B7BB9', dark: '#1F5D8C', light: '#6BA6D6', contrastText: '#FFFFFF' },
};

// Colores exclusivos del sidebar oscuro: viven fuera de la paleta de MUI
// porque no representan estados/semántica reutilizable, solo la piel del
// panel de navegación.
export const sidebar = {
  bg: '#0F1E2E',
  bgElevated: '#132840',
  border: 'rgba(255,255,255,0.08)',
  text: '#C6D2DE',
  textMuted: '#8195A8',
  textActive: '#FFFFFF',
  hoverBg: 'rgba(255,255,255,0.06)',
  activeBg: 'rgba(255,255,255,0.12)',
  accent: tokens.secondary.main,
};

export const theme = createTheme({
  palette: {
    primary: tokens.primary,
    secondary: tokens.secondary,
    success: tokens.success,
    warning: tokens.warning,
    error: tokens.error,
    info: tokens.info,
    background: tokens.background,
    text: tokens.text,
    divider: tokens.divider,
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", sans-serif',
    h1: { fontSize: '1.85rem', fontWeight: 750, letterSpacing: -0.3, lineHeight: 1.25 },
    h2: { fontSize: '1.3rem', fontWeight: 700, letterSpacing: -0.1, lineHeight: 1.3 },
    h3: { fontSize: '1.05rem', fontWeight: 700, lineHeight: 1.35 },
    subtitle1: { fontSize: '0.95rem', fontWeight: 500, color: tokens.text.secondary },
    subtitle2: { fontSize: '0.85rem', fontWeight: 600 },
    body1: { fontSize: '0.9rem' },
    body2: { fontSize: '0.85rem' },
    caption: { fontSize: '0.75rem' },
    overline: { fontSize: '0.7rem', fontWeight: 700, letterSpacing: 0.8 },
    button: { fontWeight: 650, letterSpacing: 0.2 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: tokens.background.default },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        rounded: { borderRadius: 14 },
        outlined: { borderColor: tokens.divider },
      },
    },
    MuiCard: {
      defaultProps: { variant: 'outlined' },
      styleOverrides: {
        root: {
          borderRadius: 14,
          borderColor: tokens.divider,
          boxShadow: '0 1px 2px rgba(16, 30, 44, 0.03)',
        },
      },
    },
    MuiCardContent: { styleOverrides: { root: { padding: 20, '&:last-child': { paddingBottom: 20 } } } },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 8, paddingInline: 16, paddingBlock: 8 },
        contained: { boxShadow: 'none', '&:hover': { boxShadow: '0 2px 6px rgba(16,30,44,0.12)' } },
        sizeSmall: { paddingInline: 10, paddingBlock: 5 },
      },
    },
    MuiIconButton: { styleOverrides: { root: { borderRadius: 8 } } },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 650, borderRadius: 999 },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: tokens.divider, padding: '9px 16px' },
        head: {
          fontWeight: 700,
          color: tokens.text.secondary,
          backgroundColor: '#F8FAFC',
          fontSize: '0.78rem',
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: { '&:last-child td': { borderBottom: 0 } },
      },
    },
    MuiTableContainer: {
      styleOverrides: { root: { borderRadius: 14 } },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 16 },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: { fontSize: '1.15rem', fontWeight: 700, padding: '20px 24px' },
      },
    },
    MuiDialogContent: { styleOverrides: { root: { padding: '4px 24px 20px' } } },
    MuiDialogActions: {
      styleOverrides: { root: { padding: '16px 24px', borderTop: `1px solid ${tokens.divider}` } },
    },
    MuiOutlinedInput: {
      styleOverrides: { root: { borderRadius: 8 } },
    },
    MuiAlert: {
      styleOverrides: { root: { borderRadius: 10 } },
    },
    MuiLinearProgress: {
      styleOverrides: { root: { borderRadius: 999 } },
    },
    MuiAppBar: {
      defaultProps: { color: 'inherit', elevation: 0 },
      styleOverrides: {
        root: { backgroundColor: tokens.background.paper, borderBottom: `1px solid ${tokens.divider}` },
      },
    },
    MuiTooltip: {
      styleOverrides: { tooltip: { fontSize: '0.75rem', borderRadius: 8 } },
    },
  },
});
