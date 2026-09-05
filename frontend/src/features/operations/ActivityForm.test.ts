import { describe, expect, it } from 'vitest';
import { activityStatusOptions } from './ActivityForm';
import type { Activity } from './types';

const activity = (approval_status: Activity['approval_status'], status = 'PLANNED') =>
  ({ status, approval_status } as Activity);

describe('workflow de estado de actividades', () => {
  it('no ofrece ejecución antes de la aprobación', () => {
    expect(activityStatusOptions(activity('DRAFT'))).toEqual(['PLANNED']);
    expect(activityStatusOptions(activity('PENDING_APPROVAL'))).toEqual(['PLANNED']);
    expect(activityStatusOptions(activity('REJECTED'))).toEqual(['PLANNED']);
  });

  it('ofrece completar y suspender únicamente cuando está aprobada', () => {
    expect(activityStatusOptions(activity('APPROVED'))).toEqual(['PLANNED', 'COMPLETED', 'SUSPENDED']);
  });
});
