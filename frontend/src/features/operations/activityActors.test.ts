import { describe, expect, it } from 'vitest';
import { formatActivityActor } from './activityActors';

describe('actor visible de actividad', () => {
  it('muestra manager real y rol traducido', () =>
    expect(
      formatActivityActor({
        id: '1',
        display_name: 'Manager Demo',
        username: 'manager_demo',
        role_codes: ['CAMPAIGN_MANAGER'],
      }),
    ).toBe('Manager Demo · Director de campaña'));
  it('muestra candidato sin enum técnico', () =>
    expect(
      formatActivityActor({
        id: '2',
        display_name: 'Candidate Demo',
        username: 'candidate_demo',
        role_codes: ['CANDIDATE'],
      }),
    ).toBe('Candidate Demo · Candidato'));
  it('usa username como fallback', () =>
    expect(
      formatActivityActor({
        id: '3',
        display_name: '',
        username: 'manager_demo',
        role_codes: ['CAMPAIGN_MANAGER'],
      }),
    ).toBe('manager_demo · Director de campaña'));
});
