import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getFieldDb } from '../../offline/db';
import type { OfflineDraft, OwnerScope } from '../../offline/types';
import { ConflictReviewDialog } from './ConflictReviewDialog';

const scope: OwnerScope = { user_id: 'u1', organization_id: 'org-1', campaign_id: 'campaign-1' };

function actDraft(overrides: Partial<OfflineDraft> = {}): OfflineDraft {
  return {
    id: 'ELECTION_ACT_SUBMIT:cid-1',
    owner_key: 'u1::org-1::campaign-1',
    client_generated_id: 'cid-1',
    entity_type: 'ELECTION_ACT_SUBMIT',
    organization_id: 'org-1',
    campaign_id: 'campaign-1',
    parish_id: 0,
    user_id: 'u1',
    payload: { electoral_board_id: 'board-1' },
    created_offline_at: new Date().toISOString(),
    updated_offline_at: new Date().toISOString(),
    sync_status: 'REQUIRES_REVIEW',
    last_error: 'Ya existe un acta recibida para esta junta. Revisa antes de continuar.',
    conflict_reason: 'CONFLICT',
    server_id: null,
    ...overrides,
  };
}

function renderDialog(draft: OfflineDraft) {
  return render(
    <MemoryRouter initialEntries={['/app/campaigns/campaign-1/field/drafts']}>
      <Routes>
        <Route
          path="/app/campaigns/:campaignId/field/drafts"
          element={
            <ConflictReviewDialog
              draft={draft}
              scope={scope}
              onClose={vi.fn()}
              onResolved={vi.fn()}
            />
          }
        />
        <Route
          path="/app/campaigns/:campaignId/election-day/my"
          element={<div>MI JORNADA STUB</div>}
        />
        <Route path="/app/campaigns/:campaignId/field/needs/new" element={<div>NEEDS STUB</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(async () => {
  const db = await getFieldDb();
  await db.clear('drafts');
  await db.clear('syncQueue');
});

describe('ConflictReviewDialog — acta electoral', () => {
  it('"Revisar borrador" en un acta lleva a Mi Jornada, nunca a la ruta de necesidades', async () => {
    renderDialog(actDraft());
    expect(
      screen.getAllByText('Ya existe un acta recibida para esta junta. Revisa antes de continuar.')
        .length,
    ).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: 'Revisar borrador' }));
    expect(await screen.findByText('MI JORNADA STUB')).toBeVisible();
    expect(screen.queryByText('NEEDS STUB')).not.toBeInTheDocument();
  });

  it('"Conservar servidor" elimina el borrador local sin sobrescribir el servidor', async () => {
    const draft = actDraft();
    const db = await getFieldDb();
    await db.put('drafts', draft);
    const onResolved = vi.fn();
    render(
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/field/drafts']}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/field/drafts"
            element={
              <ConflictReviewDialog
                draft={draft}
                scope={scope}
                onClose={vi.fn()}
                onResolved={onResolved}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Conservar servidor' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    expect(await db.get('drafts', draft.id)).toBeUndefined();
  });
});
