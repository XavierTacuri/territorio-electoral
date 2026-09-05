import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { LoadingSkeleton } from '../../components/feedback/States';
import { createDraft, getDraft, updateDraftPayload } from '../../offline/draftsRepository';
import { enqueue } from '../../offline/syncQueueRepository';
import { useFieldContext } from './useFieldContext';
import { useOfflineCatalog } from './useOfflineCatalog';

// Field never exposes "prioridad" as a classification/ranking control — a
// Need is a territorial need report, not a political priority ranking (see
// PWA V1 audit). CitizenNeedCreate.priority keeps its existing MEDIUM
// default server-side for backward compatibility; Field simply never sends
// it, so no new field or score is introduced here.
type FormState = {
  need_category_code: string;
  title: string;
  description: string;
  parish_id: number | '';
};

const EMPTY_FORM: FormState = {
  need_category_code: '',
  title: '',
  description: '',
  parish_id: '',
};

export default function FieldNeedFormPage() {
  const { campaignId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const field = useFieldContext();
  const categories = useOfflineCatalog('need-categories');
  const draftIdParam = searchParams.get('draft');

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const clientGeneratedId = useRef<string>(crypto.randomUUID());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    async function loadExisting() {
      if (!draftIdParam) {
        if (field.parishes.length === 1)
          setForm((prev) => ({ ...prev, parish_id: field.parishes[0].parish_id }));
        return;
      }
      const existing = await getDraft(draftIdParam);
      if (!existing) return;
      clientGeneratedId.current = existing.client_generated_id;
      setDraftId(existing.id);
      setForm({ ...EMPTY_FORM, ...(existing.payload as Partial<FormState>) });
    }
    void loadExisting();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftIdParam, field.parishes.length]);

  const persist = useCallback(
    async (next: FormState) => {
      if (!field.scope || !next.parish_id) return;
      if (draftId) {
        await updateDraftPayload(draftId, next);
      } else {
        const created = await createDraft(
          field.scope,
          'NEED',
          Number(next.parish_id),
          next,
          clientGeneratedId.current,
        );
        setDraftId(created.id);
        // Attach the draft id to the URL (no new history entry) so a reload
        // right after the first autosave still finds this exact draft
        // instead of starting a second, orphaned one.
        setSearchParams({ draft: created.id }, { replace: true });
      }
      setSavedAt(new Date());
    },
    [draftId, field.scope, setSearchParams],
  );

  function change<K extends keyof FormState>(key: K, value: FormState[K]) {
    const next = { ...form, [key]: value };
    setForm(next);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => void persist(next), 600);
  }

  async function saveAndQueue() {
    if (!field.scope || !form.parish_id) return;
    await persist(form);
    const id = draftId ?? `NEED:${clientGeneratedId.current}`;
    await enqueue(field.scope, id, 'NEED');
    navigate(`/app/campaigns/${campaignId}/field/drafts`);
  }

  if (field.loading) return <LoadingSkeleton />;
  if (field.parishes.length === 0)
    return <Alert severity="warning">No tienes parroquias asignadas activas.</Alert>;

  return (
    <Stack spacing={2} component="form" onSubmit={(e) => e.preventDefault()}>
      <Typography variant="h2" sx={{ fontSize: '1.2rem' }}>
        Registrar necesidad
      </Typography>
      <TextField
        select
        label="Parroquia"
        value={form.parish_id}
        onChange={(e) => change('parish_id', Number(e.target.value))}
        required
      >
        {field.parishes.map((p) => (
          <MenuItem key={p.parish_id} value={p.parish_id}>
            {p.parish_name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Categoría"
        value={form.need_category_code}
        onChange={(e) => change('need_category_code', e.target.value)}
        required
      >
        {categories.map((c) => (
          <MenuItem key={c.code} value={c.code}>
            {c.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Título"
        value={form.title}
        onChange={(e) => change('title', e.target.value)}
        required
      />
      <TextField
        label="Descripción / observaciones"
        value={form.description}
        onChange={(e) => change('description', e.target.value)}
        multiline
        minRows={3}
      />

      <Typography variant="caption" color="text.secondary">
        {savedAt
          ? `Guardado en el dispositivo · ${savedAt.toLocaleTimeString('es-EC')}`
          : 'Sin cambios guardados aún'}
      </Typography>

      <Button
        variant="contained"
        size="large"
        onClick={() => void saveAndQueue()}
        disabled={!form.title.trim() || !form.need_category_code || !form.parish_id}
      >
        Guardar y enviar a sincronización
      </Button>
    </Stack>
  );
}
