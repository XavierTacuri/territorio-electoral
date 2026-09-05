import { describe, expect, it } from 'vitest';
import {
  FETCH_STATUS_LABELS,
  ITEM_TYPE_LABELS,
  RETRIEVAL_METHOD_LABELS,
  SOURCE_TYPE_LABELS,
  publicTopicLabel,
} from './labels';

describe('etiquetas de inteligencia pública', () => {
  it('localiza fuentes, items y fetch sin alterar códigos API', () => {
    expect(SOURCE_TYPE_LABELS.OFFICIAL_WEBSITE).toBe('Sitio oficial');
    expect(ITEM_TYPE_LABELS.PUBLIC_DOCUMENT).toBe('Documento público');
    expect(FETCH_STATUS_LABELS.FAILED).toBe('Fallida');
    expect(Object.keys(RETRIEVAL_METHOD_LABELS)).toEqual(['MANUAL', 'RSS', 'API']);
    expect(RETRIEVAL_METHOD_LABELS.API).toBe('API');
  });
  it('traduce todos los topics públicos conocidos al español', () => {
    expect(publicTopicLabel('WATER_SANITATION')).toBe('Agua y saneamiento');
    expect(publicTopicLabel('BUDGET')).toBe('Presupuesto');
    expect(publicTopicLabel('EDUCATION')).toBe('Educación');
    expect(publicTopicLabel('HEALTH')).toBe('Salud');
    expect(publicTopicLabel('PUBLIC_WORKS')).toBe('Obras públicas');
    expect(publicTopicLabel('SECURITY')).toBe('Seguridad');
    expect(publicTopicLabel('ROAD_INFRASTRUCTURE')).toBe('Vialidad');
    expect(publicTopicLabel('OTHER')).toBe('Otros');
  });
});
