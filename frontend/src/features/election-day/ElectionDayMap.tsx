import { useEffect, useRef } from 'react';
import { Alert, Box, Chip, Paper, Stack, Typography } from '@mui/material';
import type { ElectionDayIncident, PollingPlace } from './types';

type PlaceStatus = 'UNASSIGNED' | 'ASSIGNED' | 'CHECKED_IN' | 'INCIDENT';

const STATUS_COLOR: Record<PlaceStatus, string> = {
  UNASSIGNED: '#9aa5b1',
  ASSIGNED: '#5b7c99',
  CHECKED_IN: '#2f9e6b',
  INCIDENT: '#c0562b',
};

const STATUS_LABEL: Record<PlaceStatus, string> = {
  UNASSIGNED: 'Sin asignación',
  ASSIGNED: 'Asignado',
  CHECKED_IN: 'Presencia confirmada',
  INCIDENT: 'Con incidencia',
};

function placeStatus(
  place: PollingPlace,
  coveredIds: Set<string>,
  checkedInIds: Set<string>,
  incidentIds: Set<string>,
): PlaceStatus {
  if (incidentIds.has(place.id)) return 'INCIDENT';
  if (checkedInIds.has(place.id)) return 'CHECKED_IN';
  if (coveredIds.has(place.id)) return 'ASSIGNED';
  return 'UNASSIGNED';
}

export function ElectionDayMap({
  places,
  coveredIds,
  checkedInIds,
  incidents,
  onSelect,
}: {
  places: PollingPlace[];
  coveredIds: Set<string>;
  checkedInIds: Set<string>;
  incidents: ElectionDayIncident[];
  onSelect: (place: PollingPlace) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const withCoords = places.filter((p) => p.latitude != null && p.longitude != null);
  const withoutCoords = places.filter((p) => p.latitude == null || p.longitude == null);
  const incidentIds = new Set(
    incidents.filter((i) => i.status !== 'RESOLVED').map((i) => i.polling_place_id),
  );

  useEffect(() => {
    if (!container.current || withCoords.length === 0) return;
    let disposed = false;
    let map: import('maplibre-gl').Map | undefined;
    const markers: import('maplibre-gl').Marker[] = [];
    import('maplibre-gl')
      .then(({ Map, NavigationControl, Marker }) => {
        if (disposed || !container.current) return;
        map = new Map({
          container: container.current,
          style: import.meta.env.VITE_MAP_STYLE_URL || '/map-style.json',
          center: [withCoords[0].longitude as number, withCoords[0].latitude as number],
          zoom: 11,
          scrollZoom: false,
        });
        map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
        for (const place of withCoords) {
          const status = placeStatus(place, coveredIds, checkedInIds, incidentIds);
          const el = document.createElement('div');
          el.style.width = '16px';
          el.style.height = '16px';
          el.style.borderRadius = '50%';
          el.style.border = '2px solid #fff';
          el.style.boxShadow = '0 0 0 1px rgba(0,0,0,0.2)';
          el.style.backgroundColor = STATUS_COLOR[status];
          el.style.cursor = 'pointer';
          el.setAttribute('role', 'button');
          el.setAttribute('aria-label', `${place.name}: ${STATUS_LABEL[status]}`);
          el.addEventListener('click', () => onSelect(place));
          const marker = new Marker({ element: el })
            .setLngLat([place.longitude as number, place.latitude as number])
            .addTo(map);
          markers.push(marker);
        }
        if (withCoords.length > 1) {
          const lngs = withCoords.map((p) => p.longitude as number);
          const lats = withCoords.map((p) => p.latitude as number);
          map.fitBounds(
            [
              [Math.min(...lngs), Math.min(...lats)],
              [Math.max(...lngs), Math.max(...lats)],
            ],
            { padding: 40, duration: 0 },
          );
        }
      })
      .catch(() => {});
    return () => {
      disposed = true;
      markers.forEach((m) => m.remove());
      map?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [places, incidents]);

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, overflow: 'hidden' }}>
      <Typography variant="overline" color="text.secondary">
        MAPA OPERATIVO
      </Typography>
      <Typography component="h2" variant="h2" sx={{ mb: 1 }}>
        Recintos electorales
      </Typography>
      {withCoords.length === 0 ? (
        <Alert severity="info">Ubicación cartográfica no disponible.</Alert>
      ) : (
        <Box
          ref={container}
          role="region"
          aria-label="Mapa operativo de recintos"
          sx={{ height: { xs: 320, md: 440 }, borderRadius: 2, overflow: 'hidden' }}
        />
      )}
      <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 1.5 }}>
        {(Object.keys(STATUS_LABEL) as PlaceStatus[]).map((status) => (
          <Chip
            key={status}
            size="small"
            label={STATUS_LABEL[status]}
            sx={{ bgcolor: STATUS_COLOR[status], color: '#fff' }}
          />
        ))}
      </Stack>
      {withoutCoords.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {withoutCoords.length} recinto(s) sin ubicación cartográfica disponible (siguen visibles
          en la lista y la matriz).
        </Typography>
      )}
    </Paper>
  );
}
