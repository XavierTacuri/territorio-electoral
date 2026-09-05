import { Box, Typography } from '@mui/material';

export function GlobalFooter() {
  return (
    <Box
      component="footer"
      sx={{
        mt: 'auto',
        pt: 2,
        pb: 1,
        borderTop: 1,
        borderColor: 'divider',
        textAlign: 'center',
      }}
    >
      <Typography variant="caption" color="text.secondary">
        © {new Date().getFullYear()} Territorio Electoral. Todos los derechos reservados.{' '}
        Desarrollado por Xavier Tacuri.
      </Typography>
    </Box>
  );
}
