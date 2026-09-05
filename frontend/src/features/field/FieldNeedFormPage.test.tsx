import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getFieldDb } from '../../offline/db';
import FieldNeedFormPage from './FieldNeedFormPage';
import { useFieldContext } from './useFieldContext';
import { useOfflineCatalog } from './useOfflineCatalog';

vi.mock('./useFieldContext');
vi.mock('./useOfflineCatalog');

const mockedUseFieldContext = vi.mocked(useFieldContext);
const mockedUseOfflineCatalog = vi.mocked(useOfflineCatalog);

const scope = { user_id: 'need-form-user', organization_id: 'org-1', campaign_id: 'campaign-need-form' };

beforeEach(() => {
  mockedUseFieldContext.mockReturnValue({
    loading: false,
    online: true,
    scope,
    campaignName: 'Campaña de prueba',
    parishes: [{ parish_id: 41, parish_name: 'Gualaceo' }],
    fromCache: false,
    cachedAt: null,
    error: null,
  });
  mockedUseOfflineCatalog.mockReturnValue([{ code: 'ROADS', name: 'Vialidad' }]);
});

afterEach(async () => {
  // vi.restoreAllMocks() would reset the vi.mock('./useFieldContext') auto-mock
  // to its default (undefined-returning) implementation. If the component's
  // debounced autosave timer is still pending when this runs, the next render
  // reads field.parishes on undefined and crashes. clearAllMocks() only drops
  // call history; beforeEach always re-establishes the return value anyway.
  vi.clearAllMocks();
  const db = await getFieldDb();
  await db.clear('drafts');
});

describe('FieldNeedFormPage — regla de producto: Need sin prioridad visible', () => {
  it('no muestra ningún control de "Prioridad" en el formulario', () => {
    render(
      <MemoryRouter>
        <FieldNeedFormPage />
      </MemoryRouter>,
    );
    expect(screen.queryByLabelText('Prioridad')).not.toBeInTheDocument();
    expect(screen.queryByText('Prioridad')).not.toBeInTheDocument();
  });

  it('el borrador autoguardado nunca incluye priority/priority_score/favorability/persuasion', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <FieldNeedFormPage />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('combobox', { name: 'Categoría' }));
    await user.click(await screen.findByRole('option', { name: 'Vialidad' }));
    await user.type(screen.getByRole('textbox', { name: 'Título' }), 'Necesidad de prueba');

    await waitFor(async () => {
      const db = await getFieldDb();
      const drafts = await db.getAllFromIndex('drafts', 'owner', `${scope.user_id}::${scope.organization_id}::${scope.campaign_id}`);
      expect(drafts.length).toBeGreaterThan(0);
    });

    const db = await getFieldDb();
    const drafts = await db.getAllFromIndex('drafts', 'owner', `${scope.user_id}::${scope.organization_id}::${scope.campaign_id}`);
    const draft = drafts[0];
    expect(draft.payload).not.toHaveProperty('priority');
    expect(draft.payload).not.toHaveProperty('priority_score');
    expect(draft.payload).not.toHaveProperty('favorability');
    expect(draft.payload).not.toHaveProperty('persuasion');
    expect(draft.payload.title).toBe('Necesidad de prueba');
  });
});
