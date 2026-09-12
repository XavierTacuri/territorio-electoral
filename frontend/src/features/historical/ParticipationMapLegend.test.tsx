import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  buildMetricScale,
  CurrentElectionMapLegend,
  mapLibreColorExpression,
  PARTICIPATION_COLORS,
} from './ParticipationMapLegend';

describe('CurrentElectionMapLegend', () => {
  it('mantiene la escala fija de participación central', () => {
    const scale = buildMetricScale(
      'projected_central_rate',
      'Participación central',
      'percent',
      [0.66, 0.7, 0.74],
    );
    expect(scale.stops).toEqual([
      { value: 0.67, color: '#8DB9D3' },
      { value: 0.69, color: '#4C86A8' },
      { value: 0.71, color: '#1D5F87' },
      { value: 0.73, color: '#0B3C5D' },
    ]);
    expect(scale.noDataColor).toBe('#E5E7EB');
    render(<CurrentElectionMapLegend scale={scale} />);
    expect(screen.getByLabelText('Leyenda — Participación central')).toBeVisible();
    expect(screen.getByText('Muy alta')).toBeVisible();
  });
  it('comparte los mismos stops entre fill-color y leyenda dinámica', () => {
    const scale = buildMetricScale(
      'turnout_2019',
      'Participación observada 2019',
      'percent',
      [0.56, 0.67, 0.68, 0.8, 0.83],
    );
    const expression = mapLibreColorExpression(scale);
    const serializedExpression = JSON.stringify(expression);
    scale.stops.forEach((stop) => {
      expect(serializedExpression).toContain(String(stop.value));
      expect(serializedExpression).toContain(stop.color);
      expect(scale.items.some((item) => item.color === stop.color)).toBe(true);
    });
    expect(scale.items.at(-1)).toMatchObject({
      label: 'Sin dato',
      color: PARTICIPATION_COLORS.noData,
    });
    render(<CurrentElectionMapLegend scale={scale} />);
    expect(screen.getByLabelText('Leyenda — Participación observada 2019')).toBeVisible();
  });
  it('formatea conteos, porcentajes y densidad en es-EC', () => {
    expect(
      buildMetricScale(
        'registered_voters_current',
        'Electores actuales',
        'count',
        [1000, 2000, 3000, 4000],
      ).items[0].detail,
    ).toMatch(/1[.\s]?000/);
    expect(
      buildMetricScale('density', 'Densidad poblacional', 'density', [125.4, 200, 300, 400])
        .items[0].detail,
    ).toContain('hab./km²');
    expect(
      buildMetricScale('growth', 'Crecimiento', 'percent', [-0.0943, 0, 0.02, 0.04]).items[0]
        .detail,
    ).toContain('%');
  });

  it.each([
    ['turnout_2023', 'Participación observada 2023', 'percent'],
    ['registered_voters_current', 'Electores actuales', 'count'],
    ['inec_population_2022', 'Población INEC 2022', 'count'],
  ] as const)('mantiene visible la leyenda de %s', (metric, title, unit) => {
    const { unmount } = render(
      <CurrentElectionMapLegend scale={buildMetricScale(metric, title, unit, [10, 20, 30, 40])} />,
    );
    expect(screen.getByLabelText(`Leyenda — ${title}`)).toBeVisible();
    expect(screen.getByText('Sin dato')).toBeVisible();
    unmount();
  });

  it('usa etiquetas humanas por familia de métrica en vez de "Rango N"', () => {
    const values = [1000, 2000, 3000, 4000];
    const counts = buildMetricScale(
      'registered_voters_current',
      'Electores actuales',
      'count',
      values,
    );
    expect(counts.items.map((i) => i.label)).toEqual([
      'Muy bajo',
      'Bajo',
      'Medio',
      'Alto',
      'Sin dato',
    ]);
    expect(counts.items.some((i) => i.label.startsWith('Rango'))).toBe(false);

    const change = buildMetricScale(
      'registration_change_2019',
      'Cambio del registro 2019 → actual',
      'percent',
      [-0.4, -0.28, -0.2, -0.05],
    );
    expect(change.items.map((i) => i.label)).toEqual([
      'Disminución alta',
      'Disminución media',
      'Disminución leve',
      'Cambio menor',
      'Sin dato',
    ]);

    const density = buildMetricScale(
      'population_density',
      'Densidad poblacional',
      'density',
      values,
    );
    expect(density.items.map((i) => i.label)).toEqual([
      'Baja densidad',
      'Densidad media',
      'Densidad alta',
      'Densidad muy alta',
      'Sin dato',
    ]);

    const participation = buildMetricScale(
      'turnout_2019',
      'Participación observada 2019',
      'percent',
      [0.5, 0.6, 0.7, 0.8],
    );
    expect(participation.items.map((i) => i.label)).toEqual([
      'Baja',
      'Media',
      'Alta',
      'Muy alta',
      'Sin dato',
    ]);
  });
});
