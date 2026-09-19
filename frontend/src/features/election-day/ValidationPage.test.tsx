import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiBlob, apiRequest } from '../../api/client';
import ValidationPage from './ValidationPage';

vi.mock('../../api/client', () => ({ apiRequest: vi.fn(), apiBlob: vi.fn() }));

const mockedApiRequest = vi.mocked(apiRequest);
const mockedApiBlob = vi.mocked(apiBlob);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/campaigns/campaign-1/election-day/validation']}>
        <Routes>
          <Route
            path="/app/campaigns/:campaignId/election-day/validation"
            element={<ValidationPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const act = {
  id: 'act-1',
  campaign_id: 'campaign-1',
  operation_id: 'op-1',
  polling_place_id: 'place-1',
  electoral_board_id: 'board-1',
  electoral_contest_id: 'contest-1',
  status: 'RECEIVED',
  latest_revision_number: 1,
  validated_revision_id: null,
  review_claimed_by_user_id: null,
  review_claimed_at: null,
  review_claim_expires_at: null,
  created_at: '2027-02-14T10:00:00Z',
  updated_at: '2027-02-14T10:00:00Z',
};

const detail = {
  act,
  polling_place_name: 'Escuela Central',
  electoral_board_code: 'J01',
  electoral_contest_name: 'Alcaldía',
  revisions: [
    {
      id: 'rev-1',
      act_id: 'act-1',
      revision_number: 1,
      revision_type: 'INITIAL',
      status: 'SUBMITTED',
      submitted_by_user_id: 'delegate-1',
      blank_ballots: 2,
      null_ballots: 1,
      valid_ballots: 15,
      ballots_counted: 18,
      correction_reason: null,
      notes: null,
      created_at: '2027-02-14T10:00:00Z',
      submitted_at: '2027-02-14T10:05:00Z',
      results: [{ electoral_candidate_id: 'cand-1', votes: 15 }],
      evidence: [
        {
          id: 'ev-1',
          revision_id: 'rev-1',
          mime_type: 'image/jpeg',
          size_bytes: 1024,
          original_filename: 'acta.jpg',
          uploaded_by_user_id: 'delegate-1',
          created_at: '2027-02-14T10:04:00Z',
        },
      ],
    },
  ],
  reviews: [],
};

beforeEach(() => {
  mockedApiBlob.mockResolvedValue({ blob: new Blob(['x']), disposition: null });
  URL.createObjectURL = vi.fn(() => 'blob:mock');
  URL.revokeObjectURL = vi.fn();
  window.open = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Validación de actas', () => {
  it('muestra la cola vacía cuando no hay actas pendientes', async () => {
    mockedApiRequest.mockImplementation((path: string) => {
      if (path.includes('/validation/queue')) return Promise.resolve({ items: [], total: 0 });
      return Promise.reject(new Error(`unexpected path ${path}`));
    });
    renderPage();
    expect(await screen.findByText('No existen actas pendientes de revisión.')).toBeVisible();
  });

  it('muestra 403 como "no tienes asignación de validador"', async () => {
    const { ApiError } = await import('../../api/errors');
    mockedApiRequest.mockRejectedValue(new ApiError(403, 'Forbidden'));
    renderPage();
    expect(
      await screen.findByText('No tienes una asignación de validador de actas en esta jornada.'),
    ).toBeVisible();
  });

  it('reclama, valida un acta y refresca la cola', async () => {
    let claimed = false;
    let validated = false;
    mockedApiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes('/validation/queue'))
        return Promise.resolve({
          items: validated ? [] : [{ ...act, review_claimed_by_user_id: claimed ? 'me' : null }],
          total: validated ? 0 : 1,
        });
      if (path === '/campaigns/campaign-1/election-day/acts/act-1')
        return Promise.resolve({
          ...detail,
          act: { ...act, review_claimed_by_user_id: claimed ? 'me' : null },
        });
      if (path.endsWith('/act-1/claim') && init?.method === 'POST') {
        claimed = true;
        return Promise.resolve({ ...act, review_claimed_by_user_id: 'me' });
      }
      if (path.endsWith('/act-1/validate') && init?.method === 'POST') {
        validated = true;
        return Promise.resolve({ ...act, status: 'VALIDATED' });
      }
      return Promise.reject(new Error(`unexpected path ${path}`));
    });
    renderPage();
    await screen.findByText(/Escuela Central/);
    await userEvent.click(screen.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }));
    await userEvent.click(await screen.findByRole('button', { name: 'VALIDAR' }));
    expect(await screen.findByText('Acta validada.')).toBeVisible();
  });

  it('observa un acta con motivo obligatorio', async () => {
    let claimed = false;
    mockedApiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.includes('/validation/queue'))
        return Promise.resolve({
          items: [{ ...act, review_claimed_by_user_id: claimed ? 'me' : null }],
          total: 1,
        });
      if (path === '/campaigns/campaign-1/election-day/acts/act-1')
        return Promise.resolve({
          ...detail,
          act: { ...act, review_claimed_by_user_id: claimed ? 'me' : null },
        });
      if (path.endsWith('/act-1/claim') && init?.method === 'POST') {
        claimed = true;
        return Promise.resolve({ ...act, review_claimed_by_user_id: 'me' });
      }
      if (path.endsWith('/act-1/observe') && init?.method === 'POST')
        return Promise.resolve({ ...act, status: 'OBSERVED' });
      return Promise.reject(new Error(`unexpected path ${path}`));
    });
    renderPage();
    await screen.findByText(/Escuela Central/);
    await userEvent.click(screen.getByRole('button', { name: 'RECLAMAR PARA REVISAR' }));
    await userEvent.click(await screen.findByRole('button', { name: 'OBSERVAR' }));
    const confirmButton = screen.getByRole('button', { name: 'Confirmar observación' });
    expect(confirmButton).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Motivo de la observación'), 'Totales no cuadran');
    await userEvent.click(confirmButton);
    expect(await screen.findByText('Acta observada.')).toBeVisible();
  });
});
