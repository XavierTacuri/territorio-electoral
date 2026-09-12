import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, MenuItem, Paper, Select, Stack, Typography } from '@mui/material';
import { apiRequest } from '../../api/client';
import {
  getParticipationCategory,
  getParticipationColor,
  buildMetricScale,
  CurrentElectionMapLegend,
  mapLibreColorExpression,
  type MetricUnit,
} from './ParticipationMapLegend';

type Historical = { registered_voters?: number; turnout_rate: number | null };
export type ElectionMapParish = {
  parish_id: number;
  dpa_code: string;
  name: string;
  registered_voters_current: number;
  historical_2019?: Historical;
  historical_2023?: Historical;
  projection?: { low: number; central: number; high: number; expected_voters_central: number };
  data_quality_status: string;
  demographics?: Record<string, number>;
};
type Feature = {
  type: 'Feature';
  id?: string | number;
  geometry: any;
  properties: Record<string, any>;
};
type Collection = { type: 'FeatureCollection'; features: Feature[]; unmapped_count?: number };

const METRICS: { value: string; label: string; unit: MetricUnit }[] = [
  { value: 'registered_voters_current', label: 'Electores actuales', unit: 'count' },
  { value: 'turnout_2019', label: 'Participación observada 2019', unit: 'percent' },
  { value: 'turnout_2023', label: 'Participación observada 2023', unit: 'percent' },
  { value: 'projected_low_rate', label: 'Participación baja', unit: 'percent' },
  { value: 'projected_central_rate', label: 'Participación estimada', unit: 'percent' },
  { value: 'projected_high_rate', label: 'Participación alta', unit: 'percent' },
  { value: 'expected_voters_central', label: 'Votantes esperados', unit: 'count' },
  {
    value: 'registration_change_2019',
    label: 'Cambio del registro 2019 → actual',
    unit: 'percent',
  },
  {
    value: 'registration_change_2023',
    label: 'Cambio del registro 2023 → actual',
    unit: 'percent',
  },
  { value: 'inec_population_2022', label: 'Población INEC 2022', unit: 'count' },
  { value: 'inec_population_growth', label: 'Crecimiento poblacional INEC', unit: 'percent' },
  { value: 'population_density', label: 'Densidad poblacional', unit: 'density' },
];

const shown = (value: unknown, rate = false) =>
  typeof value === 'number'
    ? `${new Intl.NumberFormat('es-EC', { maximumFractionDigits: 2 }).format(rate ? value * 100 : value)}${rate ? ' %' : ''}`
    : '—';
const dpa = (properties: Record<string, any>) =>
  String(properties.parish_dpa ?? properties.code ?? '');
const qualityLabel = (value: unknown) =>
  ({ HIGH: 'Alta', MEDIUM: 'Media', LOW: 'Baja', INSUFFICIENT_DATA: 'Datos insuficientes' })[
    String(value)
  ] ?? shown(value);

function geometryBounds(features: Feature[]): [[number, number], [number, number]] | null {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const visit = (coordinates: any): void => {
    if (!Array.isArray(coordinates)) return;
    if (
      coordinates.length >= 2 &&
      typeof coordinates[0] === 'number' &&
      typeof coordinates[1] === 'number'
    ) {
      minX = Math.min(minX, coordinates[0]);
      maxX = Math.max(maxX, coordinates[0]);
      minY = Math.min(minY, coordinates[1]);
      maxY = Math.max(maxY, coordinates[1]);
      return;
    }
    coordinates.forEach(visit);
  };
  features.forEach((feature) => visit(feature.geometry?.coordinates));
  return Number.isFinite(minX)
    ? [
        [minX, minY],
        [maxX, maxY],
      ]
    : null;
}

export function CurrentElectionMap({
  campaignId,
  parishes,
  onSelect,
  compact = false,
  title = 'MAPA · ELECCIÓN ACTUAL',
  onStatusChange,
  selectedParishId,
}: {
  campaignId: string;
  parishes: ElectionMapParish[];
  onSelect: (id: number) => void;
  compact?: boolean;
  title?: string;
  onStatusChange?: (status: 'loading' | 'success' | 'empty' | 'error') => void;
  selectedParishId?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [metric, setMetric] = useState('projected_central_rate');
  const [boundaries, setBoundaries] = useState<Collection>();
  const [status, setStatus] = useState<'loading' | 'success' | 'empty' | 'error'>('loading');

  useEffect(() => onStatusChange?.(status), [onStatusChange, status]);

  useEffect(() => {
    let active = true;
    setStatus('loading');
    setBoundaries(undefined);
    apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`)
      .then((result) => {
        if (!active) return;
        setBoundaries(result);
        setStatus(result.features.length ? 'success' : 'empty');
      })
      .catch(() => {
        if (active) setStatus('error');
      });
    return () => {
      active = false;
    };
  }, [campaignId]);

  const merged = useMemo<Collection | undefined>(() => {
    if (!boundaries) return undefined;
    const byDpa = new Map(parishes.map((parish) => [String(parish.dpa_code), parish]));
    return {
      ...boundaries,
      features: boundaries.features.map((feature) => {
        const parish = byDpa.get(dpa(feature.properties));
        return {
          ...feature,
          properties: {
            ...feature.properties,
            parish_dpa: dpa(feature.properties),
            parish_name: parish?.name ?? feature.properties.name,
            parish_id: parish?.parish_id,
            registered_voters_current: parish?.registered_voters_current,
            turnout_2019: parish?.historical_2019?.turnout_rate,
            turnout_2023: parish?.historical_2023?.turnout_rate,
            projected_low_rate: parish?.projection?.low,
            projected_central_rate: parish?.projection?.central,
            projected_high_rate: parish?.projection?.high,
            expected_voters_central: parish?.projection?.expected_voters_central,
            model_quality: parish?.data_quality_status,
            registration_change_2019: parish?.historical_2019?.registered_voters
              ? (parish.registered_voters_current - parish.historical_2019.registered_voters) /
                parish.historical_2019.registered_voters
              : undefined,
            registration_change_2023: parish?.historical_2023?.registered_voters
              ? (parish.registered_voters_current - parish.historical_2023.registered_voters) /
                parish.historical_2023.registered_voters
              : undefined,
            inec_population_2022: parish?.demographics?.POP_TOTAL,
            inec_population_growth:
              parish?.demographics?.POPULATION_GROWTH ?? parish?.demographics?.POP_GROWTH,
            population_density:
              parish?.demographics?.POPULATION_DENSITY ?? parish?.demographics?.DENSITY,
          },
        };
      }),
    };
  }, [boundaries, parishes]);

  const metricDefinition = METRICS.find((item) => item.value === metric) ?? METRICS[4];
  const scale = useMemo(
    () =>
      buildMetricScale(
        metric,
        metricDefinition.label,
        metricDefinition.unit,
        (merged?.features ?? [])
          .map((feature) => feature.properties[metric])
          .filter((value): value is number => typeof value === 'number' && Number.isFinite(value)),
      ),
    [metric, metricDefinition.label, metricDefinition.unit, merged],
  );

  useEffect(() => {
    if (!import.meta.env.DEV || !merged) return;
    console.table(
      merged.features.map((feature) => ({
        parish_name: feature.properties.parish_name,
        projected_central_rate: feature.properties.projected_central_rate,
        category: getParticipationCategory(feature.properties.projected_central_rate),
        color: getParticipationColor(feature.properties.projected_central_rate),
      })),
    );
  }, [merged]);

  useEffect(() => {
    if (status !== 'success' || !merged?.features.length || !container.current) return;
    let map: import('maplibre-gl').Map | undefined;
    let cancelled = false;
    import('maplibre-gl')
      .then(({ Map, NavigationControl, Popup }) => {
        if (!container.current || cancelled) return;
        map = new Map({
          container: container.current,
          style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json',
          scrollZoom: false,
        });
        map.addControl(new NavigationControl({ showCompass: !compact }), 'top-right');
        map.on('load', () => {
          if (!map) return;
          map.addSource('current-election-boundaries', { type: 'geojson', data: merged as any });
          map.addLayer({
            id: 'current-election-fill',
            type: 'fill',
            source: 'current-election-boundaries',
            paint: {
              'fill-color': mapLibreColorExpression(scale),
              'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.9, 0.72],
            },
          });
          if (container.current) {
            container.current.dataset.metric = metric;
            container.current.dataset.featureCount = String(merged.features.length);
            container.current.dataset.fillColorExpression = JSON.stringify(
              map.getPaintProperty('current-election-fill', 'fill-color'),
            );
            container.current.dataset.zoom = String(map.getZoom());
          }
          map.on('zoomend', () => {
            if (container.current) container.current.dataset.zoom = String(map?.getZoom());
          });
          map.addLayer({
            id: 'current-election-outline',
            type: 'line',
            source: 'current-election-boundaries',
            paint: {
              'line-color': [
                'case',
                ['boolean', ['feature-state', 'selected'], false],
                '#102a43',
                '#ffffff',
              ],
              'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 1],
            },
          });
          const bounds = geometryBounds(merged.features);
          if (bounds) map.fitBounds(bounds, { padding: 30, duration: 0 });
          let hovered: string | number | undefined;
          let selected: string | number | undefined;
          const selectedFeature = merged.features.find(
            (feature) => Number(feature.properties.parish_id) === selectedParishId,
          );
          if (selectedFeature?.id != null) {
            selected = selectedFeature.id;
            map.setFeatureState(
              { source: 'current-election-boundaries', id: selected },
              { selected: true },
            );
            const selectedBounds = geometryBounds([selectedFeature]);
            if (selectedBounds) map.fitBounds(selectedBounds, { padding: 55, duration: 0 });
          }
          const hoverPopup = new Popup({ closeButton: false, closeOnClick: false });
          map.on('mousemove', 'current-election-fill', (event) => {
            const feature = event.features?.[0];
            const id = feature?.id;
            if (hovered != null)
              map?.setFeatureState(
                { source: 'current-election-boundaries', id: hovered },
                { hover: false },
              );
            if (id != null)
              map?.setFeatureState({ source: 'current-election-boundaries', id }, { hover: true });
            hovered = id;
            if (feature) {
              const p = feature.properties as any;
              hoverPopup
                .setLngLat(event.lngLat)
                .setHTML(
                  `<strong>${p.parish_name ?? 'Parroquia'}</strong><br>` +
                    `Participación estimada: ${shown(p.projected_central_rate, true)}<br>` +
                    `Escenario bajo: ${shown(p.projected_low_rate, true)}<br>` +
                    `Escenario alto: ${shown(p.projected_high_rate, true)}<br>` +
                    `Electores actuales: ${shown(p.registered_voters_current)}<br>` +
                    `Votantes esperados: ${shown(p.expected_voters_central)}<br>` +
                    `Calidad: ${qualityLabel(p.model_quality)}`,
                )
                .addTo(map!);
            }
          });
          map.on('mouseleave', 'current-election-fill', () => {
            if (hovered != null)
              map?.setFeatureState(
                { source: 'current-election-boundaries', id: hovered },
                { hover: false },
              );
            hovered = undefined;
            hoverPopup.remove();
          });
          map.on('click', 'current-election-fill', (event) => {
            const feature = event.features?.[0];
            if (!feature) return;
            if (selected != null)
              map?.setFeatureState(
                { source: 'current-election-boundaries', id: selected },
                { selected: false },
              );
            selected = feature.id;
            if (selected != null)
              map?.setFeatureState(
                { source: 'current-election-boundaries', id: selected },
                { selected: true },
              );
            const p = feature.properties as any;
            if (p.parish_id != null) onSelect(Number(p.parish_id));
          });
        });
      })
      .catch(() => setStatus('error'));
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [status, merged, metric, scale, onSelect, compact, selectedParishId]);

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
        <Typography variant="h2">{title}</Typography>
        <Select size="small" value={metric} onChange={(event) => setMetric(event.target.value)}>
          {METRICS.map((item) => (
            <MenuItem key={item.value} value={item.value}>
              {item.label}
            </MenuItem>
          ))}
        </Select>
      </Stack>
      {status === 'loading' && <Alert severity="info">Cargando mapa territorial…</Alert>}
      {status === 'empty' && (
        <Alert severity="info">No existen geometrías parroquiales disponibles.</Alert>
      )}
      {status === 'error' && (
        <Alert severity="warning">No fue posible cargar el mapa territorial.</Alert>
      )}
      <Box
        ref={container}
        role="region"
        aria-label="Mapa de elección actual"
        sx={{
          display: status === 'success' ? 'block' : 'none',
          height: compact ? { xs: 300, sm: 340, md: 390 } : { xs: 480, md: 620 },
          minHeight: compact ? 300 : 480,
          width: '100%',
          mt: 2,
          borderRadius: 1,
          overflow: 'hidden',
        }}
      />
      {status === 'success' && (
        <Box sx={{ mt: 1, display: 'flex', justifyContent: { xs: 'stretch', md: 'flex-start' } }}>
          <CurrentElectionMapLegend scale={scale} />
        </Box>
      )}
    </Paper>
  );
}
