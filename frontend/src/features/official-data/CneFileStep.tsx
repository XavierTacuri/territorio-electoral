import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  FormControlLabel,
  Checkbox,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { ConfirmDialog } from '../../components/forms/ConfirmDialog';
import { inspectCsvText, wizardConsistencyErrors } from './csv';
import { runOfficialImport } from './importApi';
import type { CneDataset, CsvInspection, ImportResult } from './types';

const datasetLabels: Record<CneDataset, string> = {
  CNE_POLITICAL_ORGANIZATIONS: 'Organizaciones políticas',
  CNE_TURNOUT: 'Participación electoral',
  CNE_CANDIDATES: 'Candidaturas',
  CNE_ELECTORAL_RESULTS: 'Resultados electorales',
};

function localErrors(dataset: CneDataset, inspection: CsvInspection | null) {
  if (!inspection) return [];
  const errors: string[] = [];
  if (dataset === 'CNE_TURNOUT' && inspection.rows.some((row) => row.registered_voters === ''))
    errors.push(
      'El archivo no contiene electores registrados. Complete el archivo oficial de registro electoral antes de importar participación.',
    );
  if (dataset === 'CNE_CANDIDATES') {
    const codes = inspection.rows.map((row) => row.candidate_code).filter(Boolean);
    if (new Set(codes).size !== codes.length)
      errors.push('El archivo contiene candidate_code duplicados.');
  }
  return errors;
}

export function CneFileStep({
  step,
  dataset,
  sourceId,
  processCode,
  contestCode,
  locked,
  complete,
  additionalErrors = [],
  onInspection,
  onExecuted,
}: {
  step: number;
  dataset: CneDataset;
  sourceId: string;
  processCode: string;
  contestCode: string;
  locked: boolean;
  complete: boolean;
  additionalErrors?: string[];
  onInspection: (inspection: CsvInspection | null) => void;
  onExecuted: () => Promise<void> | void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<CsvInspection | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [confirmForce, setConfirmForce] = useState(false);
  const contextErrors =
    dataset === 'CNE_POLITICAL_ORGANIZATIONS' || !inspection
      ? []
      : wizardConsistencyErrors(inspection, processCode, contestCode);
  const errors = [
    ...(inspection?.missingHeaders.map((header) => `Cabecera faltante: ${header}`) ?? []),
    ...localErrors(dataset, inspection),
    ...contextErrors,
    ...additionalErrors,
  ];

  const select = async (selected: File | null) => {
    setFile(selected);
    setResult(null);
    setError('');
    if (!selected) {
      setInspection(null);
      onInspection(null);
      return;
    }
    try {
      const inspected = inspectCsvText(await selected.text(), dataset);
      setInspection(inspected);
      onInspection(inspected);
    } catch {
      setInspection(null);
      onInspection(null);
      setError('No se pudo leer el archivo CSV en el navegador.');
    }
  };

  const run = async (action: 'validate' | 'execute', forced = false) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const response = await runOfficialImport(action, sourceId, dataset, file, forced);
      setResult(response);
      if (action === 'execute' && response.status === 'COMPLETED') await onExecuted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No se pudo procesar el archivo.');
    } finally {
      setBusy(false);
      setConfirmForce(false);
    }
  };

  const validated = result?.status === 'VALIDATED' && result.rows_failed === 0;
  return (
    <Paper variant="outlined" sx={{ p: 2, opacity: locked ? 0.72 : 1 }}>
      <Stack spacing={2}>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
          <div>
            <Typography variant="h2">
              Paso {step} — {datasetLabels[dataset]}
            </Typography>
            <Typography color="text.secondary">{dataset} · Perfil automático</Typography>
          </div>
          <Chip
            color={complete ? 'success' : locked ? 'default' : 'warning'}
            label={complete ? 'Completado' : locked ? 'Bloqueado' : 'Pendiente'}
          />
        </Stack>
        {locked && (
          <Alert severity="info">
            Complete primero las dependencias indicadas por el asistente.
          </Alert>
        )}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          <Button component="label" variant="outlined">
            Seleccionar
            <input
              hidden
              type="file"
              accept="text/csv,.csv"
              onChange={(event) => void select(event.target.files?.[0] ?? null)}
            />
          </Button>
          <Typography>{file?.name ?? 'Ningún archivo seleccionado'}</Typography>
          {inspection && <Typography>{inspection.rows.length} filas detectadas</Typography>}
        </Stack>
        {errors.map((message) => (
          <Alert key={message} severity="error">
            {message}
          </Alert>
        ))}
        {error && <Alert severity="error">{error}</Alert>}
        {result && (
          <Alert severity={result.status === 'REJECTED' ? 'warning' : 'success'}>
            Estado: {result.status}. Leídas: {result.rows_read}. Válidas: {result.rows_valid}.
            Rechazadas: {result.rows_failed}.
          </Alert>
        )}
        {result?.errors.map((item, index) => (
          <Alert key={`${item.row_number ?? index}-${item.message}`} severity="warning">
            {item.row_number ? `Fila ${item.row_number}: ` : ''}
            {item.message}
          </Alert>
        ))}
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <Button
            variant="contained"
            disabled={locked || busy || !file || errors.length > 0}
            onClick={() => void run('validate')}
          >
            Validar
          </Button>
          <Button
            variant="contained"
            color="secondary"
            disabled={locked || busy || !validated || errors.length > 0}
            onClick={() => (force ? setConfirmForce(true) : void run('execute'))}
          >
            Ejecutar
          </Button>
          <FormControlLabel
            control={
              <Checkbox checked={force} onChange={(event) => setForce(event.target.checked)} />
            }
            label="Forzar actualización"
          />
        </Stack>
      </Stack>
      <ConfirmDialog
        open={confirmForce}
        title="Forzar actualización"
        busy={busy}
        onCancel={() => setConfirmForce(false)}
        onConfirm={() => void run('execute', true)}
      >
        Se volverán a procesar las filas del archivo ya identificado. No se crearán duplicados fuera
        de las reglas existentes.
      </ConfirmDialog>
    </Paper>
  );
}
