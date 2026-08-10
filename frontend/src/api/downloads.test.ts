import { describe, expect, it } from 'vitest';
import { safeFilename } from './downloads';
describe('nombres de descarga', () => {
  it('elimina segmentos peligrosos', () =>
    expect(safeFilename('../../reporte final.pdf')).toBe('.._.._reporte_final.pdf'));
});
