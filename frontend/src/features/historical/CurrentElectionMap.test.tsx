import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import { CurrentElectionMap, type ElectionMapParish } from './CurrentElectionMap';

vi.mock('../../api/client', () => ({ apiRequest: vi.fn() }));
const addSource = vi.fn();
const mapOptions = vi.fn();
vi.mock('maplibre-gl', () => ({
  NavigationControl: class {},
  Popup: class {
    setLngLat() {
      return this;
    }
    setHTML() {
      return this;
    }
    remove() {}
    addTo() {
      return this;
    }
  },
  Map: class {
    constructor(options: unknown) {
      mapOptions(options);
    }
    addControl() {}
    addSource(...args: unknown[]) {
      addSource(...args);
    }
    addLayer() {}
    getPaintProperty() {
      return ['step'];
    }
    getZoom() {
      return 10;
    }
    fitBounds() {}
    setFeatureState() {}
    remove() {}
    on(event: string, _layer: unknown, callback?: () => void) {
      if (event === 'load') (typeof _layer === 'function' ? _layer : callback)?.();
    }
  },
}));

const parish: ElectionMapParish = {
  parish_id: 1,
  dpa_code: '010350',
  name: 'Gualaceo',
  registered_voters_current: 100,
  historical_2019: { turnout_rate: 0.68 },
  historical_2023: { turnout_rate: 0.72 },
  projection: { low: 0.68, central: 0.706, high: 0.72, expected_voters_central: 71 },
  data_quality_status: 'HIGH',
};
const feature = {
  type: 'Feature' as const,
  id: 1,
  geometry: {
    type: 'MultiPolygon',
    coordinates: [
      [
        [
          [-78.8, -2.9],
          [-78.7, -2.9],
          [-78.7, -2.8],
          [-78.8, -2.9],
        ],
      ],
    ],
  },
  properties: { code: '010350', name: 'Gualaceo' },
};

describe('CurrentElectionMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it('se monta, muestra loading y solicita boundaries con el campaignId', async () => {
    vi.mocked(apiRequest).mockReturnValue(new Promise(() => {}));
    render(
      <CurrentElectionMap campaignId="campaign-real" parishes={[parish]} onSelect={vi.fn()} />,
    );
    expect(screen.getByText('Cargando mapa territorial…')).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith(
      '/campaigns/campaign-real/map/boundaries?level=PARISH&limit=5000',
    );
  });
  it('muestra error visible', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new Error('network'));
    render(<CurrentElectionMap campaignId="c" parishes={[parish]} onSelect={vi.fn()} />);
    expect(
      await screen.findByText('No fue posible cargar el mapa territorial.'),
    ).toBeInTheDocument();
  });
  it('muestra estado vacío', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ type: 'FeatureCollection', features: [] });
    render(<CurrentElectionMap campaignId="c" parishes={[parish]} onSelect={vi.fn()} />);
    expect(
      await screen.findByText('No existen geometrías parroquiales disponibles.'),
    ).toBeInTheDocument();
  });
  it('fusiona por DPA y monta el source MapLibre', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ type: 'FeatureCollection', features: [feature] });
    render(<CurrentElectionMap campaignId="c" parishes={[parish]} onSelect={vi.fn()} />);
    await waitFor(() => expect(addSource).toHaveBeenCalled());
    const source = addSource.mock.calls[0][1] as {
      data: { features: Array<{ properties: Record<string, unknown> }> };
    };
    expect(source.data.features[0].properties).toMatchObject({
      parish_dpa: '010350',
      registered_voters_current: 100,
      projected_central_rate: 0.706,
    });
    expect(screen.getByRole('region', { name: 'Mapa de elección actual' })).toHaveStyle({
      minHeight: '480px',
    });
    expect(screen.getByLabelText('Leyenda — Participación estimada')).toBeVisible();
    expect(mapOptions).toHaveBeenCalledWith(expect.objectContaining({ scrollZoom: false }));
  });
});
