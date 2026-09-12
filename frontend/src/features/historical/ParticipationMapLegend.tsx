import { Box, Paper, Stack, Typography } from '@mui/material';
import type { ExpressionSpecification } from 'maplibre-gl';

export const PARTICIPATION_COLORS = {
  veryHigh: '#0B3C5D',
  high: '#1D5F87',
  medium: '#4C86A8',
  low: '#8DB9D3',
  veryLow: '#D6E6F2',
  noData: '#E5E7EB',
} as const;
// Familias de color por tipo de dato (§24 del refinamiento UX): cada métrica del
// mapa se pinta con una rampa distinta según qué representa, en vez de reusar
// siempre la misma escala azul de participación. El rojo nunca se usa de forma
// automática para "malo"/prioridad política — son puramente descriptivas.
const COUNT_COLORS = ['#E3EEFA', '#9DC3EA', '#4C86A8', '#0B3C5D'] as const; // electores/padrón/votantes: azul
const PARTICIPATION_FALLBACK_COLORS = ['#E1F5F0', '#8FD4C4', '#3F9E8C', '#0F6656'] as const; // participación (no central): verde/turquesa
const CHANGE_COLORS = ['#7E5109', '#D68910', '#F5B041', '#FDEBD0'] as const; // cambio del registro: rampa cálida por magnitud (índice 0 = mayor disminución)
const DEMOGRAPHIC_COLORS = ['#F3EEE4', '#D8C9A3', '#B79A5B', '#8C6D2E'] as const; // demografía/densidad: neutro arena
export type MetricFamily = 'count' | 'change' | 'demographic' | 'participation';
export function metricFamily(metric: string): MetricFamily {
  if (metric.startsWith('registration_change')) return 'change';
  if (metric.startsWith('inec_population') || metric === 'population_density') return 'demographic';
  if (metric.startsWith('turnout') || metric.startsWith('projected')) return 'participation';
  return 'count';
}
function familyColors(family: MetricFamily): readonly string[] {
  switch (family) {
    case 'change':
      return CHANGE_COLORS;
    case 'demographic':
      return DEMOGRAPHIC_COLORS;
    case 'participation':
      return PARTICIPATION_FALLBACK_COLORS;
    default:
      return COUNT_COLORS;
  }
}
function familyWords(family: MetricFamily, unit: MetricUnit): readonly string[] {
  switch (family) {
    case 'change':
      return ['Disminución alta', 'Disminución media', 'Disminución leve', 'Cambio menor'];
    case 'demographic':
      return unit === 'density'
        ? ['Baja densidad', 'Densidad media', 'Densidad alta', 'Densidad muy alta']
        : ['Bajo', 'Medio', 'Alto', 'Muy alto'];
    case 'participation':
      return ['Baja', 'Media', 'Alta', 'Muy alta'];
    default:
      return ['Muy bajo', 'Bajo', 'Medio', 'Alto'];
  }
}
// Reparte las 4 palabras "base" de una familia entre el número real de buckets
// (1 a 4, según cuántos cuantiles únicos existan) sin tocar el cálculo de
// cuantiles en sí — solo decide qué palabra le corresponde a cada posición.
function graduatedLabels(total: number, words: readonly string[]): string[] {
  if (total <= 0) return [];
  if (total >= words.length) return [...words];
  if (total === 1) return [words[Math.floor((words.length - 1) / 2)]];
  return Array.from({ length: total }, (_, i) => {
    const index = Math.round((i * (words.length - 1)) / (total - 1));
    return words[index];
  });
}
export type MetricUnit = 'percent' | 'count' | 'density';
export type MapScaleItem = { label: string; detail: string; color: string };
export type MapMetricScale = {
  metric: string;
  title: string;
  unit: MetricUnit;
  stops: Array<{ value: number; color: string }>;
  baseColor: string;
  noDataColor: string;
  items: MapScaleItem[];
};

const format = (value: number, unit: MetricUnit) =>
  unit === 'percent'
    ? `${(value * 100).toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`
    : unit === 'density'
      ? `${value.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} hab./km²`
      : value.toLocaleString('es-EC', { maximumFractionDigits: 0 });
export function buildMetricScale(
  metric: string,
  title: string,
  unit: MetricUnit,
  values: number[],
): MapMetricScale {
  if (metric === 'projected_central_rate')
    return {
      metric,
      title,
      unit,
      baseColor: PARTICIPATION_COLORS.veryLow,
      noDataColor: PARTICIPATION_COLORS.noData,
      stops: [
        { value: 0.67, color: PARTICIPATION_COLORS.low },
        { value: 0.69, color: PARTICIPATION_COLORS.medium },
        { value: 0.71, color: PARTICIPATION_COLORS.high },
        { value: 0.73, color: PARTICIPATION_COLORS.veryHigh },
      ],
      items: [
        { label: 'Muy alta', detail: '≥ 73,00 %', color: PARTICIPATION_COLORS.veryHigh },
        { label: 'Alta', detail: '71,00–72,99 %', color: PARTICIPATION_COLORS.high },
        { label: 'Media', detail: '69,00–70,99 %', color: PARTICIPATION_COLORS.medium },
        { label: 'Baja', detail: '67,00–68,99 %', color: PARTICIPATION_COLORS.low },
        { label: 'Muy baja', detail: '< 67,00 %', color: PARTICIPATION_COLORS.veryLow },
        { label: 'Sin dato', detail: '—', color: PARTICIPATION_COLORS.noData },
      ],
    };
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  const quantiles = [0.25, 0.5, 0.75]
    .map((q) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * q))])
    .filter((v, i, a) => Number.isFinite(v) && (i === 0 || v !== a[i - 1]));
  const family = metricFamily(metric);
  const colors = familyColors(family);
  const labels = graduatedLabels(
    quantiles.length + (sorted.length ? 1 : 0),
    familyWords(family, unit),
  );
  const stops = quantiles.map((value, index) => ({
    value,
    color: colors[index + 1] ?? colors[colors.length - 1],
  }));
  const minimum = sorted[0];
  const dataItems: MapScaleItem[] = sorted.length
    ? [
        {
          label: labels[0],
          detail: quantiles.length
            ? `${format(minimum, unit)} – < ${format(quantiles[0], unit)}`
            : format(minimum, unit),
          color: colors[0],
        },
        ...quantiles.map((value, index) => ({
          label: labels[index + 1],
          detail:
            index === quantiles.length - 1
              ? `≥ ${format(value, unit)}`
              : `${format(value, unit)} – < ${format(quantiles[index + 1], unit)}`,
          color: colors[index + 1] ?? colors[colors.length - 1],
        })),
      ]
    : [];
  return {
    metric,
    title,
    unit,
    stops,
    baseColor: colors[0],
    noDataColor: PARTICIPATION_COLORS.noData,
    items: [...dataItems, { label: 'Sin dato', detail: '—', color: PARTICIPATION_COLORS.noData }],
  };
}
export function mapLibreColorExpression(scale: MapMetricScale): ExpressionSpecification {
  return [
    'case',
    ['has', scale.metric],
    [
      'step',
      ['to-number', ['get', scale.metric]],
      scale.baseColor,
      ...scale.stops.flatMap((stop) => [stop.value, stop.color]),
    ],
    scale.noDataColor,
  ];
}
export function getParticipationColor(rate: number | null | undefined) {
  if (rate == null || !Number.isFinite(rate)) return PARTICIPATION_COLORS.noData;
  const percent = rate <= 1 ? rate * 100 : rate;
  if (percent >= 73) return PARTICIPATION_COLORS.veryHigh;
  if (percent >= 71) return PARTICIPATION_COLORS.high;
  if (percent >= 69) return PARTICIPATION_COLORS.medium;
  if (percent >= 67) return PARTICIPATION_COLORS.low;
  return PARTICIPATION_COLORS.veryLow;
}
export function getParticipationCategory(rate: number | null | undefined) {
  if (rate == null || !Number.isFinite(rate)) return 'SIN DATO';
  const percent = rate <= 1 ? rate * 100 : rate;
  if (percent >= 73) return 'MUY ALTA';
  if (percent >= 71) return 'ALTA';
  if (percent >= 69) return 'MEDIA';
  if (percent >= 67) return 'BAJA';
  return 'MUY BAJA';
}
export function CurrentElectionMapLegend({ scale }: { scale: MapMetricScale }) {
  return (
    <Paper
      elevation={3}
      aria-label={`Leyenda — ${scale.title}`}
      title={`Leyenda — ${scale.title}`}
      sx={{
        p: 1.5,
        minWidth: 220,
        width: { xs: '100%', md: 'auto' },
        maxWidth: { xs: '100%', md: 300 },
        bgcolor: 'rgba(255,255,255,.96)',
        overflow: 'hidden',
      }}
    >
      <Typography fontWeight={800} variant="subtitle2" sx={{ mb: 1 }}>
        Leyenda — {scale.title}
      </Typography>
      <Stack spacing={0.75}>
        {scale.items.map((item) => (
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            key={`${item.label}-${item.detail}`}
          >
            <Box
              aria-hidden
              sx={{
                width: 18,
                height: 18,
                flex: '0 0 18px',
                bgcolor: item.color,
                border: '1px solid',
                borderColor: item.label === 'Sin dato' ? 'grey.500' : 'rgba(0,0,0,.3)',
                borderRadius: 0.5,
              }}
            />
            <Typography variant="caption" sx={{ flexGrow: 1, color: 'text.primary' }}>
              {item.label}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
              {item.detail}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
