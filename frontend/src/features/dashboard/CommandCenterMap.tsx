import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Paper, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import type { ElectionMapParish } from '../historical/CurrentElectionMap';

type Layer = 'activities' | 'needs';
type Feature = { type: 'Feature'; id?: string | number; geometry: GeoJSON.Geometry; properties: Record<string, unknown> };
type Collection = { type: 'FeatureCollection'; features: Feature[] };
export type TerritoryOperation = { parish_id: number; activities: number; needs_open: number; commitments_pending: number; commitments_completed: number };

const layerLabels: Record<Layer, string> = { activities: 'Actividades', needs: 'Necesidades' };
const countFor = (row: TerritoryOperation | undefined, layer: Layer) => layer === 'activities' ? row?.activities ?? 0 : row?.needs_open ?? 0;
const boundsOf = (features: Feature[]): [[number, number], [number, number]] | null => {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === 'number' && typeof value[1] === 'number') { minX = Math.min(minX, value[0]); maxX = Math.max(maxX, value[0]); minY = Math.min(minY, value[1]); maxY = Math.max(maxY, value[1]); return; }
    value.forEach(visit);
  };
  features.forEach((feature) => visit((feature.geometry as { coordinates?: unknown }).coordinates));
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
};

export function CommandCenterMap({ campaignId, parishes, operations }: { campaignId: string; parishes: ElectionMapParish[]; operations: TerritoryOperation[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [layer, setLayer] = useState<Layer>('activities');
  const [boundaries, setBoundaries] = useState<Collection>();
  const [status, setStatus] = useState<'loading' | 'success' | 'empty' | 'error'>('loading');
  const [selectedId, setSelectedId] = useState<number>();
  useEffect(() => {
    let active = true; setStatus('loading');
    apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`).then((data) => { if (active) { setBoundaries(data); setStatus(data.features.length ? 'success' : 'empty'); } }).catch(() => active && setStatus('error'));
    return () => { active = false; };
  }, [campaignId]);
  const byId = useMemo(() => new Map(operations.map((row) => [row.parish_id, row])), [operations]);
  const byDpa = useMemo(() => new Map(parishes.map((row) => [String(row.dpa_code), row])), [parishes]);
  const selected = parishes.find((row) => row.parish_id === selectedId);
  const selectedOps = selected ? byId.get(selected.parish_id) : undefined;

  useEffect(() => {
    if (status !== 'success' || !boundaries?.features.length || !container.current) return;
    let disposed = false; let map: import('maplibre-gl').Map | undefined;
    const data: Collection = { ...boundaries, features: boundaries.features.map((feature, index) => {
      const code = String(feature.properties.parish_dpa ?? feature.properties.code ?? '');
      const parish = byDpa.get(code); const count = countFor(parish ? byId.get(parish.parish_id) : undefined, layer);
      return { ...feature, id: feature.id ?? index, properties: { ...feature.properties, parish_id: parish?.parish_id, parish_name: parish?.name ?? feature.properties.name, operation_count: count } };
    }) };
    import('maplibre-gl').then(({ Map, NavigationControl }) => {
      if (disposed || !container.current) return;
      map = new Map({ container: container.current, style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json', scrollZoom: false });
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
      map.on('load', () => {
        if (!map) return;
        map.addSource('command-center', { type: 'geojson', data: data as never });
        map.addLayer({ id: 'command-center-fill', type: 'fill', source: 'command-center', paint: { 'fill-color': ['case', ['>', ['get', 'operation_count'], 0], '#5b7c99', '#dbe4ea'], 'fill-opacity': 0.72 } });
        map.addLayer({ id: 'command-center-outline', type: 'line', source: 'command-center', paint: { 'line-color': '#ffffff', 'line-width': 1.5 } });
        const bounds = boundsOf(data.features); if (bounds) map.fitBounds(bounds, { padding: 28, duration: 0 });
        map.on('click', 'command-center-fill', (event) => { const id = Number(event.features?.[0]?.properties?.parish_id); if (Number.isFinite(id)) setSelectedId(id); });
        map.on('mouseenter', 'command-center-fill', () => { if (map) map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'command-center-fill', () => { if (map) map.getCanvas().style.cursor = ''; });
      });
    }).catch(() => setStatus('error'));
    return () => { disposed = true; map?.remove(); };
  }, [boundaries, byDpa, byId, layer, status]);

  return <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, overflow: 'hidden' }}>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
      <Box><Typography variant="overline" color="text.secondary">MAPA OPERATIVO</Typography><Typography component="h2" variant="h2">Territorio en operación</Typography></Box>
      <ToggleButtonGroup exclusive size="small" value={layer} onChange={(_, value: Layer | null) => value && setLayer(value)} aria-label="Capas operativas" sx={{ alignSelf: { xs: 'stretch', md: 'center' }, '& .MuiToggleButton-root': { flex: 1 } }}>
        {(Object.keys(layerLabels) as Layer[]).map((key) => <ToggleButton key={key} value={key}>{layerLabels[key]}</ToggleButton>)}
      </ToggleButtonGroup>
    </Stack>
    {status === 'loading' && <Box sx={{ height: 390, mt: 2, bgcolor: 'action.hover', borderRadius: 2 }} />}
    {status === 'empty' && <Alert severity="info" sx={{ mt: 2 }}>No hay geometría territorial disponible para esta campaña.</Alert>}
    {status === 'error' && <Alert severity="warning" sx={{ mt: 2 }}>No fue posible cargar el mapa territorial.</Alert>}
    <Box ref={container} role="region" aria-label="Mapa operativo territorial" sx={{ display: status === 'success' ? 'block' : 'none', height: { xs: 340, md: 460 }, mt: 2, borderRadius: 2, overflow: 'hidden' }} />
    <Stack direction="row" gap={1} alignItems="center" sx={{ mt: 1 }}><Chip size="small" label="Con registros" sx={{ bgcolor: '#5b7c99', color: '#fff' }} /><Chip size="small" label="Sin registros" /><Typography variant="caption" color="text.secondary">La capa representa presencia operativa, no desempeño electoral.</Typography></Stack>
    {selected && <Box sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 2 }}><Typography variant="h3">{selected.name}</Typography><Stack direction="row" gap={2} flexWrap="wrap" sx={{ my: 1 }}><span>Actividades: <b>{selectedOps?.activities ?? 0}</b></span><span>Necesidades: <b>{selectedOps?.needs_open ?? 0}</b></span><span>Padrón: <b>{selected.registered_voters_current.toLocaleString('es-EC')}</b></span>{typeof selected.demographics?.POP_TOTAL === 'number' && <span>Población: <b>{selected.demographics.POP_TOTAL.toLocaleString('es-EC')}</b></span>}</Stack><Button component={RouterLink} to={`/app/campaigns/${campaignId}/territories/${selected.parish_id}`}>VER EXPEDIENTE TERRITORIAL</Button></Box>}
  </Paper>;
}
