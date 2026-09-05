import { Alert, Box, Button, Grid, LinearProgress, Paper, Stack, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { canManageCneExitPoll, canManageGeneralSurvey } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateEsEc, formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import type { Study } from './types';

const questionLabels = { SINGLE_CHOICE: 'Opción única', MULTIPLE_CHOICE: 'Respuesta múltiple', SCALE: 'Escala', RATING: 'Valoración', VOTE_INTENTION: 'Intención de voto agregada' } as const;

export default function StudyDetailPage() {
  const { studyId = '', campaignId = '' } = useParams(); const { user } = useAuth();
  const query = useQuery({ queryKey: ['survey-study', campaignId, studyId], queryFn: () => apiRequest<Study>(`/survey-studies/${studyId}`) });
  const action = useMutation({ mutationFn: (path: 'publish' | 'archive') => apiRequest(`/survey-studies/${studyId}/${path}`, { method: 'POST' }), onSuccess: () => query.refetch() });
  if (query.isLoading) return <LoadingSkeleton />; if (!query.data || query.isError) return <ErrorState retry={() => void query.refetch()} />;
  const study = query.data; const canEdit = study.study_type === 'CNE_EXIT_POLL' ? canManageCneExitPoll(user) : canManageGeneralSurvey(user);
  const options = study.options ?? []; const results = study.results ?? []; const territories = study.territories ?? [];
  const questionCodes = [...new Set(options.map((option) => option.question_code))];
  return <Box sx={{ maxWidth: 1100 }}><PageHeader title={study.name} description={study.study_type === 'CNE_EXIT_POLL' ? 'Exit poll / Boca de urna' : 'Encuesta general'} action={<Stack direction="row" spacing={1} flexWrap="wrap"><Button href={`/app/campaigns/${campaignId}/territory-ai?study_id=${studyId}&question=${encodeURIComponent(`Resume la encuesta ${study.name}`)}`}>Preguntar a Territorio IA</Button>{canEdit && ['DRAFT', 'VALIDATED'].includes(study.status) && <Button variant="contained" onClick={() => action.mutate('publish')} disabled={action.isPending}>PUBLICAR</Button>}{canEdit && study.status === 'PUBLISHED' && <Button onClick={() => action.mutate('archive')} disabled={action.isPending}>ARCHIVAR</Button>}</Stack>} />
    {study.name.startsWith('[DEMO]') && <Alert severity="info" sx={{ mb: 2 }}>Datos simulados para demostración.</Alert>}
    {study.exit_poll_warning && <Alert severity="warning" sx={{ mb: 2 }}>{study.exit_poll_warning}</Alert>}
    <Typography variant="h2" sx={{ mb: 2 }}>Resultado</Typography><Alert severity="info" sx={{ mb: 3 }}>Los porcentajes describen exclusivamente los resultados agregados observados en este estudio. No constituyen una predicción electoral.</Alert>
    <Stack spacing={3}>{territories.map((territory) => <Box key={territory.id}><Typography variant="h3" sx={{ mb: 1 }}>{territory.parish_name ? `Parroquia: ${territory.parish_name}` : 'Cobertura cantonal'}</Typography>{questionCodes.map((code) => { const questionOptions = options.filter((option) => option.question_code === code); const questionResults = results.filter((result) => result.study_territory_id === territory.id && questionOptions.some((option) => option.id === result.option_id)); if (!questionResults.length) return null; return <Paper key={`${territory.id}-${code}`} variant="outlined" sx={{ p: 2, mb: 2 }}><Typography variant="h2">{questionOptions[0]?.question_text}</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>{questionLabels[questionOptions[0]?.question_type] ?? questionOptions[0]?.question_type}</Typography><Stack spacing={2}>{questionResults.map((result) => <Box key={result.id}><Stack direction="row" justifyContent="space-between"><Typography>{result.option_label}</Typography><Typography fontWeight={700}>{formatPercentEsEc(result.percentage)}</Typography></Stack><LinearProgress variant="determinate" value={result.percentage * 100} sx={{ height: 8, borderRadius: 1, mt: 0.5 }} />{result.response_count != null && <Typography variant="caption">Base N: {formatIntegerEsEc(result.response_count)}</Typography>}</Box>)}</Stack></Paper>; })}</Box>)}</Stack>
    <Typography variant="h2" sx={{ mt: 4, mb: 2 }}>Metodología</Typography><Paper variant="outlined" sx={{ p: 2 }}><Grid container spacing={2}><Grid size={{ xs: 12, sm: 6 }}><b>Trabajo de campo</b><br />{formatDateEsEc(study.fieldwork_start_date)} – {formatDateEsEc(study.fieldwork_end_date)}</Grid><Grid size={{ xs: 12, sm: 6 }}><b>Muestra</b><br />{formatIntegerEsEc(study.sample_size_total)}</Grid><Grid size={12}><b>Metodología</b><br />{study.sampling_method}</Grid><Grid size={{ xs: 12, sm: 6 }}><b>Responsable / encuestadora</b><br />{study.pollster_name || 'No declarado'}</Grid><Grid size={{ xs: 12, sm: 6 }}><b>Margen de error</b><br />{study.margin_of_error == null ? 'No declarado' : `±${formatPercentEsEc(study.margin_of_error)}`}</Grid><Grid size={{ xs: 12, sm: 6 }}><b>Nivel de confianza</b><br />{study.confidence_level == null ? 'No declarado' : formatPercentEsEc(study.confidence_level)}</Grid></Grid></Paper>
    <Typography variant="h2" sx={{ mt: 4, mb: 2 }}>Cobertura</Typography><Paper variant="outlined" sx={{ p: 2 }}>{study.geography_level === 'PARISH' ? territories.map((t) => t.parish_name).filter(Boolean).join(', ') : 'Cantonal'}</Paper>
    <Typography variant="h2" sx={{ mt: 4, mb: 2 }}>Documentación / fuente</Typography><Paper variant="outlined" sx={{ p: 2 }}><Typography>{study.source_name || study.source_type || 'Sin documentación adicional'}</Typography>{study.source_document && <Typography>{study.source_document}</Typography>}{study.source_url && <Button href={study.source_url} target="_blank" rel="noreferrer">Abrir fuente verificable</Button>}</Paper>
    <Typography variant="h2" sx={{ mt: 4, mb: 2 }}>Limitaciones</Typography><Paper variant="outlined" sx={{ p: 2, mb: 4 }}>{study.notes || 'No se registraron observaciones adicionales. Los resultados corresponden al universo, cobertura y metodología declarados.'}</Paper>
  </Box>;
}
