import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest, BASE_URL } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canManageCneExitPoll, canManageGeneralSurvey } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateEsEc, formatIntegerEsEc } from '../../lib/formatEsEc';
import type { Option, Study, StudyPage, Territory } from '../survey-studies/types';

type QuestionType = 'SINGLE_CHOICE' | 'MULTIPLE_CHOICE' | 'SCALE' | 'RATING' | 'VOTE_INTENTION';
type DraftOption = { label: string; percentage: string; baseN: string };
type DraftQuestion = { text: string; type: QuestionType; options: DraftOption[] };
type Parish = { id: number; name: string; dpa_code: string };

const questionLabels: Record<QuestionType, string> = {
  SINGLE_CHOICE: 'Opción única',
  MULTIPLE_CHOICE: 'Respuesta múltiple',
  SCALE: 'Escala',
  RATING: 'Valoración',
  VOTE_INTENTION: 'Intención de voto agregada',
};
const statusLabels: Record<string, string> = {
  DRAFT: 'Borrador',
  VALIDATED: 'Borrador',
  PUBLISHED: 'Publicada',
  ARCHIVED: 'Archivada',
};
const emptyOption = (): DraftOption => ({ label: '', percentage: '', baseN: '' });
const emptyQuestion = (): DraftQuestion => ({
  text: '',
  type: 'SINGLE_CHOICE',
  options: [emptyOption(), emptyOption()],
});
const initialForm = {
  name: '',
  fieldwork_start_date: '',
  fieldwork_end_date: '',
  pollster_name: '',
  sample_size_total: '',
  methodology: '',
  margin_of_error: '',
  confidence_level: '',
  geography_level: 'CANTON',
  parish_id: '',
  notes: '',
  election_process_id: '',
  publication_date: '',
  source_name: '',
  source_url: '',
  source_document: '',
};

export default function SurveysPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { active } = useCampaign();
  const canManage = canManageGeneralSurvey(user);
  const canManageCne = canManageCneExitPoll(user);
  const [open, setOpen] = useState(false);
  const [cneOpen, setCneOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [questions, setQuestions] = useState<DraftQuestion[]>([emptyQuestion()]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const list = useQuery({
    queryKey: ['survey-studies', campaignId],
    queryFn: () =>
      apiRequest<StudyPage>(`/campaigns/${campaignId}/survey-studies?page=1&page_size=100`),
  });
  const parishes = useQuery({
    queryKey: ['survey-parishes', active?.canton_id],
    enabled: open && form.geography_level === 'PARISH' && !!active?.canton_id,
    queryFn: () => apiRequest<Parish[]>(`/parishes?canton_id=${active!.canton_id}&is_active=true`),
  });
  const processes = useQuery({
    queryKey: ['survey-electoral-processes'],
    enabled: cneOpen,
    queryFn: () => apiRequest<{ id: string; name: string }[]>('/electoral-processes'),
  });
  const updateQuestion = (index: number, patch: Partial<DraftQuestion>) =>
    setQuestions((items) => items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  const updateOption = (qi: number, oi: number, patch: Partial<DraftOption>) =>
    setQuestions((items) =>
      items.map((q, i) =>
        i === qi
          ? { ...q, options: q.options.map((o, j) => (j === oi ? { ...o, ...patch } : o)) }
          : q,
      ),
    );
  const submit = async (kind: 'GENERAL_SURVEY' | 'CNE_EXIT_POLL' = 'GENERAL_SURVEY') => {
    if (
      !form.name ||
      !form.fieldwork_start_date ||
      !form.fieldwork_end_date ||
      !form.sample_size_total ||
      !form.methodology ||
      questions.some(
        (q) =>
          !q.text || q.options.length < 2 || q.options.some((o) => !o.label || o.percentage === ''),
      )
    ) {
      setError('Complete los campos obligatorios y agregue al menos dos opciones por pregunta.');
      return;
    }
    if (form.geography_level === 'PARISH' && !form.parish_id) {
      setError('Seleccione la parroquia cuyos resultados están realmente agregados.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (
        kind === 'CNE_EXIT_POLL' &&
        (!form.election_process_id ||
          !form.publication_date ||
          !form.source_name ||
          (!form.source_url && !form.source_document))
      ) {
        setError(
          'El exit poll requiere proceso electoral, publicación, fuente y URL o documento verificable.',
        );
        setSaving(false);
        return;
      }
      const code = `${kind === 'GENERAL_SURVEY' ? 'GENERAL' : 'CNE_EXIT'}_${Date.now()}`;
      const study = await apiRequest<Study>(`/campaigns/${campaignId}/survey-studies`, {
        method: 'POST',
        body: JSON.stringify({
          code,
          name: form.name,
          description: null,
          study_type: kind,
          fieldwork_start_date: form.fieldwork_start_date,
          fieldwork_end_date: form.fieldwork_end_date,
          publication_date: kind === 'CNE_EXIT_POLL' ? form.publication_date : null,
          geography_level: form.geography_level,
          sample_size_total: Number(form.sample_size_total),
          universe_description: `Ámbito de la campaña ${active?.name ?? ''}`,
          sampling_method: form.methodology,
          collection_method: form.methodology,
          confidence_level: form.confidence_level ? Number(form.confidence_level) / 100 : null,
          margin_of_error: form.margin_of_error ? Number(form.margin_of_error) / 100 : null,
          pollster_name: form.pollster_name || null,
          sponsor_name: null,
          source_type: kind === 'CNE_EXIT_POLL' ? 'CNE_EXIT_POLL_SOURCE' : 'ESTUDIO',
          source_url: form.source_url || null,
          source_name: form.source_name || null,
          source_document: form.source_document || null,
          notes: form.notes || null,
          is_official: false,
          study_series_code: null,
          question_code: 'AGGREGATED_QUESTIONS',
          election_process_id: form.election_process_id || null,
          result_count_notes: null,
        }),
      });
      const territory = await apiRequest<Territory>(`/survey-studies/${study.id}/territories`, {
        method: 'POST',
        body: JSON.stringify({
          parish_id: form.geography_level === 'PARISH' ? Number(form.parish_id) : null,
          sample_size: Number(form.sample_size_total),
          margin_of_error: form.margin_of_error ? Number(form.margin_of_error) / 100 : null,
          coverage_notes: null,
        }),
      });
      const resultRows: {
        study_territory_id: string;
        option_id: string;
        response_count: number | null;
        percentage: number;
      }[] = [];
      for (const [qi, question] of questions.entries())
        for (const [oi, option] of question.options.entries()) {
          const created = await apiRequest<Option>(`/survey-studies/${study.id}/options`, {
            method: 'POST',
            body: JSON.stringify({
              question_code: `Q${qi + 1}`,
              question_text: question.text,
              question_type: question.type,
              code: `O${oi + 1}`,
              label: option.label,
              option_type: 'OTHER',
              display_order: oi,
            }),
          });
          resultRows.push({
            study_territory_id: territory.id,
            option_id: created.id,
            response_count: option.baseN ? Number(option.baseN) : null,
            percentage: Number(option.percentage.replace(',', '.')) / 100,
          });
        }
      await apiRequest(`/survey-studies/${study.id}/results`, {
        method: 'PUT',
        body: JSON.stringify(resultRows),
      });
      setOpen(false);
      setCneOpen(false);
      setForm(initialForm);
      setQuestions([emptyQuestion()]);
      await list.refetch();
      navigate(`/app/campaigns/${campaignId}/survey-studies/${study.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No se pudo crear la encuesta.');
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <PageHeader
        title="Encuestas y estudios"
        description="Resultados agregados de estudios de la campaña."
        action={
          canManage ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                onClick={() => navigate(`/app/campaigns/${campaignId}/survey-studies/import`)}
              >
                IMPORTAR CSV
              </Button>
              <Button href={`${BASE_URL}/campaigns/${campaignId}/survey-imports/template`}>
                DESCARGAR PLANTILLA
              </Button>
              {canManageCne && (
                <Button onClick={() => setCneOpen(true)}>REGISTRAR EXIT POLL</Button>
              )}
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
                NUEVA ENCUESTA
              </Button>
            </Stack>
          ) : undefined
        }
      />
      {list.isLoading ? (
        <LoadingSkeleton />
      ) : list.isError ? (
        <ErrorState retry={() => void list.refetch()} />
      ) : !list.data?.items.length ? (
        <Alert severity="info">No hay encuestas publicadas disponibles.</Alert>
      ) : (
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Grid container sx={{ p: 2, fontWeight: 700, minWidth: 760 }}>
            <Grid size={4}>Estudio</Grid>
            <Grid size={2}>Trabajo de campo</Grid>
            <Grid size={1.5}>Muestra</Grid>
            <Grid size={1.5}>Cobertura</Grid>
            <Grid size={1.5}>Estado</Grid>
            <Grid size={1.5}>Acciones</Grid>
          </Grid>
          {list.data.items.map((s) => (
            <Grid
              container
              key={s.id}
              alignItems="center"
              sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider', minWidth: 760 }}
            >
              <Grid size={4}>
                <Typography fontWeight={700}>{s.name}</Typography>
                <Typography variant="caption">
                  {s.study_type === 'CNE_EXIT_POLL'
                    ? 'Exit poll / Boca de urna'
                    : 'Encuesta general'}
                </Typography>
              </Grid>
              <Grid size={2}>
                {formatDateEsEc(s.fieldwork_start_date)} – {formatDateEsEc(s.fieldwork_end_date)}
              </Grid>
              <Grid size={1.5}>{formatIntegerEsEc(s.sample_size_total)}</Grid>
              <Grid size={1.5}>{s.geography_level === 'PARISH' ? 'Parroquial' : 'Cantonal'}</Grid>
              <Grid size={1.5}>
                <Chip size="small" label={statusLabels[s.status] ?? s.status} />
              </Grid>
              <Grid size={1.5}>
                <Button
                  onClick={() => navigate(`/app/campaigns/${campaignId}/survey-studies/${s.id}`)}
                >
                  Ver resultados
                </Button>
              </Grid>
            </Grid>
          ))}
        </Paper>
      )}
      <Dialog
        open={open || cneOpen}
        onClose={() => !saving && (setOpen(false), setCneOpen(false))}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>
          {cneOpen ? 'Registrar exit poll / boca de urna' : 'Nueva encuesta general'}
        </DialogTitle>
        <DialogContent>
          {cneOpen && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Este estudio no sustituye los resultados oficiales del proceso electoral. Si el
              material es escrutinio oficial CNE, debe cargarse en el módulo electoral.
            </Alert>
          )}
          <Alert severity="info" sx={{ mb: 2 }}>
            Registre únicamente resultados agregados. No incluya nombres, identificaciones,
            teléfonos ni respuestas individuales.
          </Alert>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <Grid container spacing={2}>
            {[
              ['Campaña', active?.name],
              ['Provincia', active?.province_name],
              ['Cantón', active?.canton_name],
            ].map(([label, value]) => (
              <Grid key={label} size={{ xs: 12, sm: 4 }}>
                <TextField
                  fullWidth
                  label={label}
                  value={value ?? ''}
                  slotProps={{ input: { readOnly: true } }}
                />
              </Grid>
            ))}
            <Grid size={12}>
              <TextField
                required
                fullWidth
                label="Nombre"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                required
                fullWidth
                type="date"
                label="Fecha inicio trabajo de campo"
                value={form.fieldwork_start_date}
                onChange={(e) => setForm({ ...form, fieldwork_start_date: e.target.value })}
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                required
                fullWidth
                type="date"
                label="Fecha fin trabajo de campo"
                value={form.fieldwork_end_date}
                onChange={(e) => setForm({ ...form, fieldwork_end_date: e.target.value })}
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                label="Responsable / encuestadora"
                value={form.pollster_name}
                onChange={(e) => setForm({ ...form, pollster_name: e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                required
                fullWidth
                type="number"
                label="Tamaño de muestra"
                value={form.sample_size_total}
                onChange={(e) => setForm({ ...form, sample_size_total: e.target.value })}
              />
            </Grid>
            <Grid size={12}>
              <TextField
                required
                fullWidth
                multiline
                minRows={2}
                label="Metodología"
                value={form.methodology}
                onChange={(e) => setForm({ ...form, methodology: e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                type="number"
                label="Margen de error (%)"
                value={form.margin_of_error}
                onChange={(e) => setForm({ ...form, margin_of_error: e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                type="number"
                label="Nivel de confianza (%)"
                value={form.confidence_level}
                onChange={(e) => setForm({ ...form, confidence_level: e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                select
                fullWidth
                label="Cobertura"
                value={form.geography_level}
                onChange={(e) =>
                  setForm({ ...form, geography_level: e.target.value, parish_id: '' })
                }
              >
                <MenuItem value="CANTON">Cantonal</MenuItem>
                <MenuItem value="PARISH">Parroquial</MenuItem>
              </TextField>
            </Grid>
            {form.geography_level === 'PARISH' && (
              <Grid size={12}>
                <TextField
                  required
                  select
                  fullWidth
                  label="Parroquia con resultados agregados"
                  value={form.parish_id}
                  onChange={(e) => setForm({ ...form, parish_id: e.target.value })}
                >
                  {(parishes.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={p.id}>
                      {p.name} · {p.dpa_code}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            )}
            <Grid size={12}>
              <TextField
                fullWidth
                multiline
                minRows={2}
                label="Observaciones"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Grid>
            {cneOpen && (
              <>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    required
                    select
                    fullWidth
                    label="Proceso electoral"
                    value={form.election_process_id}
                    onChange={(e) => setForm({ ...form, election_process_id: e.target.value })}
                  >
                    {(processes.data ?? []).map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.name}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    required
                    type="date"
                    fullWidth
                    label="Fecha de publicación"
                    value={form.publication_date}
                    onChange={(e) => setForm({ ...form, publication_date: e.target.value })}
                    slotProps={{ inputLabel: { shrink: true } }}
                  />
                </Grid>
                <Grid size={12}>
                  <TextField
                    required
                    fullWidth
                    label="Fuente"
                    value={form.source_name}
                    onChange={(e) => setForm({ ...form, source_name: e.target.value })}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    fullWidth
                    label="URL verificable"
                    value={form.source_url}
                    onChange={(e) => setForm({ ...form, source_url: e.target.value })}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    fullWidth
                    label="Documento / referencia"
                    value={form.source_document}
                    onChange={(e) => setForm({ ...form, source_document: e.target.value })}
                  />
                </Grid>
              </>
            )}
          </Grid>
          <Typography variant="h2" sx={{ mt: 4, mb: 2 }}>
            Resultados agregados
          </Typography>
          <Stack spacing={2}>
            {questions.map((q, qi) => (
              <Paper key={qi} variant="outlined" sx={{ p: 2 }}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, md: 8 }}>
                    <TextField
                      required
                      fullWidth
                      label="Texto de la pregunta"
                      value={q.text}
                      onChange={(e) => updateQuestion(qi, { text: e.target.value })}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <TextField
                      required
                      select
                      fullWidth
                      label="Tipo de pregunta"
                      value={q.type}
                      onChange={(e) => updateQuestion(qi, { type: e.target.value as QuestionType })}
                    >
                      {Object.entries(questionLabels).map(([value, label]) => (
                        <MenuItem key={value} value={value}>
                          {label}
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                  {q.options.map((o, oi) => (
                    <Grid container size={12} spacing={1} key={oi}>
                      <Grid size={6}>
                        <TextField
                          required
                          fullWidth
                          label="Opción"
                          value={o.label}
                          onChange={(e) => updateOption(qi, oi, { label: e.target.value })}
                        />
                      </Grid>
                      <Grid size={3}>
                        <TextField
                          required
                          fullWidth
                          label="Porcentaje"
                          value={o.percentage}
                          onChange={(e) => updateOption(qi, oi, { percentage: e.target.value })}
                        />
                      </Grid>
                      <Grid size={3}>
                        <TextField
                          fullWidth
                          type="number"
                          label="Base N"
                          value={o.baseN}
                          onChange={(e) => updateOption(qi, oi, { baseN: e.target.value })}
                        />
                      </Grid>
                    </Grid>
                  ))}
                  <Grid size={12}>
                    <Button
                      onClick={() => updateQuestion(qi, { options: [...q.options, emptyOption()] })}
                    >
                      + AGREGAR OPCIÓN
                    </Button>
                  </Grid>
                </Grid>
              </Paper>
            ))}
          </Stack>
          <Button
            sx={{ mt: 2 }}
            onClick={() => setQuestions((items) => [...items, emptyQuestion()])}
          >
            + AGREGAR PREGUNTA
          </Button>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false);
              setCneOpen(false);
            }}
            disabled={saving}
          >
            Cancelar
          </Button>
          <Button
            variant="contained"
            onClick={() => submit(cneOpen ? 'CNE_EXIT_POLL' : 'GENERAL_SURVEY')}
            disabled={saving}
          >
            {saving ? 'Guardando…' : cneOpen ? 'Registrar exit poll' : 'Crear encuesta'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
