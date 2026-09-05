import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import MyLocationIcon from '@mui/icons-material/MyLocation';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { LoadingSkeleton } from '../../components/feedback/States';
import { todayDateOnly } from '../../lib/dates';
import { addPendingAttachment, listAttachments } from '../../offline/attachmentsRepository';
import { createDraft, getDraft, updateDraftPayload } from '../../offline/draftsRepository';
import { enqueue } from '../../offline/syncQueueRepository';
import type { PendingAttachment } from '../../offline/types';
import { useFieldContext } from './useFieldContext';
import { useOfflineCatalog } from './useOfflineCatalog';

type FormState = {
  activity_type_code: string;
  title: string;
  description: string;
  activity_date: string;
  parish_id: number | '';
  location_name: string;
  latitude: number | null;
  longitude: number | null;
};

const EMPTY_FORM: FormState = {
  activity_type_code: '',
  title: '',
  description: '',
  activity_date: todayDateOnly(),
  parish_id: '',
  location_name: '',
  latitude: null,
  longitude: null,
};

export default function FieldActivityFormPage() {
  const { campaignId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const field = useFieldContext();
  const types = useOfflineCatalog('activity-types');
  const draftIdParam = searchParams.get('draft');

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [locating, setLocating] = useState(false);
  const clientGeneratedId = useRef<string>(crypto.randomUUID());
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    async function loadExisting() {
      if (!draftIdParam) {
        if (field.parishes.length === 1) setForm((prev) => ({ ...prev, parish_id: field.parishes[0].parish_id }));
        return;
      }
      const existing = await getDraft(draftIdParam);
      if (!existing) return;
      clientGeneratedId.current = existing.client_generated_id;
      setDraftId(existing.id);
      setForm({ ...EMPTY_FORM, ...(existing.payload as Partial<FormState>) });
      setAttachments(await listAttachments(existing.id));
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
          'ACTIVITY',
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

  async function captureLocation() {
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const next = { ...form, latitude: position.coords.latitude, longitude: position.coords.longitude };
        setForm(next);
        void persist(next);
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: false, timeout: 8000 },
    );
  }

  async function onFile(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file || !field.scope) return;
    let currentDraftId = draftId;
    if (!currentDraftId) {
      const created = await createDraft(field.scope, 'ACTIVITY', Number(form.parish_id), form, clientGeneratedId.current);
      currentDraftId = created.id;
      setDraftId(currentDraftId);
      setSearchParams({ draft: currentDraftId }, { replace: true });
    }
    const title = form.title.trim() ? `Evidencia — ${form.title.trim()}` : 'Evidencia de campo';
    const result = await addPendingAttachment(field.scope, currentDraftId, file, title);
    if (result.attachment) setAttachments((prev) => [...prev, result.attachment!]);
  }

  async function saveAndQueue() {
    if (!field.scope || !form.parish_id) return;
    await persist(form);
    const id = draftId ?? `ACTIVITY:${clientGeneratedId.current}`;
    await enqueue(field.scope, id, 'ACTIVITY');
    navigate(`/app/campaigns/${campaignId}/field/drafts`);
  }

  if (field.loading) return <LoadingSkeleton />;
  if (field.parishes.length === 0) return <Alert severity="warning">No tienes parroquias asignadas activas.</Alert>;

  return (
    <Stack spacing={2} component="form" onSubmit={(e) => e.preventDefault()}>
      <Typography variant="h2" sx={{ fontSize: '1.2rem' }}>
        Registrar actividad
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
        label="Tipo de actividad"
        value={form.activity_type_code}
        onChange={(e) => change('activity_type_code', e.target.value)}
        required
      >
        {types.map((t) => (
          <MenuItem key={t.code} value={t.code}>
            {t.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Nombre de la actividad"
        value={form.title}
        onChange={(e) => change('title', e.target.value)}
        required
      />
      <TextField
        type="date"
        label="Fecha"
        value={form.activity_date}
        onChange={(e) => change('activity_date', e.target.value)}
        slotProps={{ inputLabel: { shrink: true } }}
        required
      />
      <TextField
        label="Descripción / observaciones"
        value={form.description}
        onChange={(e) => change('description', e.target.value)}
        multiline
        minRows={3}
      />
      <TextField
        label="Lugar (referencia)"
        value={form.location_name}
        onChange={(e) => change('location_name', e.target.value)}
      />

      <Stack direction="row" spacing={2} alignItems="center">
        <Button startIcon={<MyLocationIcon />} onClick={() => void captureLocation()} disabled={locating}>
          {form.latitude != null ? 'Ubicación capturada' : 'Capturar ubicación (opcional)'}
        </Button>
        {form.latitude != null && (
          <Typography variant="caption" color="text.secondary">
            {form.latitude.toFixed(5)}, {form.longitude?.toFixed(5)}
          </Typography>
        )}
      </Stack>

      <Stack spacing={1}>
        <Button component="label" startIcon={<PhotoCameraIcon />}>
          Adjuntar evidencia (foto)
          <input
            type="file"
            hidden
            accept="image/jpeg,image/png,application/pdf"
            capture="environment"
            onChange={(e) => void onFile(e.target.files)}
          />
        </Button>
        {attachments.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            {attachments.length} adjunto(s) guardado(s) en el dispositivo. Se subirán al sincronizar, una vez que la
            actividad esté aprobada.
          </Typography>
        )}
      </Stack>

      <Typography variant="caption" color="text.secondary">
        {savedAt ? `Guardado en el dispositivo · ${savedAt.toLocaleTimeString('es-EC')}` : 'Sin cambios guardados aún'}
      </Typography>

      <Button
        variant="contained"
        size="large"
        onClick={() => void saveAndQueue()}
        disabled={!form.title.trim() || !form.activity_type_code || !form.parish_id}
      >
        Guardar y enviar a sincronización
      </Button>
    </Stack>
  );
}
