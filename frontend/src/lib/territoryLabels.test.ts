import { describe, expect, it } from 'vitest';
import { parishOptionLabel, type ParishOption } from './territoryLabels';

const options: ParishOption[] = [
  { id: 1, name: 'Gualaquiza', dpa_code: '140201', parish_type: 'URBAN' },
  { id: 2, name: 'Gualaquiza', dpa_code: '140250', parish_type: 'URBAN' },
  { id: 3, name: 'Amazonas', dpa_code: '140251', parish_type: 'RURAL' },
];

describe('etiquetas territoriales parroquiales', () => {
  it('desambigua por tipo oficial y DPA sólo cuando se repite el nombre', () => {
    expect(parishOptionLabel(options[0], options)).toBe('Gualaquiza · Urbana · 140201');
    expect(parishOptionLabel(options[1], options)).toBe('Gualaquiza · Cabecera cantonal · 140250');
    expect(parishOptionLabel(options[2], options)).toBe('Amazonas');
  });
});
