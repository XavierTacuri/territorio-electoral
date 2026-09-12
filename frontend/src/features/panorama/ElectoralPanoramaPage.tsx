import { Alert, Button, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { isCoordinatorOnly } from '../../auth/permissions';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';

type Historical = { ballots_cast: number; turnout_rate: number | null };
type Parish = { demographics: Record<string, number> };
type Analysis = {
  snapshot: { registered_voters: number };
  projection: { expected_voters_central: number };
  historical: Record<string, Historical>;
  demographics: { year: number; parishes: Parish[] };
};
type Operation = {
  activities: { total?: number; demo?: number; completed?: number };
  needs: { total?: number; demo?: number; open?: number };
  commitments: { pending?: number; in_progress?: number };
  coverage: { total_parishes?: number; with_activities?: number };
};
type Page<T> = { items: T[] };
type Study = {
  id: string;
  name: string;
  fieldwork_start_date: string;
  fieldwork_end_date: string;
  sample_size_total: number;
  geography_level: 'CANTON' | 'PARISH';
  study_type: string;
  methodology_completeness: string;
};
type StudyDetail = Study & {
  sampling_method: string;
  options?: { id: string; question_text: string }[];
  results?: { option_id: string; option_label: string; percentage: number }[];
};
type PublicSummary = { total_items?: number; recent_items?: number };

export const panoramaQuestions = [
  '¿Cuál es el panorama electoral actual?',
  '¿Cómo ha cambiado la participación electoral?',
  '¿Qué necesidades se han registrado por parroquia?',
  '¿Qué temas se repiten en las actividades?',
  '¿Qué estudios agregados están disponibles?',
  'Resume la evidencia disponible sobre vialidad.',
] as const;

function Metric({ title, value, note }: { title: string; value: string; note?: string }) {
  return (
    <Grid size={{ xs: 12, sm: 6, lg: 4 }}>
      <Card variant="outlined" sx={{ height: '100%' }}>
        <CardContent>
          <Typography color="text.secondary" variant="body2">
            {title}
          </Typography>
          <Typography variant="h2" sx={{ my: 1 }}>
            {value}
          </Typography>
          {note && (
            <Typography color="text.secondary" variant="caption">
              {note}
            </Typography>
          )}
        </CardContent>
      </Card>
    </Grid>
  );
}
function Detail({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Grid size={{ xs: 12, md: 6 }}>
      <Card variant="outlined" sx={{ height: '100%' }}>
        <CardContent>
          <Typography variant="h2" sx={{ mb: 1 }}>
            {title}
          </Typography>
          {children}
        </CardContent>
      </Card>
    </Grid>
  );
}

export default function ElectoralPanoramaPage() {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const isCoordinator = isCoordinatorOnly(user);
  const analysis = useQuery({
    queryKey: ['panorama-analysis', campaignId],
    queryFn: () => apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`),
  });
  const operation = useQuery({
    queryKey: ['panorama-operation', campaignId],
    queryFn: () => apiRequest<Operation>(`/campaigns/${campaignId}/operations/summary`),
  });
  const studies = useQuery({
    queryKey: ['panorama-studies', campaignId],
    queryFn: () =>
      apiRequest<Page<Study>>(
        `/campaigns/${campaignId}/survey-studies?status=PUBLISHED&page=1&page_size=20`,
      ),
  });
  const latestStudy = useQuery({
    queryKey: ['panorama-latest-study', studies.data?.items[0]?.id],
    enabled: !!studies.data?.items[0]?.id,
    queryFn: () => apiRequest<StudyDetail>(`/survey-studies/${studies.data!.items[0].id}`),
  });
  const publicInfo = useQuery({
    queryKey: ['panorama-public', campaignId],
    queryFn: () =>
      apiRequest<PublicSummary>(`/campaigns/${campaignId}/public-intelligence/summary`),
  });
  const aiPath = (question: string) =>
    `/app/campaigns/${campaignId}/territory-ai?question=${encodeURIComponent(question)}`;
  const a = analysis.data,
    o = operation.data;
  const registered = a?.snapshot.registered_voters,
    central = a?.projection.expected_voters_central;
  const centralRate = registered && central != null ? central / registered : null;
  const population = a?.demographics.parishes.reduce(
    (sum, parish) => sum + (parish.demographics.POP_TOTAL ?? 0),
    0,
  );
  const totalParishes = o?.coverage.total_parishes ?? 0;
  const withActivities = o?.coverage.with_activities ?? 0;
  const activitiesTotal = o?.activities.total ?? o?.activities.completed ?? 0;
  const needsTotal = o?.needs.total ?? o?.needs.open ?? 0;
  const demoStudies =
    studies.data?.items.filter((study) => study.name.startsWith('[DEMO]')).length ?? 0;
  const hasDemoData = demoStudies > 0 || !!o?.activities.demo || !!o?.needs.demo;
  const publicCount = publicInfo.data?.recent_items ?? publicInfo.data?.total_items ?? 0;
  return (
    <>
      <PageHeader
        title="Panorama electoral"
        description="Síntesis descriptiva y trazable de la campaña seleccionada. No constituye una predicción electoral."
        action={
          !isCoordinator && (
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
              <Button
                component={RouterLink}
                to={aiPath('¿Cuál es el panorama electoral actual?')}
                variant="contained"
              >
                CONSULTAR EN TERRITORIO IA
              </Button>
              <Button
                component={RouterLink}
                to={`/app/campaigns/${campaignId}/reports?type=CURRENT_ELECTION_EXECUTIVE`}
              >
                GENERAR INFORME
              </Button>
            </Stack>
          )
        }
      />
      {(analysis.isError || operation.isError) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Parte de la información no está disponible en este momento.
        </Alert>
      )}
      {hasDemoData && (
        <Alert severity="info" icon={false} sx={{ mb: 2 }}>
          Esta campaña contiene datos de demostración.
        </Alert>
      )}
      <Grid
        container
        spacing={2}
        sx={{ mb: 3 }}
        aria-label="Indicadores descriptivos del panorama electoral"
      >
        {registered != null && (
          <Metric
            title="Electores actuales"
            value={formatIntegerEsEc(registered)}
            note="Electores registrados · CNE"
          />
        )}
        {central != null && (
          <Metric
            title="Votantes esperados"
            value={formatIntegerEsEc(central)}
            note="Escenario estimado"
          />
        )}
        {centralRate != null && (
          <Metric
            title="Participación estimada"
            value={formatPercentEsEc(centralRate)}
            note="Modelo de participación"
          />
        )}
        {o && (
          <Metric
            title="Actividades"
            value={formatIntegerEsEc(activitiesTotal)}
            note="Cobertura operativa agregada"
          />
        )}
        {o && (
          <Metric
            title="Necesidades"
            value={formatIntegerEsEc(needsTotal)}
            note="Registro territorial agregado"
          />
        )}
        {o && (
          <Metric
            title="Parroquias con actividad"
            value={`${formatIntegerEsEc(withActivities)} / ${formatIntegerEsEc(totalParishes)}`}
          />
        )}
      </Grid>
      <Grid container spacing={2}>
        <Detail title="Antecedentes electorales">
          {a?.historical['2019'] || a?.historical['2023'] ? (
            <Stack spacing={1.5}>
              {['2019', '2023'].map(
                (year) =>
                  a.historical[year] && (
                    <Stack key={year} spacing={0.25}>
                      <Typography fontWeight={700}>{year}</Typography>
                      <Typography>
                        Participación: {formatPercentEsEc(a.historical[year].turnout_rate)}
                      </Typography>
                      <Typography>
                        Votantes: {formatIntegerEsEc(a.historical[year].ballots_cast)}
                      </Typography>
                    </Stack>
                  ),
              )}
            </Stack>
          ) : (
            <Typography color="text.secondary">
              No hay antecedentes electorales disponibles.
            </Typography>
          )}
        </Detail>
        <Detail title="Operación territorial">
          {o ? (
            <Stack spacing={0.5}>
              <Typography>Actividades: {formatIntegerEsEc(activitiesTotal)}</Typography>
              <Typography>Necesidades: {formatIntegerEsEc(needsTotal)}</Typography>
              <Typography>
                Parroquias con actividad: {formatIntegerEsEc(withActivities)} de{' '}
                {formatIntegerEsEc(totalParishes)}
              </Typography>
            </Stack>
          ) : (
            <Typography color="text.secondary">No hay información operativa disponible.</Typography>
          )}
        </Detail>
        <Detail title="Contexto demográfico">
          {population ? (
            <Stack spacing={0.5}>
              <Typography variant="h3">{formatIntegerEsEc(population)} habitantes</Typography>
              <Typography color="text.secondary" variant="body2">
                INEC · Censo {a?.demographics.year}
              </Typography>
            </Stack>
          ) : (
            <Typography color="text.secondary">
              No hay información demográfica disponible.
            </Typography>
          )}
          <Button component={RouterLink} to={`/app/campaigns/${campaignId}/demographics`}>
            VER DEMOGRAFÍA
          </Button>
        </Detail>
        <Detail title="Estudios y encuestas">
          {studies.data?.items.length ? (
            <Stack spacing={0.5}>
              <Typography fontWeight={700}>
                {studies.data.items.length} estudios publicados
              </Typography>
              <Typography color="text.secondary" variant="body2">
                Último estudio
              </Typography>
              <Typography>{studies.data.items[0].name.replace(/^\[DEMO\]\s*/, '')}</Typography>
              <Typography>
                Muestra: {formatIntegerEsEc(studies.data.items[0].sample_size_total)}
              </Typography>
              {(latestStudy.data?.results?.length ?? 0) > 0 && (
                <>
                  <Typography color="text.secondary" variant="body2" sx={{ mt: 1 }}>
                    Principales resultados
                  </Typography>
                  {latestStudy.data?.results?.slice(0, 3).map((result) => (
                    <Typography key={result.option_id}>
                      {result.option_label}: {formatPercentEsEc(result.percentage)}
                    </Typography>
                  ))}
                </>
              )}
              <Button
                component={RouterLink}
                to={`/app/campaigns/${campaignId}/survey-studies/${studies.data.items[0].id}`}
                sx={{ mt: 1 }}
              >
                VER ESTUDIO
              </Button>
            </Stack>
          ) : (
            <Typography color="text.secondary">No hay estudios publicados.</Typography>
          )}
        </Detail>
        <Detail title="Información pública">
          {publicCount > 0 ? (
            <Typography>
              {formatIntegerEsEc(publicCount)} publicaciones o documentos recientes disponibles como
              fuente complementaria.
            </Typography>
          ) : (
            <Typography color="text.secondary">Sin información reciente.</Typography>
          )}
        </Detail>
      </Grid>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>
        Los datos dependen de la disponibilidad, fecha de corte y procedencia de cada fuente. El
        escenario de participación se muestra tal como está persistido; no se recalcula. No se
        calculan probabilidades de ganador, apoyo político ni puntuaciones de persuasión.
      </Typography>
      {!isCoordinator && (
        <>
          <Typography variant="h2" sx={{ mt: 3, mb: 1 }}>
            Preguntas rápidas
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {panoramaQuestions.map((question) => (
              <Button
                key={question}
                component={RouterLink}
                to={aiPath(question)}
                variant="outlined"
              >
                {question}
              </Button>
            ))}
          </Stack>
        </>
      )}
    </>
  );
}
