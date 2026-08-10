import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { todayDateOnly, formatDateOnly } from '../../lib/dates';
type Template = { code: string; name: string; allowed_formats: string[] };
type Run = {
  id: string;
  title: string;
  requested_format: string;
  status: string;
  report_date: string;
  artifact?: { is_available: boolean; original_download_name: string } | null;
};
export default function ReportsPage() {
  const { campaignId = '' } = useParams();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [template, setTemplate] = useState('');
  const [format, setFormat] = useState('PDF');
  const [title, setTitle] = useState('Informe territorial');
  const [error, setError] = useState('');
  const templates = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => apiRequest<Template[]>('/report-templates'),
  });
  const runs = useQuery({
    queryKey: ['reports', campaignId],
    queryFn: () =>
      apiRequest<{ items: Run[] }>(`/campaigns/${campaignId}/reports?page=1&page_size=50`),
    enabled: !!campaignId,
  });
  const generate = useMutation({
    mutationFn: () =>
      apiRequest<Run>(`/campaigns/${campaignId}/reports/generate`, {
        method: 'POST',
        body: JSON.stringify({
          template_code: template,
          format,
          title,
          report_date: todayDateOnly(),
          period: 'LAST_30_DAYS',
          survey_ids: [],
          electoral_process_ids: [],
          demographic_indicator_codes: [],
          include_comparisons: true,
        }),
      }),
    onSuccess: () => {
      setOpen(false);
      qc.invalidateQueries({ queryKey: ['reports', campaignId] });
    },
    onError: () => setError('No se pudo generar el informe.'),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/campaigns/${campaignId}/reports/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', campaignId] }),
  });
  const columns: Column<Run>[] = [
    { key: 'title', label: 'Título', render: (x) => x.title },
    { key: 'requested_format', label: 'Formato', render: (x) => x.requested_format },
    { key: 'status', label: 'Estado', render: (x) => x.status },
    { key: 'report_date', label: 'Fecha', render: (x) => formatDateOnly(x.report_date) },
    {
      key: 'id',
      label: 'Acciones',
      render: (x) => (
        <Stack direction="row" gap={1}>
          <Button
            size="small"
            disabled={!x.artifact?.is_available}
            onClick={() =>
              downloadReport(
                `/campaigns/${campaignId}/reports/${x.id}/download`,
                x.artifact?.original_download_name || `informe.${x.requested_format.toLowerCase()}`,
                false,
              )
            }
          >
            Descargar
          </Button>
          <Button size="small" color="error" onClick={() => remove.mutate(x.id)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        title="Informes"
        description="Generación y descarga privada de PDF y XLSX."
        action={
          <Button variant="contained" onClick={() => setOpen(true)}>
            Generar informe
          </Button>
        }
      />
      {error && <Alert severity="error">{error}</Alert>}
      <DataTable
        columns={columns}
        rows={runs.data?.items || []}
        loading={runs.isLoading}
        label="Informes generados"
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth>
        <DialogTitle>Generar informe</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              select
              label="Plantilla"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              {templates.data?.map((x) => (
                <MenuItem key={x.code} value={x.code}>
                  {x.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Formato"
              value={format}
              onChange={(e) => setFormat(e.target.value)}
            >
              {['PDF', 'XLSX'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Título" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!template || generate.isPending}
            onClick={() => generate.mutate()}
          >
            Generar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
