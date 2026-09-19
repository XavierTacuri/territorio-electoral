import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import { getFieldDb } from '../../offline/db';
import { useOnlineStatus } from '../../offline/useOnlineStatus';
import MyElectionDayPage from './MyElectionDayPage';

vi.mock('../../api/client', () => ({ apiRequest: vi.fn() }));
vi.mock('../../offline/useOnlineStatus');

const mockedApiRequest = vi.mocked(apiRequest);
const mockedUseOnlineStatus = vi.mocked(useOnlineStatus);

const auth = vi.hoisted(() => ({
  user: { id: 'u1', username: 'delegate', roles: [{ code: 'TERRITORIAL_COORDINATOR' }] } as any,
}));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: auth.user }) }));

const geolocationMock = {
  getCurrentPosition: vi.fn((success: PositionCallback) =>
    success({ coords: { latitude: -2.9, longitude: -78.8 } } as GeolocationPosition),
  ),
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/app/campaigns/campaign-1/election-day/my']}>
      <Routes>
        <Route path="/app/campaigns/:campaignId/election-day/my" element={<MyElectionDayPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const myContext = {
  campaign_id: 'campaign-1',
  campaign_name: 'Campaña Uno',
  organization_id: 'org-1',
  operation_id: 'op1',
  election_date: '2027-02-14',
  operation_status: 'ACTIVE',
  staff_types: ['POLLING_PLACE_DELEGATE'],
  polling_places: [{ id: 'place-1', name: 'Escuela Central' }],
};
const myAssignment = {
  id: 'a1',
  operation_id: 'op1',
  user_id: 'u1',
  polling_place_id: 'place-1',
  assignment_role: 'POLLING_PLACE_DELEGATE',
  status: 'ASSIGNED',
  checked_in_at: null,
  checkin_latitude: null,
  checkin_longitude: null,
  replaced_by_assignment_id: null,
};
const validatorAssignment = {
  ...myAssignment,
  id: 'a-validator',
  polling_place_id: null,
  assignment_role: 'ACT_VALIDATOR',
};
const place = { id: 'place-1', name: 'Escuela Central' };

beforeEach(() => {
  Object.defineProperty(navigator, 'geolocation', { value: geolocationMock, configurable: true });
  mockedUseOnlineStatus.mockReturnValue(true);
});

afterEach(async () => {
  vi.restoreAllMocks();
  const db = await getFieldDb();
  await db.clear('drafts');
  await db.clear('syncQueue');
  await db.clear('cachedCampaignInfo');
  await db.clear('cachedElectionDayAssignment');
  await db.clear('cachedElectionActContext');
  await db.clear('pendingAttachments');
});

function mockOnlineFlow(assignments: unknown[] = [myAssignment]) {
  mockedApiRequest.mockImplementation((path: string) => {
    if (path === '/campaigns/campaign-1/election-day/my-context') return Promise.resolve(myContext);
    if (path === '/campaigns/campaign-1/election-day/my-assignments')
      return Promise.resolve(assignments);
    if (path === '/campaigns/campaign-1/election-day/polling-places/place-1')
      return Promise.resolve(place);
    return Promise.reject(new Error(`unexpected path ${path}`));
  });
}

describe('Mi Jornada', () => {
  it('carga las asignaciones de delegado en línea y las muestra', async () => {
    mockOnlineFlow();
    renderPage();
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    expect(screen.getByText(/Asignado/)).toBeVisible();
  });

  it('ignora asignaciones de validador: solo muestra recintos de delegado', async () => {
    mockOnlineFlow([myAssignment, validatorAssignment]);
    renderPage();
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    // Una única tarjeta de recinto, la de validador no aporta ninguna.
    expect(screen.getAllByText('Escuela Central')).toHaveLength(1);
  });

  it('muestra un mensaje cuando el usuario no tiene asignación de delegado', async () => {
    mockedApiRequest.mockImplementation((path: string) => {
      if (path === '/campaigns/campaign-1/election-day/my-context')
        return Promise.resolve(myContext);
      if (path === '/campaigns/campaign-1/election-day/my-assignments') return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected path ${path}`));
    });
    renderPage();
    expect(
      await screen.findByText('No tienes una asignación de delegado de recinto en esta campaña.'),
    ).toBeVisible();
  });

  it('confirmar presencia guarda un draft y lo encola sin llamar directamente a la API', async () => {
    mockOnlineFlow();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(screen.getByRole('button', { name: 'CONFIRMAR PRESENCIA' }));
    expect(
      await screen.findByText('Guardado en el dispositivo. Se sincronizará con el servidor.'),
    ).toBeVisible();
    const db = await getFieldDb();
    const drafts = await db.getAllFromIndex('drafts', 'owner', 'u1::org-1::campaign-1');
    const checkIn = drafts.find((d) => d.entity_type === 'ELECTION_DAY_CHECK_IN');
    expect(checkIn?.payload).toMatchObject({
      assignment_id: 'a1',
      latitude: -2.9,
      longitude: -78.8,
    });
    const queue = await db.getAllFromIndex('syncQueue', 'owner', 'u1::org-1::campaign-1');
    expect(queue.some((q) => q.draft_id === checkIn?.id)).toBe(true);
    // apiRequest is never invoked for the mutation itself — only the initial GETs.
    expect(mockedApiRequest).not.toHaveBeenCalledWith(
      expect.stringContaining('/check-in'),
      expect.anything(),
    );
  });

  it('reportar incidencia guarda un draft con categoría y descripción', async () => {
    mockOnlineFlow();
    renderPage();
    await screen.findByText('Escuela Central');
    await userEvent.click(screen.getByRole('button', { name: 'REPORTAR INCIDENCIA' }));
    await userEvent.type(screen.getByLabelText('Descripción'), 'Sin energía eléctrica');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar incidencia' }));
    expect(
      await screen.findByText(
        'Incidencia guardada en el dispositivo. Se sincronizará con el servidor.',
      ),
    ).toBeVisible();
    const db = await getFieldDb();
    const drafts = await db.getAllFromIndex('drafts', 'owner', 'u1::org-1::campaign-1');
    const incident = drafts.find((d) => d.entity_type === 'ELECTION_DAY_INCIDENT');
    expect(incident?.payload).toMatchObject({
      polling_place_id: 'place-1',
      description: 'Sin energía eléctrica',
    });
  });

  it('durante escrutinio, registra un acta offline con foto y candidatos', async () => {
    const scrutinyContext = { ...myContext, operation_status: 'SCRUTINY' };
    const board = {
      id: 'board-1',
      polling_place_id: 'place-1',
      official_code: 'J01',
      board_number: 1,
      sex_category: null,
      registered_voters: 300,
      is_active: true,
    };
    const contest = {
      id: 'contest-1',
      name: 'Alcaldía',
      office_type: 'MAYOR',
      vote_method: 'SINGLE_CHOICE',
      candidates: [
        {
          id: 'cand-1',
          full_name: 'Candidata A',
          display_name: 'Candidata A',
          list_number: '1',
          ballot_order: 1,
        },
      ],
    };
    mockedApiRequest.mockImplementation((path: string) => {
      if (path === '/campaigns/campaign-1/election-day/my-context')
        return Promise.resolve(scrutinyContext);
      if (path === '/campaigns/campaign-1/election-day/my-assignments')
        return Promise.resolve([myAssignment]);
      if (path === '/campaigns/campaign-1/election-day/polling-places/place-1')
        return Promise.resolve(place);
      if (path === '/campaigns/campaign-1/election-day/acts/contests')
        return Promise.resolve([contest]);
      if (path === '/campaigns/campaign-1/election-day/polling-places/place-1/boards')
        return Promise.resolve([board]);
      if (path === '/campaigns/campaign-1/election-day/acts?polling_place_id=place-1')
        return Promise.resolve({ items: [], total: 0 });
      return Promise.reject(new Error(`unexpected path ${path}`));
    });
    renderPage();
    await screen.findByText('Escuela Central');
    expect(await screen.findByText('Junta 1')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'REGISTRAR ACTA' }));

    await screen.findByText('Registrar acta — Junta 1');
    const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'acta.jpg', { type: 'image/jpeg' });
    const fileInputs = document.querySelectorAll('input[type="file"]');
    const fileInput = fileInputs[fileInputs.length - 1] as HTMLInputElement;
    await userEvent.upload(fileInput, file);
    expect(await screen.findByText('Fotos agregadas: 1')).toBeVisible();
    await userEvent.type(screen.getByLabelText('Candidata A'), '10');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    expect(
      await screen.findByText('Acta guardada en el dispositivo. Se sincronizará con el servidor.'),
    ).toBeVisible();
    const db = await getFieldDb();
    const drafts = await db.getAllFromIndex('drafts', 'owner', 'u1::org-1::campaign-1');
    const actDraft = drafts.find((d) => d.entity_type === 'ELECTION_ACT_SUBMIT');
    expect(actDraft?.payload).toMatchObject({
      is_correction: false,
      electoral_board_id: 'board-1',
      electoral_contest_id: 'contest-1',
      results: [{ electoral_candidate_id: 'cand-1', votes: 10 }],
    });
    const attachments = await db.getAllFromIndex('pendingAttachments', 'draft', actDraft!.id);
    expect(attachments).toHaveLength(1);
  });

  it('sin conexión, usa las asignaciones cacheadas previamente', async () => {
    mockOnlineFlow();
    const { unmount } = renderPage();
    await screen.findByText('Escuela Central');
    unmount();

    mockedUseOnlineStatus.mockReturnValue(false);
    mockedApiRequest.mockReset();
    renderPage();
    expect(await screen.findByText('Escuela Central')).toBeVisible();
    expect(
      screen.getByText(
        'Sin conexión: los registros se guardan en el dispositivo y se sincronizan al reconectar.',
      ),
    ).toBeVisible();
  });
});
