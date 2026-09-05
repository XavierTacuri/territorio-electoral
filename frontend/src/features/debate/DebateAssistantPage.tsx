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
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { useCampaign } from '../../app/CampaignProvider';
import { PageHeader } from '../../components/layout/PageHeader';
import { todayDateOnly } from '../../lib/dates';
import { ReportPreviewView } from '../reports/ReportPreviewView';
import { THEME_OPTIONS, type ReportPreview, type ReportRun } from '../reports/types';
import type { ClaimCheckResponse } from './types';

type Parish = { id: number; name: string; dpa_code?: string };

const VERDICT_COLOR: Record<ClaimCheckResponse['verdict'], 'success' | 'warning' | 'error'> = {
  SUPPORTED: 'success',
  PARTIALLY_SUPPORTED: 'warning',
  UNSUPPORTED: 'error',
};

export default function DebateAssistantPage() {
  const { campaignId = '' } = useParams();
  const { active } = useCampaign();
  const [searchParams] = useSearchParams();
  const boolParam = (name: string, fallback: boolean) => {
    const value = searchParams.get(name);
    return value === null ? fallback : value !== 'false' && value !== '0';
  };

  const [theme, setTheme] = useState(searchParams.get('theme') || 'VIALIDAD');
  const [parishId, setParishId] = useState(searchParams.get('parish_id') || '');
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') || '');
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || '');
  const [includeSurveys, setIncludeSurveys] = useState(boolParam('include_surveys', true));
  const [includePublicIntelligence, setIncludePublicIntelligence] = useState(
    boolParam('include_public_intelligence', true),
  );
  const [includeEvidence, setIncludeEvidence] = useState(boolParam('include_evidence', true));
  const [includeDemo, setIncludeDemo] = useState(boolParam('include_demo', true));
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [claimText, setClaimText] = useState('');
  const [claimParishId, setClaimParishId] = useState('');
  const [claimResult, setClaimResult] = useState<ClaimCheckResponse | null>(null);

  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () => apiRequest<Parish[]>(`/parishes?canton_id=${active!.canton_id}`),
    enabled: Boolean(active?.canton_id),
  });

  const themeLabel = THEME_OPTIONS.find((t) => t.code === theme)?.label ?? theme;

  const payload = useMemo(
    () => ({
      template_code: 'DEBATE_BRIEF_REPORT',
      format: 'PDF' as const,
      title: `Preparación para debate · ${themeLabel}`,
      report_date: todayDateOnly(),
      date_from: dateFrom || null,
      date_to: dateTo || null,
      parish_id: parishId ? Number(parishId) : null,
      theme,
      include_surveys: includeSurveys,
      include_public_intelligence: includePublicIntelligence,
      include_evidence: includeEvidence,
      include_demo: includeDemo,
      include_citations: true,
    }),
    [
      theme,
      themeLabel,
      dateFrom,
      dateTo,
      parishId,
      includeSurveys,
      includePublicIntelligence,
      includeEvidence,
      includeDemo,
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
      if (run.artifact) {
        await downloadReport(
          `/campaigns/${campaignId}/reports/${run.id}/download`,
          run.artifact.original_download_name,
          true,
        );
      }
    },
  });
  const claimMutation = useMutation({
    mutationFn: () =>
      apiRequest<ClaimCheckResponse>(`/campaigns/${campaignId}/debate/claim-check`, {
        method: 'POST',
        body: JSON.stringify({
          claim_text: claimText,
          parish_id: claimParishId ? Number(claimParishId) : null,
        }),
      }),
    onSuccess: (data) => setClaimResult(data),
  });

  const aiPath = `/app/campaigns/${campaignId}/territory-ai?question=${encodeURIComponent(`Resumen de debate sobre ${themeLabel.toLowerCase()}.`)}`;

  return (
    <>
      <PageHeader
        title="Preparación para debate"
        description="Genera un briefing factual respaldado por evidencia y verifica afirmaciones antes de un debate o reunión. No genera ataques, persuasión ni predicciones."
      />
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography component="h2" variant="h2" sx={{ mb: 2 }}>
                Preparar debate
              </Typography>
              <Stack spacing={2}>
                <TextField
                  select
                  label="Tema"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                >
                  {THEME_OPTIONS.map((t) => (
                    <MenuItem key={t.code} value={t.code}>
                      {t.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  label="Territorio (opcional)"
                  value={parishId}
                  onChange={(e) => setParishId(e.target.value)}
                >
                  <MenuItem value="">Toda la campaña</MenuItem>
                  {(parishes.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </MenuItem>
                  ))}
                </TextField>
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
                <Box>
                  <Typography variant="overline" color="text.secondary">
                    Fuentes a incluir
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
                  </Stack>
                </Box>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    disabled={previewMutation.isPending}
                    onClick={() => previewMutation.mutate()}
                  >
                    Generar briefing
                  </Button>
                  <Button
                    disabled={generateMutation.isPending}
                    onClick={() => generateMutation.mutate()}
                  >
                    Exportar briefing PDF
                  </Button>
                  <Button
                    component={RouterLink}
                    to={aiPath}
                    startIcon={<AutoAwesomeOutlinedIcon />}
                  >
                    Abrir en Territorio IA
                  </Button>
                </Stack>
                {previewMutation.isError && (
                  <Alert severity="error">No se pudo generar el briefing.</Alert>
                )}
                {generateMutation.isError && (
                  <Alert severity="error">No se pudo exportar el briefing.</Alert>
                )}
                {generateMutation.isSuccess && (
                  <Alert severity="success">Briefing exportado y agregado a Mis Informes.</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          {previewMutation.isPending ? (
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary">Generando briefing…</Typography>
              </CardContent>
            </Card>
          ) : preview ? (
            <ReportPreviewView preview={preview} />
          ) : (
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary">
                  Elige un tema y presiona <strong>Generar briefing</strong> para ver el resumen
                  factual antes de exportarlo.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>

      <Typography component="h2" variant="h2" sx={{ mt: 4, mb: 2 }}>
        Verificar afirmación
      </Typography>
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={2}>
                <TextField
                  label="Afirmación a verificar"
                  placeholder="Ej: En Gualaceo hay 43.188 habitantes."
                  multiline
                  minRows={3}
                  value={claimText}
                  onChange={(e) => setClaimText(e.target.value)}
                />
                <TextField
                  select
                  label="Territorio (opcional)"
                  value={claimParishId}
                  onChange={(e) => setClaimParishId(e.target.value)}
                >
                  <MenuItem value="">Toda la campaña</MenuItem>
                  {(parishes.data ?? []).map((p) => (
                    <MenuItem key={p.id} value={String(p.id)}>
                      {p.name}
                    </MenuItem>
                  ))}
                </TextField>
                <Button
                  variant="contained"
                  startIcon={<FactCheckOutlinedIcon />}
                  disabled={claimText.trim().length < 3 || claimMutation.isPending}
                  onClick={() => claimMutation.mutate()}
                >
                  Verificar afirmación
                </Button>
                {claimMutation.isError && (
                  <Alert severity="error">No se pudo verificar la afirmación.</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {claimResult ? (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="overline" color="text.secondary">
                  Afirmación
                </Typography>
                <Typography sx={{ mb: 1 }}>{claimResult.claim_text}</Typography>
                <Chip
                  color={VERDICT_COLOR[claimResult.verdict]}
                  label={claimResult.verdict_label}
                  sx={{ mb: 2 }}
                />
                {claimResult.evidence.length > 0 ? (
                  <Stack spacing={1}>
                    {claimResult.evidence.map((item) => (
                      <Box key={item.id} sx={{ py: 1, borderBottom: 1, borderColor: 'divider' }}>
                        <Typography fontWeight={700}>{item.title}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {item.source_label} · {item.source_name}
                          {item.record_date ? ` · ${item.record_date}` : ''}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                ) : (
                  <Typography color="text.secondary">
                    No se encontró evidencia relacionada.
                  </Typography>
                )}
                {claimResult.warnings.length > 0 && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    {claimResult.warnings.join(' ')}
                  </Typography>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary">
                  El resultado indica si la afirmación está respaldada, parcialmente respaldada o no
                  respaldada por la evidencia disponible — nunca verdadero/falso.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
    </>
  );
}
