import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { PageHeader } from '../components/layout/PageHeader';
type GeoJSON = { type: 'FeatureCollection'; features: any[] };
const LAYERS = [
  ['boundaries?level=PARISH', 'Parroquias', 'fill'],
  ['communities', 'Comunidades', 'circle'],
  ['activities?cluster=true', 'Actividades', 'circle'],
  ['needs', 'Necesidades', 'fill'],
  ['commitments', 'Compromisos', 'fill'],
] as const;
export default function MapPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const container = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState<string[]>(['boundaries?level=PARISH']);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('');
  const operational = location.pathname.includes('/operations/map');
  const style = import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json';
  useEffect(() => {
    if (!style || !container.current) return;
    let map: import('maplibre-gl').Map | undefined;
    let cancelled = false;
    import('maplibre-gl')
      .then(({ Map, NavigationControl }) => {
        if (!container.current || cancelled) return;
        map = new Map({
          container: container.current,
          style,
          center: [-78.78, -2.89],
          zoom: 10,
          scrollZoom: false,
        });
        map.addControl(new NavigationControl(), 'top-right');
        map.on('load', async () => {
          for (const [path, , kind] of LAYERS.filter((x) => enabled.includes(x[0]))) {
            try {
              const data = await apiRequest<GeoJSON>(
                `/campaigns/${campaignId}/map/${path}${path.includes('?') ? '&' : '?'}limit=5000${path === 'needs' && category ? `&need_category_code=${category}` : ''}`,
              );
              const id = 'te-' + path.replace(/[^a-z]/gi, '-');
              map?.addSource(id, { type: 'geojson', data, cluster: kind === 'circle' });
              map?.addLayer(
                kind === 'fill'
                  ? {
                      id,
                      type: 'fill',
                      source: id,
                      paint: {
                        'fill-color': '#557a83',
                        'fill-opacity': 0.3,
                        'fill-outline-color': '#263238',
                      },
                    }
                  : {
                      id,
                      type: 'circle',
                      source: id,
                      paint: {
                        'circle-radius': 6,
                        'circle-color': '#355c67',
                        'circle-stroke-color': '#fff',
                        'circle-stroke-width': 1,
                      },
                    },
              );
              if (path === 'boundaries?level=PARISH') {
                map?.on('mouseenter', id, () => {
                  if (map) map.getCanvas().style.cursor = 'pointer';
                });
                map?.on('mouseleave', id, () => {
                  if (map) map.getCanvas().style.cursor = '';
                });
                map?.on('click', id, (event) => {
                  const parishId = event.features?.[0]?.properties?.resource_id;
                  if (parishId) navigate(`/app/campaigns/${campaignId}/territories/${parishId}`);
                });
              }
              if (path === 'needs')
                map?.on('click', id, (event) => {
                  const parishId = event.features?.[0]?.properties?.resource_id;
                  if (parishId)
                    navigate(`/app/campaigns/${campaignId}/needs?parish_id=${parishId}`);
                });
            } catch {
              setError('Una o más capas no pudieron cargarse.');
            }
          }
        });
      })
      .catch(() => setError('No se pudo cargar el mapa.'));
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [style, campaignId, enabled, navigate, category]);
  return (
    <>
      <PageHeader
        title={operational ? 'Mapa operacional' : 'Mapas territoriales'}
        description="Geometrías oficiales y datos agregados; nunca ubicaciones individuales."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        {operational && (
          <TextField
            select
            label="Categoría de necesidades"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setEnabled((v) => (v.includes('needs') ? v : [...v, 'needs']));
            }}
            sx={{ minWidth: 260, mb: 2 }}
          >
            <MenuItem value="">Todas las categorías</MenuItem>
            <MenuItem value="ROADS">Vialidad</MenuItem>
            <MenuItem value="DRINKING_WATER">Agua y saneamiento</MenuItem>
            <MenuItem value="SECURITY">Seguridad</MenuItem>
            <MenuItem value="HEALTH">Salud</MenuItem>
            <MenuItem value="EDUCATION">Educación</MenuItem>
            <MenuItem value="ENVIRONMENT">Ambiente</MenuItem>
            <MenuItem value="CONNECTIVITY">Conectividad</MenuItem>
          </TextField>
        )}
        <Stack direction={{ xs: 'column', md: 'row' }} flexWrap="wrap">
          {LAYERS.map(([path, name]) => (
            <FormControlLabel
              key={path}
              control={
                <Switch
                  checked={enabled.includes(path)}
                  onChange={(e) =>
                    setEnabled((v) =>
                      e.target.checked ? [...v, path] : v.filter((x) => x !== path),
                    )
                  }
                />
              }
              label={name}
            />
          ))}
        </Stack>
        <Stack direction="row" gap={1} flexWrap="wrap" aria-label="Leyenda del mapa" sx={{ mt: 1 }}>
          <Typography fontWeight={700}>Leyenda:</Typography>
          {LAYERS.filter((x) => enabled.includes(x[0])).map(([path, name]) => (
            <Chip key={path} size="small" label={name} />
          ))}
        </Stack>
      </Paper>
      {!style ? (
        <Alert severity="info">
          Configure VITE_MAP_STYLE_URL para visualizar el mapa. No se inventan geometrías ni
          centroides.
        </Alert>
      ) : (
        <>
          {error && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <Box
            ref={container}
            role="region"
            aria-label="Mapa territorial"
            sx={{ height: { xs: 440, md: 640 }, borderRadius: 2, overflow: 'hidden' }}
          />
        </>
      )}
    </>
  );
}
