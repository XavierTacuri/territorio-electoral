import { Chip, Paper, Stack, Typography } from '@mui/material';
type Tone = 'success' | 'warning' | 'error' | 'info' | 'default';
// Los distintos módulos ya traducen sus códigos de estado a texto en
// español antes de llegar aquí (p. ej. "Aprobada", "Requiere atención"),
// así que el tono se infiere por palabra clave del propio texto en vez de
// exigir que cada pantalla declare un color — mantiene un solo lugar
// responsable de la coherencia visual de estados en toda la app.
const TONE_KEYWORDS: [RegExp, Tone][] = [
  [/rechaz|cancel|error|crític|vencid|descart/i, 'error'],
  [/pendient|suspend|revisión|revisada|advertencia|requiere atención|borrador/i, 'warning'],
  [/aprob|complet|realizad|resuelt|válid|activ[oa]\b|éxito/i, 'success'],
  [/información|planificad|programad|en curso|reconocid/i, 'info'],
];
export function statusTone(value: string): Tone {
  const match = TONE_KEYWORDS.find(([pattern]) => pattern.test(value));
  return match ? match[1] : 'default';
}
export function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  const resolved = tone ?? statusTone(value);
  return (
    <Chip
      size="small"
      label={value.replaceAll('_', ' ')}
      color={resolved === 'default' ? undefined : resolved}
      variant={resolved === 'default' ? 'outlined' : 'filled'}
      sx={
        resolved === 'default'
          ? undefined
          : (theme) => ({
              bgcolor: `${theme.palette[resolved].main}1F`,
              color: theme.palette[resolved].dark,
              border: `1px solid ${theme.palette[resolved].main}3D`,
            })
      }
    />
  );
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
