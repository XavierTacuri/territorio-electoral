import { describe, expect, it } from 'vitest';
import { NEED_TABLE_HEADERS } from './NeedsPage';
import { FOLLOW_UP_TABLE_HEADERS, followUpPayload } from './CommitmentsPage';
import { activityClosurePayload } from './ActivityClosureDialog';

describe('necesidades y seguimientos de campaña', () => {
  it('simplifica la tabla de necesidades sin ranking ni workflow administrativo', () => {
    expect(NEED_TABLE_HEADERS).toEqual(['Necesidad', 'Parroquia', 'Origen', 'Acciones']);
    expect(NEED_TABLE_HEADERS).not.toContain('Prioridad');
    expect(NEED_TABLE_HEADERS).not.toContain('Menciones');
    expect(NEED_TABLE_HEADERS).not.toContain('Estado');
  });

  it('presenta seguimientos internos sin prioridad ni fecha límite', () => {
    expect(FOLLOW_UP_TABLE_HEADERS).toEqual(['Seguimiento', 'Responsable', 'Origen', 'Estado', 'Acciones']);
    const payload = followUpPayload({ title: 'Revisar documentación', description: '', status: 'PENDING', due_date: '', completed_date: '', parish_id: 1, responsible_user_id: '' });
    expect(payload.due_date).toBeNull();
    expect(payload).not.toHaveProperty('priority');
    expect(payload).not.toHaveProperty('deadline');
  });

  it('cierra una actividad creando necesidad y nunca crea un seguimiento (retirado de la UI de cierre)', () => {
    const payload = activityClosurePayload({ summary: 'Resumen territorial suficiente', outcomeNotes: '', existingNeedId: '', needTitle: 'Mejoramiento vial', needDescription: '', needCategory: 'ROADS' });
    expect(payload.new_needs).toHaveLength(1);
    expect(payload.commitments).toEqual([]);
  });
});
