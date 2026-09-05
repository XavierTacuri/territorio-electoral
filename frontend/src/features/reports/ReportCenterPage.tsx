import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { useCampaign } from '../../app/CampaignProvider';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, todayDateOnly } from '../../lib/dates';
import { ReportPreviewView } from './ReportPreviewView';
import {
  RUN_STATUS_LABELS,
  THEME_OPTIONS,
  type ReportPreview,
  type ReportRun,
  type ReportTypeInfo,
} from './types';

type Parish = { id: number; name: string; dpa_code?: string };

export default function ReportCenterPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const boolParam = (name: string, fallback: boolean) => {
    const value = searchParams.get(name);
    return value === null ? fallback : value !== 'false' && value !== '0';
  };

  const [templateCode, setTemplateCode] = useState(
    searchParams.get('type') || 'CAMPAIGN_EXECUTIVE_REPORT',
  );
  const [parishId, setParishId] = useState<string>(searchParams.get('parish_id') || '');
  const [theme, setTheme] = useState<string>(searchParams.get('theme') || '');
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') || '');
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || '');
  const [format, setFormat] = useState<'PDF' | 'XLSX'>('PDF');
  const [title, setTitle] = useState('');
  const [includeSurveys, setIncludeSurveys] = useState(boolParam('include_surveys', true));
  const [includePublicIntelligence, setIncludePublicIntelligence] = useState(
    boolParam('include_public_intelligence', true),
  );
  const [includeEvidence, setIncludeEvidence] = useState(boolParam('include_evidence', true));
  const [includeDemo, setIncludeDemo] = useState(boolParam('include_demo', true));
  const [includeCitations, setIncludeCitations] = useState(true);
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [copyMessage, setCopyMessage] = useState('');

  const types = useQuery({
    queryKey: ['report-types'],
    queryFn: () => apiRequest<ReportTypeInfo[]>('/report-types'),
    staleTime: Infinity,
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>(`/parishes?canton_id=${active!.canton_id}`),
    enabled: Boolean(active?.canton_id),
  });
  const runs = useQuery({
    queryKey: ['report-runs', campaignId],
    queryFn: () =>
      apiRequest<{ items: ReportRun[]; total: number }>(
        `/campaigns/${campaignId}/reports?page=1&page_size=20`,
      ),
    enabled: Boolean(campaignId),
  });

  const selectedType = types.data?.find((t) => t.code === templateCode);
  const effectiveTitle = title.trim() || selectedType?.name || 'Informe';

  const payload = useMemo(
    () => ({
      template_code: templateCode,
      format,
      title: effectiveTitle,
      report_date: todayDateOnly(),
      date_from: dateFrom || null,
      date_to: dateTo || null,
      parish_id: parishId ? Number(parishId) : null,
      theme: theme || null,
      include_surveys: includeSurveys,
      include_public_intelligence: includePublicIntelligence,
      include_evidence: includeEvidence,
      include_demo: includeDemo,
      include_citations: includeCitations,
    }),
    [
      templateCode,
      format,
      effectiveTitle,
      dateFrom,
      dateTo,
      parishId,
      theme,
      includeSurveys,
      includePublicIntelligence,
      includeEvidence,
      includeDemo,
      includeCitations,
    ],
  );

  const previewMutation = useMutation({
    mutationFn: () =>
      apiRequest<ReportPreview>(`/campaigns/${campaignId}/reports/preview`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => setPreview(data),
  });
  const generateMutation = useMutation({
    mutationFn: () =>
      apiRequest<ReportRun>(`/campaigns/${campaignId}/reports/generate`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: async (run) => {
      await qc.invalidateQueries({ queryKey: ['report-runs', campaignId] });
      if (run.artifact) {
        await downloadReport(
          `/campaigns/${campaignId}/reports/${run.id}/download`,
          run.artifact.original_download_name,
          format === 'PDF',
        );
      }
    },
  });

  const missingParish = selectedType?.requires_parish && !parishId;
  const missingTheme = selectedType?.requires_theme && !theme;
  const canSubmit = !missingParish && !missingTheme;

  const copyResumen = async () => {
    if (!preview) return;
    try {
      await navigator.clipboard.writeText(preview.narrative.resumen_ejecutivo);
      setCopyMessage('Resumen copiado al portapapeles.');
    } catch {
      setCopyMessage('No se pudo copiar el resumen.');
    }
  };

  const aiPath = (question: string) =>
    `/app/campaigns/${campaignId}/territory-ai?question=${encodeURIComponent(question)}`;
  const suggestedQuestion = theme
    ? `Resume la evidencia disponible sobre ${THEME_OPTIONS.find((t) => t.code === theme)?.label.toLowerCase() ?? theme}.`
    : `¿Qué explica los hallazgos del ${selectedType?.name ?? 'informe'}?`;
  const scrollToCitations = () =>
    document
      .getElementById('report-citations')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const columns: Column<ReportRun>[] = [
    { key: 'title', label: 'Informe', render: (x) => x.title },
    { key: 'template_code', label: 'Tipo', render: (x) => x.template_code.replaceAll('_', ' ') },
    { key: 'report_date', label: 'Fecha', render: (x) => formatDateOnly(x.report_date) },
    { key: 'status', label: 'Estado', render: (x) => RUN_STATUS_LABELS[x.status] ?? x.status },
    {
      key: 'id',
      label: 'Acciones',
      render: (x) => (
        <Stack direction="row" gap={1}>
          <Button
            size="small"
            component={RouterLink}
            to={`/app/campaigns/${campaignId}/reports/${x.id}`}
          >
            Ver
          </Button>
          <Button
            size="small"
            disabled={!x.artifact?.is_available}
            onClick={() =>
              downloadReport(
                `/campaigns/${campaignId}/reports/${x.id}/download`,
                x.artifact?.original_download_name || `informe.${x.requested_format.toLowerCase()}`,
              )
            }
          >
            Descargar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Centro de Informes"
        description="Informes ejecutivos y territoriales de campaña, redactados con evidencia real y sin predicción electoral."
      />
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 2 }}>
                Configurar informe
              </Typography>
              <Stack spacing={2}>
                <TextField
                  select
                  label="Tipo de informe"
                  value={templateCode}
                  onChange={(e) => setTemplateCode(e.target.value)}
                >
                  {(types.data ?? []).map((t) => (
                    <MenuItem key={t.code} value={t.code}>
                      {t.name}
                    </MenuItem>
                  ))}
                </TextField>
                {selectedType && (
                  <Typography variant="body2" color="text.secondary">
                    {selectedType.description}
                  </Typography>
                )}
                <TextField
                  label="Título del informe"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={selectedType?.name}
                />
                {(selectedType?.requires_parish ||
                  templateCode === 'OPERATION_TERRITORIAL_REPORT' ||
                  templateCode === 'THEMATIC_REPORT') && (
                  <TextField
                    select
                    label={selectedType?.requires_parish ? 'Parroquia' : 'Parroquia (opcional)'}
                    value={parishId}
                    onChange={(e) => setParishId(e.target.value)}
                    error={Boolean(missingParish)}
                    helperText={missingParish ? 'Este informe requiere una parroquia.' : ' '}
                  >
                    {!selectedType?.requires_parish && (
                      <MenuItem value="">Toda la campaña</MenuItem>
                    )}
                    {(parishes.data ?? []).map((p) => (
                      <MenuItem key={p.id} value={String(p.id)}>
                        {p.name}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
                {selectedType?.requires_theme && (
                  <TextField
                    select
                    label="Tema"
                    value={theme}
                    onChange={(e) => setTheme(e.target.value)}
                    error={Boolean(missingTheme)}
                    helperText={missingTheme ? 'Elige un tema.' : ' '}
                  >
                    {THEME_OPTIONS.map((t) => (
                      <MenuItem key={t.code} value={t.code}>
                        {t.label}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
                <Stack direction="row" spacing={2}>
                  <TextField
                    type="date"
                    label="Desde (opcional)"
                    InputLabelProps={{ shrink: true }}
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    type="date"
                    label="Hasta (opcional)"
                    InputLabelProps={{ shrink: true }}
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    fullWidth
                  />
                </Stack>
                <TextField
                  select
                  label="Formato de exportación"
                  value={format}
                  onChange={(e) => setFormat(e.target.value as 'PDF' | 'XLSX')}
                >
                  <MenuItem value="PDF">PDF</MenuItem>
                  <MenuItem value="XLSX">Excel (XLSX)</MenuItem>
                </TextField>
                <Box>
                  <Typography variant="overline" color="text.secondary">
                    Incluir en el informe
                  </Typography>
                  <Stack>
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includeSurveys}
                          onChange={(e) => setIncludeSurveys(e.target.checked)}
                        />
                      }
                      label="Encuestas publicadas"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includePublicIntelligence}
                          onChange={(e) => setIncludePublicIntelligence(e.target.checked)}
                        />
                      }
                      label="Información pública"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includeEvidence}
                          onChange={(e) => setIncludeEvidence(e.target.checked)}
                        />
                      }
                      label="Evidencias"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includeDemo}
                          onChange={(e) => setIncludeDemo(e.target.checked)}
                        />
                      }
                      label="Datos DEMO"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={includeCitations}
                          onChange={(e) => setIncludeCitations(e.target.checked)}
                        />
                      }
                      label="Citas y fuentes"
                    />
                  </Stack>
                </Box>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    disabled={!canSubmit || previewMutation.isPending}
                    onClick={() => previewMutation.mutate()}
                  >
                    {preview ? 'Regenerar' : 'Generar'}
                  </Button>
                  <Button
                    disabled={!canSubmit || generateMutation.isPending}
                    onClick={() => generateMutation.mutate()}
                  >
                    Exportar {format}
                  </Button>
                  <Button disabled={!preview} onClick={copyResumen}>
                    Copiar resumen
                  </Button>
                  <Button
                    disabled={!preview || !preview.citations.length}
                    onClick={scrollToCitations}
                  >
                    Ver fuentes
                  </Button>
                </Stack>
                {copyMessage && (
                  <Alert severity="info" onClose={() => setCopyMessage('')}>
                    {copyMessage}
                  </Alert>
                )}
                {previewMutation.isError && (
                  <Alert severity="error">No se pudo generar la previsualización.</Alert>
                )}
                {generateMutation.isError && (
                  <Alert severity="error">No se pudo exportar el informe.</Alert>
                )}
                {generateMutation.isSuccess && (
                  <Alert severity="success">Informe exportado y agregado al historial.</Alert>
                )}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    component={RouterLink}
                    to={aiPath(suggestedQuestion)}
                    startIcon={<AutoAwesomeOutlinedIcon />}
                  >
                    Abrir en Territorio IA
                  </Button>
                  {preview ? (
                    <Button
                      component={RouterLink}
                      to={aiPath(`Amplía este resumen: ${preview.narrative.resumen_ejecutivo}`)}
                    >
                      Usar resumen IA
                    </Button>
                  ) : (
                    <Button disabled>Usar resumen IA</Button>
                  )}
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          {previewMutation.isPending ? (
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary">Generando previsualización…</Typography>
              </CardContent>
            </Card>
          ) : preview ? (
            <ReportPreviewView preview={preview} />
          ) : (
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary">
                  Configura el informe y presiona <strong>Generar</strong> para ver la
                  previsualización antes de exportar.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>

      <Typography component="h2" variant="h2" sx={{ mt: 4, mb: 2 }}>
        Informes generados
      </Typography>
      {runs.isError ? (
        <ErrorState retry={() => runs.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={runs.data?.items ?? []}
          loading={runs.isLoading}
          label="Historial de informes"
        />
      )}
      {!runs.isLoading && !runs.data?.items.length && (
        <Chip
          label="Aún no has generado informes en esta campaña."
          variant="outlined"
          sx={{ mt: 1 }}
        />
      )}
    </>
  );
}
