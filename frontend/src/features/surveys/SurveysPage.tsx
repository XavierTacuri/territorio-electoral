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
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { PageHeader } from '../../components/layout/PageHeader';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { formatDateEsEc, formatIntegerEsEc } from '../../lib/formatEsEc';
import type { Study, StudyPage } from '../survey-studies/types';
const typeLabel = {
  POLL: 'Encuesta',
  TRACKING_POLL: 'Tracking',
  EXIT_POLL: 'Exit poll',
  OTHER: 'Otro',
};
const statusLabel = {
  DRAFT: 'Borrador',
  VALIDATED: 'Validado',
  PUBLISHED: 'Publicado',
  ARCHIVED: 'Archivado',
};
const quality = { COMPLETE: 'Completa', PARTIAL: 'Parcial', LIMITED: 'Limitada' };
const initial = {
  code: '',
  name: '',
  description: '',
  study_type: 'POLL',
  fieldwork_start_date: '',
  fieldwork_end_date: '',
  geography_level: 'PARISH',
  sample_size_total: '',
  universe_description: '',
  sampling_method: '',
  collection_method: '',
  margin_of_error: '',
  pollster_name: '',
  sponsor_name: '',
  source_type: 'ESTUDIO',
  source_url: '',
  study_series_code: '',
  question_code: 'VOTE_INTENTION',
};
export default function SurveysPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('');
  const [studyType, setStudyType] = useState('');
  const [open, setOpen] = useState(false);
  const [compare, setCompare] = useState<string[]>([]);
  const [form, setForm] = useState(initial);
  const [error, setError] = useState('');
  const [territory, setTerritory] = useState('');
  const [fieldworkDate, setFieldworkDate] = useState('');
  const list = useQuery({
    queryKey: ['survey-studies', campaignId, status, studyType],
    queryFn: () =>
      apiRequest<StudyPage>(
        `/campaigns/${campaignId}/survey-studies?page=1&page_size=100${status ? '&status=' + status : ''}${studyType ? '&study_type=' + studyType : ''}`,
      ),
  });
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiRequest<Study>(`/campaigns/${campaignId}/survey-studies`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (s) => navigate(`/app/campaigns/${campaignId}/survey-studies/${s.id}`),
  });
  const submit = async () => {
    try {
      setError('');
      await create.mutateAsync({
        ...form,
        sample_size_total: Number(form.sample_size_total),
        margin_of_error: form.margin_of_error ? Number(form.margin_of_error) / 100 : null,
        source_url: form.source_url || null,
        description: form.description || null,
        pollster_name: form.pollster_name || null,
        sponsor_name: form.sponsor_name || null,
        study_series_code: form.study_series_code || null,
        is_official: false,
        publication_date: null,
        confidence_level: null,
        notes: null,
        election_process_id: null,
        result_count_notes: null,
      });
    } catch {
      setError('Revise la información general y metodológica del estudio.');
    }
  };
  return (
    <>
      <PageHeader
        title="ENCUESTAS Y ESTUDIOS"
        description="Resultados agregados de encuestas, tracking polls y exit polls."
        action={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button onClick={() => navigate(`/app/campaigns/${campaignId}/questionnaires`)}>
              Gestionar cuestionarios
            </Button>
            <Button onClick={() => navigate(`/app/campaigns/${campaignId}/survey-studies/import`)}>
              Importar resultados
            </Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
              Nuevo estudio
            </Button>
          </Stack>
        }
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
        <TextField
          select
          label="Tipo"
          value={studyType}
          onChange={(e) => setStudyType(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(typeLabel).map(([v, l]) => (
            <MenuItem key={v} value={v}>
              {l}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Territorio"
          value={territory}
          onChange={(e) => setTerritory(e.target.value)}
          sx={{ minWidth: 180 }}
        />
        <TextField
          type="date"
          label="Fecha"
          value={fieldworkDate}
          onChange={(e) => setFieldworkDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 180 }}
        />
        <TextField
          select
          label="Estado"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(statusLabel).map(([v, l]) => (
            <MenuItem key={v} value={v}>
              {l}
            </MenuItem>
          ))}
        </TextField>
        <Button
          startIcon={<CompareArrowsIcon />}
          disabled={compare.length < 2}
          onClick={() =>
            navigate(`/app/campaigns/${campaignId}/survey-studies/compare?ids=${compare.join(',')}`)
          }
        >
          Comparar estudios ({compare.length}/3)
        </Button>
      </Stack>
      {list.isLoading ? (
        <LoadingSkeleton />
      ) : list.isError ? (
        <ErrorState retry={() => void list.refetch()} />
      ) : list.data?.items.length === 0 ? (
        <Alert severity="info">No hay estudios registrados.</Alert>
      ) : (
        <Grid container spacing={2}>
          {list.data?.items.map((s) => (
            <Grid key={s.id} size={{ xs: 12, md: 6, lg: 4 }}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Stack direction="row" justifyContent="space-between">
                  <Chip label={typeLabel[s.study_type]} />
                  <Chip
                    color={s.status === 'PUBLISHED' ? 'success' : 'default'}
                    label={statusLabel[s.status]}
                  />
                </Stack>
                <Typography variant="h2" sx={{ mt: 2 }}>
                  {s.name}
                </Typography>
                <Typography color="text.secondary">
                  Campo: {formatDateEsEc(s.fieldwork_start_date)} –{' '}
                  {formatDateEsEc(s.fieldwork_end_date)}
                </Typography>
                <Grid container spacing={1} sx={{ my: 2 }}>
                  <Grid size={6}>
                    <Typography variant="caption">MUESTRA</Typography>
                    <Typography fontWeight={700}>
                      {formatIntegerEsEc(s.sample_size_total)}
                    </Typography>
                  </Grid>
                  <Grid size={6}>
                    <Typography variant="caption">COBERTURA</Typography>
                    <Typography fontWeight={700}>
                      {s.geography_level === 'PARISH' ? 'Parroquial' : 'Cantonal'}
                    </Typography>
                  </Grid>
                  <Grid size={12}>
                    <Typography variant="caption">METODOLOGÍA</Typography>
                    <Typography>{quality[s.methodology_completeness]}</Typography>
                  </Grid>
                </Grid>
                <Stack direction="row">
                  <Button
                    onClick={() => navigate(`/app/campaigns/${campaignId}/survey-studies/${s.id}`)}
                  >
                    Ver estudio
                  </Button>
                  <Button
                    onClick={() =>
                      setCompare((v) =>
                        v.includes(s.id)
                          ? v.filter((x) => x !== s.id)
                          : v.length < 3
                            ? [...v, s.id]
                            : v,
                      )
                    }
                  >
                    {compare.includes(s.id) ? 'Quitar' : 'Comparar'}
                  </Button>
                </Stack>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>NUEVO ESTUDIO · Información y metodología</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Solo registre resultados agregados. No incluya datos personales ni respuestas
            individuales.
          </Alert>
          {error && <Alert severity="error">{error}</Alert>}
          <Grid container spacing={2} sx={{ mt: 0 }}>
            {[
              ['code', 'Código'],
              ['name', 'Nombre'],
              ['fieldwork_start_date', 'Inicio de campo'],
              ['fieldwork_end_date', 'Fin de campo'],
              ['sample_size_total', 'Muestra total'],
              ['universe_description', 'Universo'],
              ['sampling_method', 'Método de muestreo'],
              ['collection_method', 'Método de recolección'],
              ['pollster_name', 'Responsable'],
              ['sponsor_name', 'Quién encargó'],
              ['source_type', 'Tipo de fuente'],
              ['source_url', 'URL de fuente'],
            ].map(([k, l]) => (
              <Grid key={k} size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  label={l}
                  type={k.includes('date') ? 'date' : k === 'sample_size_total' ? 'number' : 'text'}
                  InputLabelProps={k.includes('date') ? { shrink: true } : undefined}
                  value={form[k as keyof typeof form]}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                />
              </Grid>
            ))}
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                select
                label="Tipo"
                value={form.study_type}
                onChange={(e) => setForm({ ...form, study_type: e.target.value })}
              >
                {Object.entries(typeLabel).map(([v, l]) => (
                  <MenuItem key={v} value={v}>
                    {l}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                select
                label="Nivel"
                value={form.geography_level}
                onChange={(e) => setForm({ ...form, geography_level: e.target.value })}
              >
                <MenuItem value="CANTON">Cantón</MenuItem>
                <MenuItem value="PARISH">Parroquia</MenuItem>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                label="Margen de error (%)"
                type="number"
                value={form.margin_of_error}
                onChange={(e) => setForm({ ...form, margin_of_error: e.target.value })}
              />
            </Grid>
            {form.study_type === 'TRACKING_POLL' && (
              <Grid size={12}>
                <TextField
                  fullWidth
                  required
                  label="Código de serie"
                  value={form.study_series_code}
                  onChange={(e) => setForm({ ...form, study_series_code: e.target.value })}
                />
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={submit} disabled={create.isPending}>
            Crear estudio
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
