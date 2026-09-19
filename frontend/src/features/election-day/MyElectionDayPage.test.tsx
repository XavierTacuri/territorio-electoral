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
