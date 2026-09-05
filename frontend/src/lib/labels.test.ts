import { describe, expect, it } from 'vitest';
import { needStatusLabel, priorityLabel } from './labels';

describe('labels operativos en español', () => {
  it.each([['HIGH', 'Alta'], ['MEDIUM', 'Media'], ['LOW', 'Baja'], ['CRITICAL', 'Crítica']])(
    'traduce prioridad %s', (value, label) => expect(priorityLabel(value)).toBe(label),
  );
  it.each([
    ['VALIDATED', 'Validada'], ['REPORTED', 'Reportada'], ['UNDER_REVIEW', 'En revisión'],
    ['IDENTIFIED', 'Identificada'], ['IN_PLAN', 'En plan'], ['INCLUDED_IN_PLAN', 'Incluida en el plan'],
    ['CLOSED', 'Cerrada'], ['ARCHIVED', 'Archivada'], ['DISCARDED', 'Descartada'],
  ])('traduce estado %s', (value, label) => expect(needStatusLabel(value)).toBe(label));
});
