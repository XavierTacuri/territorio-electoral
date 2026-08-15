import { describe, expect, it } from 'vitest';
import { FETCH_STATUS_LABELS, ITEM_TYPE_LABELS, SOURCE_TYPE_LABELS } from './labels';

describe('etiquetas de inteligencia pública', () => {
  it('localiza fuentes, items y fetch sin alterar códigos API', () => {
    expect(SOURCE_TYPE_LABELS.OFFICIAL_WEBSITE).toBe('Sitio oficial');
    expect(ITEM_TYPE_LABELS.PUBLIC_DOCUMENT).toBe('Documento público');
    expect(FETCH_STATUS_LABELS.FAILED).toBe('Fallida');
  });
});
