import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, MenuItem, Paper, Select, Stack, Typography } from '@mui/material';
import { apiRequest } from '../../api/client';
import { formatPercentEsEc } from '../../lib/formatEsEc';
import type { Study } from './types';
type Feature = {
  type: 'Feature';
  id?: string | number;
  geometry: unknown;
  properties: Record<string, unknown>;
};
type Collection = { type: 'FeatureCollection'; features: Feature[] };
const colors = ['#edf6f9', '#bde0e6', '#83c5be', '#4f9f9a', '#256d68'];
const dpa = (p: Record<string, unknown>) => String(p.parish_dpa ?? p.code ?? '');
function bounds(features: Feature[]): [[number, number], [number, number]] | null {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const visit = (v: unknown): void => {
    if (!Array.isArray(v)) return;
    if (v.length >= 2 && typeof v[0] === 'number' && typeof v[1] === 'number') {
      minX = Math.min(minX, v[0]);
      maxX = Math.max(maxX, v[0]);
      minY = Math.min(minY, v[1]);
      maxY = Math.max(maxY, v[1]);
      return;
    }
    v.forEach(visit);
  };
  features.forEach((f) => visit((f.geometry as { coordinates?: unknown })?.coordinates));
  return Number.isFinite(minX)
    ? [
        [minX, minY],
        [maxX, maxY],
      ]
    : null;
}
export default function StudyMap({ campaignId, study }: { campaignId: string; study: Study }) {
  const ref = useRef<HTMLDivElement>(null);
  const [boundaries, setBoundaries] = useState<Collection>();
  const [option, setOption] = useState(study.options?.[0]?.id ?? '');
  const [status, setStatus] = useState<'loading' | 'success' | 'empty' | 'error'>('loading');
  const selected = study.options?.find((o) => o.id === option);
  const values = useMemo(
    () =>
      new Map(
        (study.territories ?? []).map((t) => {
          const result = study.results?.find(
            (r) => r.study_territory_id === t.id && r.option_id === option,
          );
          return [
            String(t.parish_dpa),
            { value: result?.percentage, sample: t.sample_size, name: t.parish_name },
          ];
        }),
      ),
    [study, option],
  );
  const merged = useMemo(
    () =>
      boundaries && {
        ...boundaries,
        features: boundaries.features.map((f) => {
          const row = values.get(dpa(f.properties));
          return {
            ...f,
            properties: {
              ...f.properties,
              study_value: row?.value,
              sample_size: row?.sample,
              parish_name: row?.name ?? f.properties.name,
            },
          };
        }),
      },
    [boundaries, values],
  );
  useEffect(() => {
    apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`)
      .then((x) => {
        setBoundaries(x);
        setStatus(x.features.length ? 'success' : 'empty');
      })
      .catch(() => setStatus('error'));
  }, [campaignId]);
  useEffect(() => {
    if (status !== 'success' || !merged?.features.length || !ref.current) return;
    let map: import('maplibre-gl').Map | undefined,
      cancelled = false;
    import('maplibre-gl').then(({ Map, NavigationControl, Popup }) => {
      if (cancelled || !ref.current) return;
      map = new Map({
        container: ref.current,
        style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json',
        scrollZoom: false,
      });
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
      map.on('load', () => {
        if (!map) return;
        map.addSource('study-boundaries', { type: 'geojson', data: merged as never });
        map.addLayer({
          id: 'study-fill',
          type: 'fill',
          source: 'study-boundaries',
          paint: {
            'fill-color': [
              'step',
              ['coalesce', ['get', 'study_value'], -1],
              '#e5e7eb',
              0,
              colors[0],
              0.1,
              colors[1],
              0.2,
              colors[2],
              0.3,
              colors[3],
              0.4,
              colors[4],
            ],
            'fill-opacity': 0.78,
          },
        });
        map.addLayer({
          id: 'study-outline',
          type: 'line',
          source: 'study-boundaries',
          paint: { 'line-color': '#ffffff', 'line-width': 1 },
        });
        const b = bounds(merged.features);
        if (b) map.fitBounds(b, { padding: 30, duration: 0 });
        const popup = new Popup({ closeButton: false, closeOnClick: false });
        map.on('mousemove', 'study-fill', (event) => {
          const p = event.features?.[0]?.properties;
          if (p)
            popup
              .setLngLat(event.lngLat)
              .setHTML(
                `<strong>${p.parish_name ?? 'Parroquia'}</strong><br>Porcentaje observado: ${typeof p.study_value === 'number' ? formatPercentEsEc(p.study_value) : 'Sin dato'}<br>Muestra: ${p.sample_size ?? 'Sin dato'}`,
              )
              .addTo(map!);
        });
        map.on('mouseleave', 'study-fill', () => popup.remove());
      });
    });
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [status, merged]);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
        <Typography variant="h2">MAPA DE ESTUDIOS</Typography>
        <Select size="small" value={option} onChange={(e) => setOption(e.target.value)}>
          {study.options?.map((o) => (
            <MenuItem key={o.id} value={o.id}>
              {o.label}
            </MenuItem>
          ))}
        </Select>
      </Stack>
      <Typography sx={{ mt: 1 }}>Porcentaje observado en el estudio — {selected?.label}</Typography>
      {status === 'loading' && <Alert severity="info">Cargando mapa…</Alert>}
      {status === 'empty' && <Alert severity="info">Sin geometrías disponibles.</Alert>}
      {status === 'error' && <Alert severity="warning">No fue posible cargar el mapa.</Alert>}
      <Box
        ref={ref}
        role="region"
        aria-label="Mapa neutral de resultados del estudio"
        sx={{
          display: status === 'success' ? 'block' : 'none',
          height: { xs: 340, md: 480 },
          width: '100%',
          mt: 2,
          overflow: 'hidden',
        }}
      />
      <Stack direction="row" flexWrap="wrap" spacing={1} sx={{ mt: 1 }}>
        {['0–10 %', '10–20 %', '20–30 %', '30–40 %', '≥ 40 %'].map((label, i) => (
          <Stack direction="row" alignItems="center" key={label}>
            <Box sx={{ width: 18, height: 12, bgcolor: colors[i], mr: 0.5 }} />
            <Typography variant="caption">{label}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
