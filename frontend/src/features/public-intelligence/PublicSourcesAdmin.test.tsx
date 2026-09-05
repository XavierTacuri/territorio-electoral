import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PublicSource } from './types';
import { PublicSourcesAdmin } from './PublicSourcesAdmin';

vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ user: {} }) }));
vi.mock('../../auth/permissions', () => ({ canManageCampaign: () => true }));

const source = (overrides: Partial<PublicSource>): PublicSource => ({
  id: crypto.randomUUID(),
  campaign_id: 'campaign',
  code: 'SOURCE',
  name: 'Fuente',
  publisher: 'Entidad',
  source_type: 'OFFICIAL_WEBSITE',
  base_url: 'https://example.test',
  official: true,
  active: true,
  retrieval_method: 'MANUAL',
  consecutive_failures: 0,
  items_last_fetch: 0,
  ...overrides,
});

describe('fuentes públicas manuales y automáticas', () => {
  it('oculta refresh para manual y lo ofrece para RSS/API configuradas', () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <PublicSourcesAdmin
          campaignId="campaign"
          sources={[
            source({ id: 'manual', name: 'CNE Ecuador' }),
            source({
              id: 'rss',
              name: 'RSS',
              retrieval_method: 'RSS',
              feed_url: 'https://example.test/feed',
            }),
            source({
              id: 'api',
              name: 'API',
              retrieval_method: 'API',
              api_url: 'https://example.test/api',
            }),
          ]}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Estado: Actualización manual/)).toBeInTheDocument();
    expect(
      screen.getByText('Esta fuente no tiene actualización automática configurada.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Actualizar ahora' })).toHaveLength(2);
  });
});
