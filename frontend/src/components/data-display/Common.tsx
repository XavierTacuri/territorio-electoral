import { Chip, Paper, Stack, Typography } from '@mui/material';
export function StatusBadge({ value }: { value: string }) {
  return <Chip size="small" variant="outlined" label={value.replaceAll('_', ' ')} />;
}
export function RoleBadge({ value }: { value: string }) {
  return (
    <Chip size="small" color="primary" variant="outlined" label={value.replaceAll('_', ' ')} />
  );
}
export function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={0.5}>
        <Typography color="text.secondary">{label}</Typography>
        <Typography variant="h2">{value}</Typography>
        {detail && <Typography variant="caption">{detail}</Typography>}
      </Stack>
    </Paper>
  );
}
export function PrivacySuppressedNotice() {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography fontWeight={600}>Datos protegidos por privacidad</Typography>
      <Typography>
        El segmento no alcanza el umbral mínimo; no se muestran respuestas individuales ni textos
        abiertos.
      </Typography>
    </Paper>
  );
}
