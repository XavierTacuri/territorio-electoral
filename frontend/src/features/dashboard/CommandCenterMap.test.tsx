import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import { CommandCenterMap } from './CommandCenterMap';
import { TERRITORIAL_FALLBACK_CENTER, TERRITORIAL_FALLBACK_ZOOM } from './mapFallbackCenter';

vi.mock('../../api/client', () => ({ apiRequest: vi.fn() }));
const addSource = vi.fn();
const addLayer = vi.fn();
const setData = vi.fn();
const mapOptions = vi.fn();
const onSpy = vi.fn();
const popupOptions = vi.fn();
const popupSetLngLat = vi.fn();
const popupSetText = vi.fn();
const popupAddTo = vi.fn();
const popupRemove = vi.fn();
const sourceIds = new Set<string>();
// event:layer -> handler, so tests can simulate a hover/leave the same way
// MapLibre would dispatch it.
const handlers = new Map<string, (event: unknown) => void>();
vi.mock('maplibre-gl', () => ({
  NavigationControl: class {},
  Popup: class {
    constructor(options: unknown) {
      popupOptions(options);
    }
    setLngLat(...args: unknown[]) {
      popupSetLngLat(...args);
      return this;
    }
    setText(...args: unknown[]) {
      popupSetText(...args);
      return this;
    }
    addTo(...args: unknown[]) {
      popupAddTo(...args);
      return this;
    }
    remove() {
      popupRemove();
    }
  },
  Map: class {
    constructor(options: unknown) {
      mapOptions(options);
    }
    addControl() {}
    addSource(id: string, ...rest: unknown[]) {
      sourceIds.add(id);
      addSource(id, ...rest);
    }
    getSource(id: string) {
      return sourceIds.has(id) ? { setData } : undefined;
    }
    addLayer(...args: unknown[]) {
      addLayer(...args);
    }
    fitBounds() {}
    getCanvas() {
      return { style: {} };
    }
    remove() {}
    on(event: string, layerOrCallback: unknown, callback?: (event: unknown) => void) {
      onSpy(event, layerOrCallback);
      if (event === 'load') {
        (typeof layerOrCallback === 'function' ? layerOrCallback : callback)?.(undefined);
        return;
      }
      handlers.set(`${event}:${layerOrCallback as string}`, callback!);
    }
  },
}));

const parish = {
  parish_id: 1,
  dpa_code: '010353',
  name: 'Jadán',
  registered_voters_current: 100,
  historical_2019: { turnout_rate: 0.6 },
  historical_2023: { turnout_rate: 0.6 },
  projection: { low: 0.6, central: 0.6, high: 0.6, expected_voters_central: 60 },
  data_quality_status: 'HIGH',
} as never;

const square = (x: number, y: number) => [
  [
    [x, y],
    [x + 0.8, y],
    [x + 0.8, y + 0.8],
    [x, y],
  ],
];

const placeholderFeature = {
  type: 'Feature' as const,
  id: 1,
  geometry: { type: 'MultiPolygon', coordinates: [square(0, 0)] },
  properties: { code: '010353', name: 'Jadán', geometry_source: 'SYNTHETIC_PLACEHOLDER' },
};
const officialParishFeature = {
  type: 'Feature' as const,
  id: 2,
  geometry: {
    type: 'MultiPolygon',
    coordinates: [
      [
        [-78.79, -2.9],
        [-78.77, -2.9],
        [-78.77, -2.88],
        [-78.79, -2.9],
      ],
    ],
  },
  properties: { code: '010353', name: 'Jadán', geometry_source: 'OFFICIAL_IMPORT' },
};
const officialCantonFeature = {
  type: 'Feature' as const,
  id: 3,
  geometry: {
    type: 'MultiPolygon',
    coordinates: [
      [
        [-78.9, -3.0],
        [-78.6, -3.0],
        [-78.6, -2.7],
        [-78.9, -3.0],
      ],
    ],
  },
  properties: { code: '0103', name: 'Gualaceo', geometry_source: 'OFFICIAL_IMPORT' },
};

function mockBoundaries(parishFeatures: unknown[], cantonFeatures: unknown[] = []) {
  vi.mocked(apiRequest).mockImplementation((path: string) => {
    const features = path.includes('level=CANTON') ? cantonFeatures : parishFeatures;
    return Promise.resolve({ type: 'FeatureCollection', features });
  });
}

function hover(name: string) {
  handlers.get('mousemove:command-center-fill')?.({
    lngLat: { lng: -78.78, lat: -2.89 },
    features: [{ properties: { parish_name: name } }],
  });
}

function leave() {
  handlers.get('mouseleave:command-center-fill')?.(undefined);
}

describe('CommandCenterMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sourceIds.clear();
    handlers.clear();
  });

  it('nunca renderiza geometría SYNTHETIC_PLACEHOLDER ni la usa para el viewport, pero mantiene el basemap', async () => {
    mockBoundaries([placeholderFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() => expect(mapOptions).toHaveBeenCalled());
    expect(addSource).not.toHaveBeenCalled();
    expect(mapOptions).toHaveBeenCalledWith(
      expect.objectContaining({
        center: TERRITORIAL_FALLBACK_CENTER,
        zoom: TERRITORIAL_FALLBACK_ZOOM,
      }),
    );
    expect(mapOptions.mock.calls[0][0]).not.toHaveProperty('bounds');
    expect(
      await screen.findByText(/todavía no tiene límites territoriales oficiales importados/),
    ).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Mapa operativo territorial' })).toBeVisible();
  });

  it('renderiza y ajusta el viewport solo con geometría de parroquia OFFICIAL_IMPORT', async () => {
    mockBoundaries([officialParishFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() =>
      expect(addSource).toHaveBeenCalledWith('command-center', expect.anything()),
    );
    expect(mapOptions.mock.calls[0][0]).toHaveProperty('bounds');
    expect(
      screen.queryByText(/todavía no tiene límites territoriales oficiales importados/),
    ).not.toBeInTheDocument();
  });

  it('dibuja el límite cantonal solo como contorno (sin fill) y solo si hay geometría oficial de cantón', async () => {
    mockBoundaries([officialParishFeature], [officialCantonFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() =>
      expect(addSource).toHaveBeenCalledWith('canton-boundary', expect.anything()),
    );
    const cantonLayer = addLayer.mock.calls
      .map((call) => call[0])
      .find((l) => l.source === 'canton-boundary');
    expect(cantonLayer).toMatchObject({ type: 'line' });
    expect(
      addLayer.mock.calls.some(
        (call) => call[0].source === 'canton-boundary' && call[0].type === 'fill',
      ),
    ).toBe(false);
  });

  it('la geometría (límites) y el estado operativo (relleno) son capas separadas: sin registros usa fill-opacity muy baja', async () => {
    mockBoundaries([officialParishFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() => expect(addLayer).toHaveBeenCalled());
    const fillLayer = addLayer.mock.calls
      .map((call) => call[0])
      .find((l) => l.id === 'command-center-fill');
    const outlineLayer = addLayer.mock.calls
      .map((call) => call[0])
      .find((l) => l.id === 'command-center-outline');
    expect(fillLayer.paint['fill-opacity']).toEqual([
      'case',
      ['>', ['get', 'operation_count'], 0],
      0.42,
      0.06,
    ]);
    expect(outlineLayer.type).toBe('line');
  });

  it('alternar ACTIVIDADES/NECESIDADES actualiza el source existente (setData) sin agregar layers ni listeners nuevos', async () => {
    mockBoundaries([officialParishFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() => expect(addLayer).toHaveBeenCalled());
    const layerCountAfterLoad = addLayer.mock.calls.length;
    const sourceCountAfterLoad = addSource.mock.calls.length;
    const onCountAfterLoad = onSpy.mock.calls.length;

    screen.getByRole('button', { name: 'Necesidades' }).click();
    await waitFor(() => expect(setData).toHaveBeenCalled());
    screen.getByRole('button', { name: 'Actividades' }).click();
    await waitFor(() => expect(setData).toHaveBeenCalledTimes(2));

    expect(addLayer.mock.calls.length).toBe(layerCountAfterLoad);
    expect(addSource.mock.calls.length).toBe(sourceCountAfterLoad);
    expect(onSpy.mock.calls.length).toBe(onCountAfterLoad);
  });

  it('un refresco de datos operativos (con/sin registros) no duplica listeners de hover', async () => {
    mockBoundaries([officialParishFeature]);
    const { rerender } = render(
      <CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />,
    );
    await waitFor(() => expect(addLayer).toHaveBeenCalled());
    const onCountAfterLoad = onSpy.mock.calls.length;

    rerender(
      <CommandCenterMap
        campaignId="c"
        parishes={[parish]}
        operations={[
          {
            parish_id: 1,
            activities: 3,
            needs_open: 1,
            commitments_pending: 0,
            commitments_completed: 0,
          },
        ]}
      />,
    );
    await waitFor(() => expect(setData).toHaveBeenCalled());
    expect(onSpy.mock.calls.length).toBe(onCountAfterLoad);
  });

  it('hover sobre una parroquia muestra su nombre real y mouseleave lo retira', async () => {
    mockBoundaries([officialParishFeature]);
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    await waitFor(() => expect(addLayer).toHaveBeenCalled());

    hover('Jadán');
    expect(popupSetText).toHaveBeenCalledWith('Jadán');
    expect(popupAddTo).toHaveBeenCalled();

    hover('San Juan');
    expect(popupSetText).toHaveBeenLastCalledWith('San Juan');
    // Same reusable popup instance throughout — never recreated per move.
    expect(popupOptions).toHaveBeenCalledTimes(1);

    leave();
    expect(popupRemove).toHaveBeenCalled();
  });

  it('muestra error visible sin ocultar la lógica de reintento', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new Error('network'));
    render(<CommandCenterMap campaignId="c" parishes={[parish]} operations={[]} />);
    expect(
      await screen.findByText('No fue posible cargar el mapa territorial.'),
    ).toBeInTheDocument();
  });
});
