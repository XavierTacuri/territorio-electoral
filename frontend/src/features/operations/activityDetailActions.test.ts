import { describe, expect, it } from 'vitest';
import type { SessionUser } from '../../auth/permissions';
import { activityDetailActions } from './activityDetailActions';
import type { Activity } from './types';

const user = (role: string): SessionUser => ({ id: role, username: role, email: `${role}@test`, first_name: role, last_name: 'Demo', is_active: true, is_superuser: false, roles: [{ code: role, name: role }] });
const activity = (approval_status: Activity['approval_status']) => ({ approval_status, status: 'PLANNED' } as Activity);

describe('acciones del detalle de actividad', () => {
  it.each(['CANDIDATE', 'CAMPAIGN_MANAGER'])('%s aprueba y rechaza pendientes', (role) => {
    expect(activityDetailActions(user(role), activity('PENDING_APPROVAL'))).toMatchObject({ approve: true, reject: true, execution: false });
  });

  it('coordinador no aprueba pendientes y corrige rechazadas', () => {
    expect(activityDetailActions(user('TERRITORIAL_COORDINATOR'), activity('PENDING_APPROVAL')).approve).toBe(false);
    expect(activityDetailActions(user('TERRITORIAL_COORDINATOR'), activity('REJECTED')).correctAndResubmit).toBe(true);
  });

  it('solo muestra resultados de ejecución cuando está aprobada', () => {
    expect(activityDetailActions(user('CANDIDATE'), activity('REJECTED')).execution).toBe(false);
    expect(activityDetailActions(user('CANDIDATE'), activity('APPROVED')).execution).toBe(true);
  });
});
