import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { ControlCenterPanel } from './ControlCenterPanel';
import type { ControlCenterSummary } from './types';

const server = setupServer();
const nativeFetch = globalThis.fetch;

beforeAll(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    nativeFetch(
      new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost'),
      init,
    )) as typeof fetch;
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  globalThis.fetch = nativeFetch;
});

const baseSummary: ControlCenterSummary = {
  acts_coverage: {
    expected_boards: 4,
    received: 3,
    validated: 2,
    in_review: 1,
    observed: 0,
    pending: 1,
    received_coverage_pct: 75,
    validated_coverage_pct: 50,
  },
  contests: [
    {
      contest_id: 'contest-1',
      contest_name: 'Alcaldía',
      office_type: 'MAYOR',
      vote_method: 'SINGLE_CHOICE',
      validated_acts: 2,
      expected_acts: 4,
      valid_votes: 14,
      blank_votes: 1,
      null_votes: 1,
      ballots_counted: 16,
      candidates: [
        {
          candidate_id: 'cand-1',
          display_name: 'Candidata Uno',
          list_number: '1',
          ballot_order: 1,
          votes: 4,
          pct_valid_votes: 28.6,
        },
        {
          candidate_id: 'cand-2',
          display_name: 'Candidato Dos',
          list_number: '2',
          ballot_order: 2,
          votes: 10,
          pct_valid_votes: 71.4,
        },
      ],
    },
  ],
  polling_places: [
    {
      polling_place_id: 'place-1',
      polling_place_name: 'Escuela Central',
      parish_id: 1,
      expected_boards: 4,
      received: 3,
      validated: 2,
      in_review: 1,
      observed: 0,
      pending: 1,
      coverage_validated_pct: 50,
    },
  ],
  parishes: [
    {
      parish_id: 1,
      parish_name: 'Parroquia Centro',
      expected_boards: 4,
      validated: 2,
      coverage_validated_pct: 50,
      valid_votes: 14,
      blank_votes: 1,
      null_votes: 1,
    },
  ],
};

function handlers(controlCenter: ControlCenterSummary | null) {
  server.use(
    http.get('*/api/v1/campaigns/campaign-1/election-day/control-center', () =>
      HttpResponse.json({ operation: null, coverage: null, control_center: controlCenter }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/polling-places/place-1/boards', () =>
      HttpResponse.json([
        {
          id: 'board-1',
          polling_place_id: 'place-1',
          official_code: 'J01',
          board_number: 1,
          sex_category: null,
          registered_voters: 300,
          is_active: true,
        },
      ]),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/acts', () =>
      HttpResponse.json({
        items: [
          {
            id: 'act-1',
            campaign_id: 'campaign-1',
            operation_id: 'op-1',
            polling_place_id: 'place-1',
            electoral_board_id: 'board-1',
            electoral_contest_id: 'contest-1',
            status: 'VALIDATED',
            latest_revision_number: 1,
            validated_revision_id: 'rev-1',
            review_claimed_by_user_id: null,
            review_claimed_at: null,
            review_claim_expires_at: null,
            created_at: '2027-02-14T10:00:00Z',
            updated_at: '2027-02-14T10:00:00Z',
          },
        ],
        total: 1,
      }),
    ),
    http.get('*/api/v1/campaigns/campaign-1/election-day/acts/act-1', () =>
      HttpResponse.json({
        act: {
          id: 'act-1',
          campaign_id: 'campaign-1',
          operation_id: 'op-1',
          polling_place_id: 'place-1',
          electoral_board_id: 'board-1',
          electoral_contest_id: 'contest-1',
          status: 'VALIDATED',
          latest_revision_number: 1,
          validated_revision_id: 'rev-1',
          review_claimed_by_user_id: null,
          review_claimed_at: null,
          review_claim_expires_at: null,
          created_at: '2027-02-14T10:00:00Z',
          updated_at: '2027-02-14T10:00:00Z',
        },
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
            submitted_by_user_id: 'u1',
            blank_ballots: 1,
            null_ballots: 0,
            valid_ballots: 10,
            ballots_counted: 11,
            correction_reason: null,
            notes: null,
            created_at: '2027-02-14T10:00:00Z',
            submitted_at: '2027-02-14T10:05:00Z',
            results: [{ electoral_candidate_id: 'cand-2', votes: 10 }],
            evidence: [],
          },
        ],
        reviews: [],
      }),
    ),
  );
}

function renderPanel(
  controlCenter: ControlCenterSummary | null,
  operationStatus: 'PREPARATION' | 'ACTIVE' | 'SCRUTINY' | 'CLOSED' = 'SCRUTINY',
  isAdminSupport = false,
) {
  handlers(controlCenter);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ControlCenterPanel
        campaignId="campaign-1"
        operationStatus={operationStatus}
        isAdminSupport={isAdminSupport}
      />
    </QueryClientProvider>,
  );
}

describe('ControlCenterPanel — consolidado factual NO OFICIAL', () => {
  it('muestra la insignia NO OFICIAL y nunca palabras de predicción o ranking', async () => {
    renderPanel(baseSummary);
    expect(await screen.findByText('NO OFICIAL')).toBeVisible();
    const body = document.body.textContent ?? '';
    for (const forbidden of [
      'Ganando',
      'Primero',
      'Favorito',
      'Virtual ganador',
      'Probabilidad',
      'Proyección',
      'Ganador',
    ]) {
      expect(body).not.toContain(forbidden);
    }
  });

  it('ordena los candidatos por ballot_order, nunca por votos', async () => {
    renderPanel(baseSummary);
    await screen.findByText('Candidata Uno');
    const rows = screen.getAllByRole('row').map((r) => r.textContent ?? '');
    const idxUno = rows.findIndex((r) => r.includes('Candidata Uno'));
    const idxDos = rows.findIndex((r) => r.includes('Candidato Dos'));
    // Candidata Uno tiene ballot_order 1 y MENOS votos (4) que Candidato Dos
    // (ballot_order 2, 10 votos): si apareciera primero por votos, esta
    // aserción de orden fallaría.
    expect(idxUno).toBeGreaterThan(-1);
    expect(idxUno).toBeLessThan(idxDos);
  });

  it('muestra la cobertura de actas por recinto sin colorear ni ordenar por candidato', async () => {
    renderPanel(baseSummary);
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    expect(screen.getByText('50%')).toBeVisible();
  });

  it('no ofrece selector de contienda cuando solo hay una contienda elegible', async () => {
    renderPanel(baseSummary);
    await screen.findByText('Escuela Central');
    expect(screen.queryByLabelText('Contienda')).not.toBeInTheDocument();
  });

  it('ofrece selector de contienda cuando hay más de una contienda elegible', async () => {
    const twoContests: ControlCenterSummary = {
      ...baseSummary,
      contests: [
        baseSummary.contests[0],
        { ...baseSummary.contests[0], contest_id: 'contest-2', contest_name: 'Concejales' },
      ],
    };
    renderPanel(twoContests);
    expect(await screen.findByLabelText('Contienda')).toBeVisible();
  });

  it('muestra el aviso de modo soporte administrativo cuando corresponde', async () => {
    renderPanel(baseSummary, 'SCRUTINY', true);
    expect(await screen.findByText(/Modo soporte administrativo/)).toBeVisible();
  });

  it('muestra el banner de solo lectura cuando la jornada está cerrada', async () => {
    renderPanel(baseSummary, 'CLOSED');
    expect(await screen.findByText(/modo solo lectura/)).toBeVisible();
  });

  it('sin contienda elegible configurada, explica la ausencia de datos en vez de fallar', async () => {
    renderPanel(null);
    expect(await screen.findByText(/Aún no hay una contienda elegible configurada/)).toBeVisible();
  });

  it('muestra el banner de solo lectura al cerrar la jornada incluso sin contienda elegible', async () => {
    renderPanel(null, 'CLOSED');
    expect(await screen.findByText(/modo solo lectura/)).toBeVisible();
    expect(screen.getByText(/Aún no hay una contienda elegible configurada/)).toBeVisible();
  });

  it('el drill-down de un recinto muestra el estado de sus juntas y el detalle de un acta validada', async () => {
    renderPanel(baseSummary);
    await screen.findByText('Escuela Central');
    await userEvent.click(screen.getByRole('button', { name: /Ver juntas de Escuela Central/ }));
    expect(await screen.findByText('Validada')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'VER ACTA VALIDADA' }));
    await waitFor(() => expect(screen.getByText(/Revisión validada #1/)).toBeVisible());
  });
});
