import { Alert, Box, Button, CircularProgress, Paper, Typography } from '@mui/material';
export function LoadingSkeleton() {
  return (
    <Box role="status" aria-live="polite" sx={{ p: 4, textAlign: 'center' }}>
      <CircularProgress size={32} />
      <Typography>Cargando información…</Typography>
    </Box>
  );
}
export function EmptyState({
  title = 'No hay datos disponibles',
  detail = 'Ajusta los filtros o registra nueva información.',
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
      <Typography variant="h2">{title}</Typography>
      <Typography color="text.secondary">{detail}</Typography>
    </Paper>
  );
}
export function ErrorState({
  message = 'No fue posible cargar la información.',
  retry,
}: {
  message?: string;
  retry?: () => void;
}) {
  return (
    <Alert severity="error" action={retry && <Button onClick={retry}>Reintentar</Button>}>
      {message}
    </Alert>
  );
}
