import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';

type Metric = { parish_id: number; dpa_code: string; name: string; value: number };
type Topic = { code: string; name: string };
type Feature = {
  type: 'Feature';
  id?: string | number;
  geometry: any;
  properties: Record<string, any>;
};
type Collection = { type: 'FeatureCollection'; features: Feature[] };
const COLORS = ['#eef2f3', '#cbd5d8', '#94a7ad', '#5f7880', '#344e56'];
const PERIODS: Record<string, string> = {
  '7': 'Últimos 7 días',
  '30': 'Últimos 30 días',
  total: 'Total',
};
const bounds = (features: Feature[]) => {
  let a = Infinity,
    b = Infinity,
    c = -Infinity,
    d = -Infinity;
  const visit = (x: any): void => {
    if (!Array.isArray(x)) return;
    if (typeof x[0] === 'number') {
      a = Math.min(a, x[0]);
      b = Math.min(b, x[1]);
      c = Math.max(c, x[0]);
      d = Math.max(d, x[1]);
      return;
    }
    x.forEach(visit);
  };
  features.forEach((f) => visit(f.geometry?.coordinates));
  return Number.isFinite(a)
    ? ([
        [a, b],
        [c, d],
      ] as [[number, number], [number, number]])
    : null;
};
const scale = (values: number[]) => {
  const max = Math.max(0, ...values);
  const stops = max
    ? Array.from(
        new Set([1, Math.ceil(max * 0.25), Math.ceil(max * 0.5), Math.ceil(max * 0.75)]),
      ).sort((a, b) => a - b)
    : [];
  return {
    stops,
    expression: (stops.length
      ? [
          'step',
          ['to-number', ['get', 'value']],
          COLORS[0],
          ...stops.flatMap((v, i) => [v, COLORS[Math.min(i + 1, COLORS.length - 1)]]),
        ]
      : COLORS[0]) as any,
  };
};

export function PublicIntelligenceMap({
  campaignId,
  onView,
}: {
  campaignId: string;
  onView: (parishId: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [period, setPeriod] = useState('30'),
    [topic, setTopic] = useState(''),
    [selected, setSelected] = useState<Metric>();
  const boundaries = useQuery({
    queryKey: ['public-map-boundaries', campaignId],
    queryFn: () =>
      apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`),
  });
  const metrics = useQuery({
    queryKey: ['public-map', campaignId, period, topic],
    queryFn: () =>
      apiRequest<Metric[]>(
        `/campaigns/${campaignId}/public-intelligence/map?period=${period}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}`,
      ),
  });
  const topics = useQuery({
    queryKey: ['public-topics'],
    queryFn: () => apiRequest<Topic[]>('/public-topics'),
  });
  const merged = useMemo(() => {
    if (!boundaries.data || !metrics.data) return;
    const byDpa = new Map(metrics.data.map((x) => [x.dpa_code, x]));
    return {
      ...boundaries.data,
      features: boundaries.data.features.map((f) => {
        const m = byDpa.get(String(f.properties.parish_dpa ?? f.properties.code ?? ''));
        return {
          ...f,
          properties: {
            ...f.properties,
            parish_id: m?.parish_id,
            parish_name: m?.name ?? f.properties.name,
            value: m?.value ?? 0,
          },
        };
      }),
    };
  }, [boundaries.data, metrics.data]);
  const legend = useMemo(
    () => scale((merged?.features ?? []).map((f) => Number(f.properties.value))),
    [merged],
  );
  useEffect(() => {
    if (!merged?.features.length || !ref.current) return;
    let map: import('maplibre-gl').Map | undefined,
      cancelled = false;
    import('maplibre-gl')
      .then(({ Map, NavigationControl, Popup }) => {
        if (cancelled || !ref.current) return;
        map = new Map({
          container: ref.current,
          style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json',
          scrollZoom: false,
        });
        map.addControl(new NavigationControl(), 'top-right');
        map.on('load', () => {
          if (!map) return;
          map.addSource('public-boundaries', { type: 'geojson', data: merged as any });
          map.addLayer({
            id: 'public-fill',
            type: 'fill',
            source: 'public-boundaries',
            paint: {
              'fill-color': legend.expression,
              'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.9, 0.72],
            },
          });
          map.addLayer({
            id: 'public-outline',
            type: 'line',
            source: 'public-boundaries',
            paint: {
              'line-color': [
                'case',
                ['boolean', ['feature-state', 'selected'], false],
                '#172f35',
                '#fff',
              ],
              'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 1],
            },
          });
          const box = bounds(merged.features);
          if (box) map.fitBounds(box, { padding: 28, duration: 0 });
          if (ref.current) {
            ref.current.dataset.featureCount = String(merged.features.length);
            ref.current.dataset.scrollZoom = String(map.scrollZoom.isEnabled());
          }
          let hovered: string | number | undefined, chosen: string | number | undefined;
          const popup = new Popup({ closeButton: false, closeOnClick: false });
          map.on('mousemove', 'public-fill', (e) => {
            const f = e.features?.[0];
            if (hovered != null)
              map?.setFeatureState({ source: 'public-boundaries', id: hovered }, { hover: false });
            hovered = f?.id;
            if (hovered != null)
              map?.setFeatureState({ source: 'public-boundaries', id: hovered }, { hover: true });
            if (f)
              popup
                .setLngLat(e.lngLat)
                .setHTML(
                  `<strong>${f.properties?.parish_name}</strong><br>Publicaciones: ${f.properties?.value ?? 0}<br>Periodo: ${PERIODS[period]}<br>Tema: ${topic ? (topics.data?.find((t) => t.code === topic)?.name ?? topic) : 'Todos'}`,
                )
                .addTo(map!);
          });
          map.on('mouseleave', 'public-fill', () => popup.remove());
          map.on('click', 'public-fill', (e) => {
            const f = e.features?.[0];
            if (!f) return;
            if (chosen != null)
              map?.setFeatureState(
                { source: 'public-boundaries', id: chosen },
                { selected: false },
              );
            chosen = f.id;
            if (chosen != null)
              map?.setFeatureState({ source: 'public-boundaries', id: chosen }, { selected: true });
            setSelected({
              parish_id: Number(f.properties?.parish_id),
              dpa_code: '',
              name: String(f.properties?.parish_name),
              value: Number(f.properties?.value ?? 0),
            });
          });
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [merged, legend.expression, period, topic, topics.data]);
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h2">MAPA DE INFORMACIÓN PÚBLICA</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ my: 2 }}>
        <TextField
          select
          label="Periodo / Métrica"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        >
          {Object.entries(PERIODS).map(([v, l]) => (
            <MenuItem key={v} value={v}>
              {l}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Tema"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {topics.data?.map((t) => (
            <MenuItem key={t.code} value={t.code}>
              {t.name}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {(boundaries.isLoading || metrics.isLoading) && (
        <Alert severity="info">Cargando mapa territorial…</Alert>
      )}
      {(boundaries.isError || metrics.isError) && (
        <Alert severity="warning">No fue posible cargar el mapa territorial.</Alert>
      )}
      <Box
        ref={ref}
        role="region"
        aria-label="Mapa de información pública"
        sx={{
          display: merged?.features.length ? 'block' : 'none',
          height: { xs: 420, md: 600 },
          width: '100%',
          borderRadius: 1,
          overflow: 'hidden',
        }}
      />
      <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
        <Typography fontWeight={700}>Leyenda — publicaciones</Typography>
        {legend.stops.length === 0 ? (
          <Typography>0 publicaciones</Typography>
        ) : (
          <>
            {<Typography sx={{ color: COLORS[0] }}>■ 0</Typography>}
            {legend.stops.map((v, i) => (
              <Typography key={v} sx={{ color: COLORS[i + 1] }}>
                ■ ≥ {v}
              </Typography>
            ))}
          </>
        )}
      </Stack>
      {selected && (
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ sm: 'center' }}
          gap={2}
          sx={{ mt: 2 }}
        >
          <Typography>
            <strong>{selected.name}</strong> · {selected.value} publicaciones
          </Typography>
          <Button variant="contained" onClick={() => onView(selected.parish_id)}>
            Ver publicaciones
          </Button>
        </Stack>
      )}
    </Paper>
  );
}
