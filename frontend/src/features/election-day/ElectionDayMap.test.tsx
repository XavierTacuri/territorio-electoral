import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ElectionDayMap } from './ElectionDayMap';
import type { ElectionDayIncident, PollingPlace } from './types';

const addTo = vi.fn();
const markerEls: HTMLElement[] = [];
vi.mock('maplibre-gl', () => ({
  NavigationControl: class {},
  Marker: class {
    element: HTMLElement;
    constructor(opts: { element: HTMLElement }) {
      this.element = opts.element;
      markerEls.push(opts.element);
    }
    setLngLat() {
      return this;
    }
    addTo(...args: unknown[]) {
      addTo(...args);
      return this;
    }
    remove() {}
  },
  Map: class {
    addControl() {}
    fitBounds() {}
    remove() {}
  },
}));

function place(overrides: Partial<PollingPlace>): PollingPlace {
  return {
    id: 'p1',
    electoral_process_id: 'proc-1',
    province_id: 1,
    canton_id: 1,
    parish_id: 1,
    official_code: 'R-001',
    name: 'Escuela Central',
    address: null,
    latitude: -2.9,
    longitude: -78.8,
    is_active: true,
    ...overrides,
  };
}

describe('ElectionDayMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    markerEls.length = 0;
  });

  it('muestra aviso cuando ningún recinto tiene coordenadas', () => {
    render(
      <ElectionDayMap
        places={[place({ id: 'p1', latitude: null, longitude: null })]}
        coveredIds={new Set()}
        checkedInIds={new Set()}
        incidents={[]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Ubicación cartográfica no disponible.')).toBeVisible();
  });

  it('muestra la leyenda con los cuatro estados posibles', () => {
    render(
      <ElectionDayMap
        places={[place({})]}
        coveredIds={new Set()}
        checkedInIds={new Set()}
        incidents={[]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Sin asignación')).toBeVisible();
    expect(screen.getByText('Asignado')).toBeVisible();
    expect(screen.getByText('Presencia confirmada')).toBeVisible();
    expect(screen.getByText('Con incidencia')).toBeVisible();
  });

  it('avisa cuántos recintos quedan fuera del mapa por no tener ubicación', () => {
    render(
      <ElectionDayMap
        places={[place({ id: 'p1' }), place({ id: 'p2', latitude: null, longitude: null })]}
        coveredIds={new Set()}
        checkedInIds={new Set()}
        incidents={[]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/1 recinto\(s\) sin ubicación cartográfica disponible/)).toBeVisible();
  });

  it('crea un marcador por recinto con coordenadas y una etiqueta accesible según su estado', async () => {
    render(
      <ElectionDayMap
        places={[place({ id: 'p1' })]}
        coveredIds={new Set(['p1'])}
        checkedInIds={new Set()}
        incidents={[]}
        onSelect={vi.fn()}
      />,
    );
    await vi.waitFor(() => expect(markerEls.length).toBe(1));
    expect(markerEls[0].getAttribute('aria-label')).toBe('Escuela Central: Asignado');
  });

  it('marca un recinto como con incidencia cuando tiene una incidencia sin resolver', async () => {
    const incident: ElectionDayIncident = {
      id: 'inc-1',
      operation_id: 'op1',
      polling_place_id: 'p1',
      board_id: null,
      reported_by_user_id: 'u1',
      category: 'LOGISTICS',
      description: 'Falta material',
      status: 'OPEN',
      reported_at: '2027-03-14T11:00:00Z',
      resolved_at: null,
      resolution_notes: null,
    };
    render(
      <ElectionDayMap
        places={[place({ id: 'p1' })]}
        coveredIds={new Set(['p1'])}
        checkedInIds={new Set(['p1'])}
        incidents={[incident]}
        onSelect={vi.fn()}
      />,
    );
    await vi.waitFor(() => expect(markerEls.length).toBe(1));
    expect(markerEls[0].getAttribute('aria-label')).toBe('Escuela Central: Con incidencia');
  });
});
