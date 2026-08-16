import { describe, expect, it } from 'vitest';
import { ApiError, statusMessage } from './errors';
describe('errores HTTP', () => {
  for (const [status, text] of [
    [400, 'solicitud'],
    [401, 'sesi'],
    [403, 'permisos'],
    [404, 'recurso'],
    [409, 'conflicto'],
    [410, 'disponible'],
    [413, 'tama'],
    [415, 'formato'],
    [422, 'campos'],
    [429, 'intentos'],
    [500, 'inesperado'],
    [503, 'servicio'],
  ] as const)
    it(`normaliza ${status}`, () => expect(statusMessage(status).toLowerCase()).toContain(text));
  it('normaliza códigos desconocidos', () => expect(statusMessage(418)).toContain('completar'));
  it('conserva detalle estructurado', () => {
    const e = new ApiError(422, 'x', { field: 'title' });
    expect(e.status).toBe(422);
    expect(e.detail).toEqual({ field: 'title' });
  });
});
