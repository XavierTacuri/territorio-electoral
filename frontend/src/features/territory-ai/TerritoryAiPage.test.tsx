import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { apiRequest } from '../../api/client';
import TerritoryAiPage from './TerritoryAiPage';
vi.mock('../../api/client', () => ({ apiRequest: vi.fn() }));
const api = vi.mocked(apiRequest);
function page(path = '/app/campaigns/c1/territory-ai') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/campaigns/:campaignId/territory-ai" element={<TerritoryAiPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => api.mockReset());
describe('Territorio IA', () => {
  it('muestra bloqueo PRO para campaña Standard sin consultar conversaciones', async () => {
    api.mockResolvedValueOnce(null);
    page();
    expect(await screen.findByText('Funcionalidad disponible en el plan Pro.')).toBeVisible();
    expect(api).toHaveBeenCalledTimes(1);
  });
  it('muestra asistente, sugerencias, mensajes y drawer de citation', async () => {
    api.mockImplementation(async (path) => {
      if (String(path).includes('feature-entitlements'))
        return { status: 'ENABLED', expires_at: null };
      if (String(path).endsWith('/conversations')) return [];
      if (String(path).endsWith('/query'))
        return {
          answer: 'Respuesta grounded',
          citations: [
            {
              id: '1',
              source_type: 'CNE',
              title: 'Padrón electoral actual',
              source_name: 'CNE',
              reference_date: '2026-01-01',
              data_cutoff: '2026-01-01',
              territory: { id: 1, name: 'Gualaceo', dpa_code: '0106', level: 'CANTON' },
              excerpt: 'Datos agregados',
              internal_path: '/app/campaigns/c1/current-election',
              external_url: null,
              freshness: 'CURRENT',
            },
          ],
          limitations: [],
          intent: 'ELECTORAL_REGISTER',
          territory: null,
          conversation_id: 'conv1',
          message_id: 'msg1',
          provider: 'fake',
          model: 'fake',
          status: 'ANSWERED',
        };
      return [];
    });
    page();
    expect(await screen.findByText('Preguntas sugeridas')).toBeVisible();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Escribe una pregunta'), '¿Cuál es el padrón?');
    await user.click(screen.getByRole('button', { name: 'ENVIAR' }));
    expect(await screen.findByText('Respuesta grounded')).toBeVisible();
    await user.click(screen.getByText(/Padrón electoral actual/));
    expect(await screen.findByText('Datos agregados')).toBeVisible();
    expect(screen.getByText(/Tipo:/)).toBeVisible();
    expect(screen.getByText('Cantón')).toBeVisible();
  });
  it('muestra provider disabled controlado', async () => {
    api.mockImplementation(async (path) => {
      if (String(path).includes('feature-entitlements'))
        return { status: 'ENABLED', expires_at: null };
      if (String(path).endsWith('/conversations')) return [];
      if (String(path).endsWith('/query'))
        throw new ApiError(503, 'No disponible', {
          detail: { code: 'AI_PROVIDER_UNAVAILABLE', message: 'Proveedor' },
        });
      return [];
    });
    page();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText('Escribe una pregunta'), '¿Cuál es la fuente?');
    await user.keyboard('{Enter}');
    expect(
      await screen.findByText('Territorio IA no está configurada en este entorno.'),
    ).toBeVisible();
  });
  it('transporta contexto de deep link', async () => {
    api.mockImplementation(async (path) => {
      if (String(path).includes('feature-entitlements'))
        return { status: 'ENABLED', expires_at: null };
      if (String(path).endsWith('/conversations')) return [];
      return {
        answer: 'Contexto',
        citations: [],
        limitations: [],
        intent: 'NEEDS',
        territory: null,
        conversation_id: 'c',
        message_id: 'm',
        provider: 'fake',
        model: 'fake',
        status: 'ANSWERED',
      };
    });
    page(
      '/app/campaigns/c1/territory-ai?need_id=00000000-0000-0000-0000-000000000001&question=Resume',
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'ENVIAR' }));
    await waitFor(() =>
      expect(
        JSON.parse(String(api.mock.calls.find((c) => String(c[0]).endsWith('/query'))?.[1]?.body))
          .need_id,
      ).toBe('00000000-0000-0000-0000-000000000001'),
    );
  });
});
