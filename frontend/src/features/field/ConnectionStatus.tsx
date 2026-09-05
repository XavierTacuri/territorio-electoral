import { Box, Typography } from '@mui/material';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

// Text is always paired with the dot: color alone must never be the only
// signal (accessibility, section 47 — and useful in bright sunlight too).
export function ConnectionStatus() {
  const online = useOnlineStatus();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }} role="status">
      <Box
        component="span"
        aria-hidden
        sx={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          bgcolor: online ? 'success.main' : 'text.disabled',
          flexShrink: 0,
        }}
      />
      <Typography variant="body2" fontWeight={700}>
        {online ? 'En línea' : 'Sin conexión'}
      </Typography>
    </Box>
  );
}

export function OfflineBanner() {
  const online = useOnlineStatus();
  if (online) return null;
  return (
    <Box
      sx={{
        bgcolor: 'warning.light',
        color: 'warning.contrastText',
        px: 2,
        py: 1,
        borderRadius: 1,
        mb: 2,
      }}
    >
      <Typography variant="body2">
        Puedes seguir trabajando. Los cambios quedarán guardados en este dispositivo.
      </Typography>
    </Box>
  );
}
