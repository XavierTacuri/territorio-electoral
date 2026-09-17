import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import MapOutlinedIcon from '@mui/icons-material/MapOutlined';
import { Link as RouterLink } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import type { ElectionMapParish } from '../historical/CurrentElectionMap';
import { TERRITORIAL_FALLBACK_CENTER, TERRITORIAL_FALLBACK_ZOOM } from './mapFallbackCenter';

type Layer = 'activities' | 'needs';
type Feature = {
  type: 'Feature';
  id?: string | number;
  geometry: GeoJSON.Geometry;
  properties: Record<string, unknown>;
};
type Collection = { type: 'FeatureCollection'; features: Feature[] };
// Only geometry the backend actually validated and imported may be drawn as an
// official territorial boundary. SYNTHETIC_PLACEHOLDER/UNKNOWN rows (e.g. the
// seed_gualaceo.py fixture squares) must never render, and must never feed
// fitBounds — that is how a placeholder near [0,0] used to be mistaken for a
// real map.
const isOfficialBoundary = (feature: Feature) =>
  feature.properties.geometry_source === 'OFFICIAL_IMPORT';
export type TerritoryOperation = {
  parish_id: number;
  activities: number;
  needs_open: number;
  commitments_pending: number;
  commitments_completed: number;
};

const layerLabels: Record<Layer, string> = { activities: 'Actividades', needs: 'Necesidades' };
const countFor = (row: TerritoryOperation | undefined, layer: Layer) =>
  layer === 'activities' ? (row?.activities ?? 0) : (row?.needs_open ?? 0);
const boundsOf = (features: Feature[]): [[number, number], [number, number]] | null => {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === 'number' && typeof value[1] === 'number') {
      minX = Math.min(minX, value[0]);
      maxX = Math.max(maxX, value[0]);
      minY = Math.min(minY, value[1]);
      maxY = Math.max(maxY, value[1]);
      return;
    }
    value.forEach(visit);
  };
  features.forEach((feature) => visit((feature.geometry as { coordinates?: unknown }).coordinates));
  return Number.isFinite(minX)
    ? [
        [minX, minY],
        [maxX, maxY],
      ]
    : null;
};

export function CommandCenterMap({
  campaignId,
  parishes,
  operations,
  cantonName,
}: {
  campaignId: string;
  parishes: ElectionMapParish[];
  operations: TerritoryOperation[];
  cantonName?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import('maplibre-gl').Map | undefined>(undefined);
  const popupRef = useRef<import('maplibre-gl').Popup | undefined>(undefined);
  const [layer, setLayer] = useState<Layer>('activities');
  const [boundaries, setBoundaries] = useState<Collection>();
  const [cantonBoundaries, setCantonBoundaries] = useState<Collection>();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [selectedId, setSelectedId] = useState<number>();
  useEffect(() => {
    let active = true;
    setStatus('loading');
    Promise.all([
      apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=PARISH&limit=5000`),
      // The canton outline is a hierarchy cue, not the operative unit: if it
      // fails or isn't imported yet, the parish map must still render.
      apiRequest<Collection>(`/campaigns/${campaignId}/map/boundaries?level=CANTON`).catch(
        () => ({ type: 'FeatureCollection', features: [] }) as Collection,
      ),
    ])
      .then(([parishData, cantonData]) => {
        // A successful response always mounts the basemap, whether or not it
        // contains any officially-imported boundary — the map must never
        // depend on official geometry existing just to render.
        if (active) {
          setBoundaries(parishData);
          setCantonBoundaries(cantonData);
          setStatus('success');
        }
      })
      .catch(() => active && setStatus('error'));
    return () => {
      active = false;
    };
  }, [campaignId]);
  const byId = useMemo(() => new Map(operations.map((row) => [row.parish_id, row])), [operations]);
  const byDpa = useMemo(
    () => new Map(parishes.map((row) => [String(row.dpa_code), row])),
    [parishes],
  );
  const officialFeatures = useMemo(
    () => boundaries?.features.filter(isOfficialBoundary) ?? [],
    [boundaries],
  );
  const officialCantonFeatures = useMemo(
    () => cantonBoundaries?.features.filter(isOfficialBoundary) ?? [],
    [cantonBoundaries],
  );
  const hasOfficialBoundaries = officialFeatures.length > 0;
  const selected = parishes.find((row) => row.parish_id === selectedId);
  const selectedOps = selected ? byId.get(selected.parish_id) : undefined;

  // Geometry (limits) and operational state (color) are two separate
  // concerns: this only recomputes the fill-driving `operation_count`
  // property, never the layer/paint definitions.
  const parishData: Collection = useMemo(
    () => ({
      type: 'FeatureCollection',
      features: officialFeatures.map((feature, index) => {
        const code = String(feature.properties.parish_dpa ?? feature.properties.code ?? '');
        const parish = byDpa.get(code);
        const count = countFor(parish ? byId.get(parish.parish_id) : undefined, layer);
        return {
          ...feature,
          id: feature.id ?? index,
          properties: {
            ...feature.properties,
            parish_id: parish?.parish_id,
            parish_name: parish?.name ?? feature.properties.name,
            operation_count: count,
          },
        };
      }),
    }),
    [officialFeatures, byDpa, byId, layer],
  );

  // Creates the map and its layers exactly once per successful load. Toggling
  // ACTIVIDADES/NECESIDADES must never re-run this — see the effect below,
  // which only pushes new data into the existing source.
  useEffect(() => {
    if (status !== 'success' || !container.current) return;
    let disposed = false;
    let map: import('maplibre-gl').Map | undefined;
    // Only official geometry may set the viewport; without it, fall back to a
    // fixed, non-placeholder view instead of MapLibre's default [0,0].
    const bounds = boundsOf(parishData.features);
    import('maplibre-gl')
      .then(({ Map, NavigationControl, Popup }) => {
        if (disposed || !container.current) return;
        map = new Map({
          container: container.current,
          style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json',
          scrollZoom: false,
          ...(bounds
            ? { bounds, fitBoundsOptions: { padding: 28 } }
            : { center: TERRITORIAL_FALLBACK_CENTER, zoom: TERRITORIAL_FALLBACK_ZOOM }),
        });
        map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
        map.on('load', () => {
          if (!map) return;
          mapRef.current = map;
          // 1) canton outline — a hierarchy cue, stroke only, never a fill
          // that would sit on top of the parishes it contains.
          if (officialCantonFeatures.length) {
            map.addSource('canton-boundary', {
              type: 'geojson',
              data: { type: 'FeatureCollection', features: officialCantonFeatures } as never,
            });
            map.addLayer({
              id: 'canton-boundary-line',
              type: 'line',
              source: 'canton-boundary',
              paint: {
                'line-color': '#1e4e52',
                'line-width': 2.5,
                'line-dasharray': [2, 1.5],
              },
            });
          }
          if (parishData.features.length === 0) return;
          // 2) parish fill — represents operational presence, not the
          // boundary itself: near-transparent where there is no activity so
          // the basemap (streets, names) stays legible underneath.
          map.addSource('command-center', { type: 'geojson', data: parishData as never });
          map.addLayer({
            id: 'command-center-fill',
            type: 'fill',
            source: 'command-center',
            paint: {
              'fill-color': ['case', ['>', ['get', 'operation_count'], 0], '#5b7c99', '#dbe4ea'],
              'fill-opacity': ['case', ['>', ['get', 'operation_count'], 0], 0.42, 0.06],
            },
          });
          // 3) parish outline — the actual limit, drawn last so it stays
          // crisp over the operational fill.
          map.addLayer({
            id: 'command-center-outline',
            type: 'line',
            source: 'command-center',
            paint: { 'line-color': '#33474f', 'line-width': 1.2, 'line-opacity': 0.85 },
          });
          map.on('click', 'command-center-fill', (event) => {
            const id = Number(event.features?.[0]?.properties?.parish_id);
            if (Number.isFinite(id)) setSelectedId(id);
          });
          // A single, reusable Popup instance — hover only ever moves it and
          // rewrites its text, it is never recreated per pixel of movement.
          const popup = new Popup({
            closeButton: false,
            closeOnClick: false,
            className: 'command-center-tooltip',
          });
          popupRef.current = popup;
          map.on('mouseenter', 'command-center-fill', () => {
            if (map) map.getCanvas().style.cursor = 'pointer';
          });
          map.on('mousemove', 'command-center-fill', (event) => {
            const name = event.features?.[0]?.properties?.parish_name;
            if (!map || typeof name !== 'string' || !name) return;
            popup.setLngLat(event.lngLat).setText(name).addTo(map);
          });
          map.on('mouseleave', 'command-center-fill', () => {
            if (map) map.getCanvas().style.cursor = '';
            popup.remove();
          });
        });
      })
      .catch(() => setStatus('error'));
    return () => {
      disposed = true;
      mapRef.current = undefined;
      popupRef.current?.remove();
      popupRef.current = undefined;
      map?.remove();
    };
    // Only the initial official geometry (parish + canton) and a successful
    // load should recreate the map/layers. `parishData` on later renders
    // (layer toggles, operations refresh) is pushed via setData below instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, officialCantonFeatures]);

  // Toggling ACTIVIDADES/NECESIDADES (or a fresh operations snapshot) updates
  // the existing GeoJSON source in place — it must never add another layer.
  useEffect(() => {
    const source = mapRef.current?.getSource('command-center') as
      | import('maplibre-gl').GeoJSONSource
      | undefined;
    source?.setData(parishData as never);
  }, [parishData]);

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, overflow: 'hidden', borderRadius: 4 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Box
            sx={{
              width: 38,
              height: 38,
              borderRadius: 2.5,
              display: 'grid',
              placeItems: 'center',
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              flexShrink: 0,
            }}
          >
            <MapOutlinedIcon sx={{ fontSize: 20 }} />
          </Box>
          <Box>
            <Typography variant="overline" color="text.secondary">
              MAPA OPERATIVO
            </Typography>
            <Typography component="h2" variant="h2">
              Territorio en operación
            </Typography>
            {cantonName && (
              <Typography variant="body2" color="text.secondary">
                Parroquias del cantón {cantonName}
              </Typography>
            )}
          </Box>
        </Stack>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={layer}
          onChange={(_, value: Layer | null) => value && setLayer(value)}
          aria-label="Capas operativas"
          sx={{
            alignSelf: { xs: 'stretch', md: 'center' },
            '& .MuiToggleButton-root': { flex: 1 },
          }}
        >
          {(Object.keys(layerLabels) as Layer[]).map((key) => (
            <ToggleButton key={key} value={key}>
              {layerLabels[key]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>
      {status === 'loading' && (
        <Box sx={{ height: 390, mt: 2, bgcolor: 'action.hover', borderRadius: 2 }} />
      )}
      {status === 'error' && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          No fue posible cargar el mapa territorial.
        </Alert>
      )}
      {status === 'success' && !hasOfficialBoundaries && (
        <Alert severity="info" sx={{ mt: 2 }}>
          Esta campaña todavía no tiene límites territoriales oficiales importados. Importa la
          geometría desde Centro de Datos &gt; Límites territoriales.
        </Alert>
      )}
      <Box
        ref={container}
        role="region"
        aria-label="Mapa operativo territorial"
        sx={{
          display: status === 'success' ? 'block' : 'none',
          height: { xs: 340, md: 480 },
          mt: 2,
          borderRadius: 2,
          overflow: 'hidden',
        }}
      />
      <Stack direction="row" gap={1} alignItems="center" sx={{ mt: 1 }}>
        <Chip size="small" label="Con registros" sx={{ bgcolor: '#5b7c99', color: '#fff' }} />
        <Chip size="small" label="Sin registros" />
        <Typography variant="caption" color="text.secondary">
          La capa representa presencia operativa, no desempeño electoral.
        </Typography>
      </Stack>
      {selected && (
        <Box sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 2 }}>
          <Typography variant="h3">{selected.name}</Typography>
          <Stack direction="row" gap={2} flexWrap="wrap" sx={{ my: 1 }}>
            <span>
              Actividades: <b>{selectedOps?.activities ?? 0}</b>
            </span>
            <span>
              Necesidades: <b>{selectedOps?.needs_open ?? 0}</b>
            </span>
            <span>
              Padrón: <b>{selected.registered_voters_current.toLocaleString('es-EC')}</b>
            </span>
            {typeof selected.demographics?.POP_TOTAL === 'number' && (
              <span>
                Población: <b>{selected.demographics.POP_TOTAL.toLocaleString('es-EC')}</b>
              </span>
            )}
          </Stack>
          <Button
            component={RouterLink}
            to={`/app/campaigns/${campaignId}/territories/${selected.parish_id}`}
            sx={{ textTransform: 'none' }}
          >
            Ver expediente territorial
          </Button>
        </Box>
      )}
    </Paper>
  );
}
