import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Grid,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { apiRequest } from '../../api/client';
import { PageHeader } from '../../components/layout/PageHeader';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import type { Study, Territory } from './types';
import StudyMap from './StudyMap';
import { downloadReport } from '../../api/downloads';
import { todayDateOnly } from '../../lib/dates';
const typeLabel = {
  POLL: 'ENCUESTA',
  TRACKING_POLL: 'TRACKING',
  EXIT_POLL: 'EXIT POLL',
  OTHER: 'OTRO',
};
export default function StudyDetailPage() {
  const { studyId = '', campaignId = '' } = useParams();
  const [tab, setTab] = useState(0);
  const [territory, setTerritory] = useState('');
  const query = useQuery({
    queryKey: ['survey-study', studyId],
    queryFn: () => apiRequest<Study>(`/survey-studies/${studyId}`),
  });
  const action = useMutation({
    mutationFn: (path: string) =>
      apiRequest(`/survey-studies/${studyId}/${path}`, { method: 'POST' }),
    onSuccess: () => query.refetch(),
  });
  const report = useMutation({
    mutationFn: async (format: 'PDF' | 'XLSX') => {
      const run = await apiRequest<{ id: string; artifact?: { original_download_name?: string } }>(
        `/campaigns/${campaignId}/reports/generate`,
        {
          method: 'POST',
          body: JSON.stringify({
            template_code: 'SURVEY_STUDY_REPORT',
            format,
            title: `Estudio territorial · ${s?.name ?? ''}`,
            report_date: todayDateOnly(),
            survey_ids: [studyId],
            electoral_process_ids: [],
            demographic_indicator_codes: [],
            include_comparisons: true,
          }),
        },
      );
      await downloadReport(
        `/campaigns/${campaignId}/reports/${run.id}/download`,
        run.artifact?.original_download_name ?? `estudio.${format.toLowerCase()}`,
      );
    },
  });
  const s = query.data;
  const selected: Territory | undefined = s?.territories?.find(
    (t) => t.id === (territory || s.territories?.[0]?.id),
  );
  const results = useMemo(
    () =>
      s?.results
        ?.filter((r) => r.study_territory_id === selected?.id)
        .sort((a, b) => b.percentage - a.percentage) ?? [],
    [s, selected],
  );
  if (query.isLoading) return <LoadingSkeleton />;
  if (!s || query.isError) return <ErrorState retry={() => void query.refetch()} />;
  const top = results[0],
    second = results[1];
  return (
    <Box sx={{ maxWidth: '100%', minWidth: 0, overflowX: 'hidden' }}>
      <PageHeader
        title={`${typeLabel[s.study_type]} TERRITORIAL — ${s.name}`}
        description="Lectura descriptiva de resultados agregados; no constituye pronóstico electoral."
        action={
          <Stack direction="row" flexWrap="wrap">
            <Button onClick={() => report.mutate('PDF')}>PDF</Button>
            <Button onClick={() => report.mutate('XLSX')}>XLSX</Button>
            {s.status === 'DRAFT' && (
              <Button onClick={() => action.mutate('validate')}>Validar</Button>
            )}
            {s.status === 'VALIDATED' && (
              <Button variant="contained" onClick={() => action.mutate('publish')}>
                Publicar
              </Button>
            )}
          </Stack>
        }
      />
      {s.exit_poll_warning && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <b>{s.is_official ? 'FUENTE OFICIAL' : 'NO OFICIAL CNE'}</b>
          <br />
          {s.exit_poll_warning}
        </Alert>
      )}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          {[
            ['Tipo', typeLabel[s.study_type]],
            [
              'Campo',
              `${formatDateEsEc(s.fieldwork_start_date)} – ${formatDateEsEc(s.fieldwork_end_date)}`,
            ],
            ['Muestra', formatIntegerEsEc(s.sample_size_total)],
            [
              'Margen de error declarado',
              s.margin_of_error != null
                ? `±${formatPercentEsEc(s.margin_of_error)}`
                : 'No declarado',
            ],
            ['Método', `${s.sampling_method} · ${s.collection_method}`],
            ['Responsable', s.pollster_name || 'No declarado'],
            ['Estado', s.status],
          ].map(([l, v]) => (
            <Grid key={l} size={{ xs: 12, sm: 6, lg: 3 }}>
              <Typography variant="caption">{l.toUpperCase()}</Typography>
              <Typography fontWeight={700}>{v}</Typography>
            </Grid>
          ))}
        </Grid>
      </Paper>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable">
        <Tab label="Resultados" />
        <Tab label="Metodología" />
        <Tab label="Territorio" />
        <Tab label="Fuentes" />
      </Tabs>
      {tab === 0 && (
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Paper variant="outlined" sx={{ p: 2, height: 420 }}>
              <TextField
                select
                label="Territorio"
                value={selected?.id || ''}
                onChange={(e) => setTerritory(e.target.value)}
                size="small"
                sx={{ minWidth: 220 }}
              >
                {s.territories?.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.parish_name || 'Cantón'}
                  </MenuItem>
                ))}
              </TextField>
              <ResponsiveContainer width="100%" height="85%">
                <BarChart data={results} layout="vertical" margin={{ left: 30, right: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    domain={[0, 1]}
                    tickFormatter={(v) => formatPercentEsEc(v)}
                  />
                  <YAxis dataKey="option_label" type="category" width={110} />
                  <Tooltip formatter={(v) => formatPercentEsEc(Number(v))} />
                  <Bar dataKey="percentage" fill="#315b7d" />
                </BarChart>
              </ResponsiveContainer>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Paper variant="outlined" sx={{ p: 3 }}>
              <Chip label="MAYOR PORCENTAJE DEL ESTUDIO" />
              <Typography variant="h2" sx={{ mt: 2 }}>
                {top?.option_label || 'Sin resultados'}
              </Typography>
              <Typography variant="h3">{top ? formatPercentEsEc(top.percentage) : '—'}</Typography>
              {top && second && (
                <Typography sx={{ mt: 2 }}>
                  Diferencia descriptiva respecto a la segunda opción:{' '}
                  {((top.percentage - second.percentage) * 100).toLocaleString('es-EC', {
                    minimumFractionDigits: 2,
                  })}{' '}
                  puntos porcentuales.
                </Typography>
              )}
              <Alert severity="info" sx={{ mt: 2 }}>
                Este resultado describe la muestra del estudio. No infiere ganador ni probabilidad
                de victoria.
              </Alert>
            </Paper>
          </Grid>
        </Grid>
      )}
      {tab === 0 && s.geography_level === 'PARISH' && (
        <Box sx={{ mt: 2 }}>
          <StudyMap campaignId={campaignId} study={s} />
        </Box>
      )}
      {tab === 1 && (
        <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
          <Typography variant="h2">Ficha metodológica</Typography>
          <Stack spacing={1} sx={{ mt: 2 }}>
            <Typography>
              <b>Universo:</b> {s.universe_description}
            </Typography>
            <Typography>
              <b>Muestreo:</b> {s.sampling_method}
            </Typography>
            <Typography>
              <b>Recolección:</b> {s.collection_method}
            </Typography>
            <Typography>
              <b>Completitud descriptiva:</b>{' '}
              {s.methodology_completeness === 'COMPLETE'
                ? 'Completa'
                : s.methodology_completeness === 'PARTIAL'
                  ? 'Parcial'
                  : 'Limitada'}
            </Typography>
            <Typography color="text.secondary">
              La completitud indica documentación disponible; no califica al estudio como confiable.
            </Typography>
          </Stack>
        </Paper>
      )}
      {tab === 2 && (
        <Grid container spacing={2} sx={{ mt: 1 }}>
          {s.territories?.map((t) => (
            <Grid key={t.id} size={{ xs: 12, md: 6 }}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="h2">{t.parish_name || 'Cobertura cantonal'}</Typography>
                <Typography>Muestra: {formatIntegerEsEc(t.sample_size)}</Typography>
                {s.results
                  ?.filter((r) => r.study_territory_id === t.id)
                  .sort((a, b) => b.percentage - a.percentage)
                  .map((r) => (
                    <Stack key={r.id} direction="row" justifyContent="space-between">
                      <span>{r.option_label}</span>
                      <b>{formatPercentEsEc(r.percentage)}</b>
                    </Stack>
                  ))}
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
      {tab === 3 && (
        <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
          <Typography>
            <b>Quién realizó el estudio:</b> {s.pollster_name || 'No declarado'}
          </Typography>
          <Typography>
            <b>Quién lo encargó:</b> {s.sponsor_name || 'No declarado'}
          </Typography>
          <Typography>
            <b>Fuente:</b> {s.source_type}
          </Typography>
          {s.source_url && (
            <Button href={s.source_url} target="_blank">
              Abrir fuente
            </Button>
          )}
        </Paper>
      )}
    </Box>
  );
}
