import { createTheme } from '@mui/material/styles';
export const theme = createTheme({
  palette: {
    primary: { main: '#244b5a' },
    secondary: { main: '#6c5d47' },
    background: { default: '#f5f7f8' },
  },
  typography: {
    fontFamily: '"Inter", "Segoe UI", sans-serif',
    h1: { fontSize: '2rem', fontWeight: 700 },
    h2: { fontSize: '1.45rem', fontWeight: 650 },
  },
});
