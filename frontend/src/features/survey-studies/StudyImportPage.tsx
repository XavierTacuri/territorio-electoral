import { useState } from 'react';
import { Alert, Button, Grid, Paper, Stack, Typography } from '@mui/material';
import { useParams } from 'react-router-dom';
import { BASE_URL, tokenStore } from '../../api/client';
import { PageHeader } from '../../components/layout/PageHeader';
type Summary = {
  status: string;
  rows_read: number;
  rows_valid: number;
  rows_rejected: number;
  studies: string[];
  territories: number;
  options: number;
  errors: { row_number?: number; code: string; message: string }[];
};
export default function StudyImportPage() {
  const { campaignId = '' } = useParams();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Summary | null>(null);
  const [validated, setValidated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (execute: boolean) => {
    if (!file) {
      setError('Seleccione un CSV.');
      return;
    }
    setBusy(true);
    setError('');
    const body = new FormData();
    body.set('file', file);
    try {
      const response = await fetch(
        `${BASE_URL}/campaigns/${campaignId}/survey-imports/${execute ? 'execute' : 'validate'}`,
        {
          method: 'POST',
          body,
          credentials: 'include',
          headers: tokenStore.get() ? { Authorization: `Bearer ${tokenStore.get()}` } : {},
        },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'No se pudo procesar el CSV.');
      setResult(payload);
      setValidated(!execute && payload.status === 'VALIDATED');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No se pudo procesar el CSV.');
      setValidated(false);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader
        title="IMPORTAR RESULTADOS AGREGADOS"
        description="SURVEY_AGGREGATE_RESULTS · Validar no escribe resultados en la base."
      />
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Alert severity="info" sx={{ mb: 2 }}>
          Headers: study_code, territory_level, parish_dpa, option_code, option_label, option_type,
          response_count, percentage
        </Alert>
        <Button component="label" variant="outlined">
          Seleccionar CSV
          <input
            hidden
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
              setValidated(false);
            }}
          />
        </Button>
        <Typography component="span" sx={{ ml: 2, overflowWrap: 'anywhere' }}>
          {file?.name || 'Ningún archivo seleccionado'}
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mt: 2 }}>
          <Button variant="contained" disabled={busy || !file} onClick={() => run(false)}>
            1. Validar
          </Button>
          <Button
            variant="contained"
            color="secondary"
            disabled={busy || !validated}
            onClick={() => run(true)}
          >
            2. Ejecutar
          </Button>
        </Stack>
      </Paper>
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
      {result && (
        <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
          <Typography variant="h2">Resultado: {result.status}</Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {[
              ['Filas leídas', result.rows_read],
              ['Válidas', result.rows_valid],
              ['Rechazadas', result.rows_rejected],
              ['Territorios', result.territories],
              ['Opciones', result.options],
            ].map(([label, value]) => (
              <Grid key={label} size={{ xs: 6, md: 2 }}>
                <Typography variant="caption">{label}</Typography>
                <Typography variant="h3">{value}</Typography>
              </Grid>
            ))}
          </Grid>
          <Typography sx={{ mt: 2 }}>
            <b>Estudio detectado:</b> {result.studies.join(', ') || 'Ninguno'}
          </Typography>
          {result.errors.map((item, index) => (
            <Alert severity="warning" key={index}>
              {item.row_number ? `Fila ${item.row_number}: ` : ''}
              {item.message}
            </Alert>
          ))}
        </Paper>
      )}
    </>
  );
}
