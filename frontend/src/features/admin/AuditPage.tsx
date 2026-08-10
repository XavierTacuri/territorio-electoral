import { useState } from 'react';
import { MenuItem, Pagination, Stack, TextField } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { DataTable } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
type E = {
  id: string;
  event_type: string;
  outcome: string;
  event_date: string;
  user_id?: string;
  campaign_id?: string;
  resource_type?: string;
  description: string;
};
export default function AuditPage() {
  const [page, setPage] = useState(1);
  const [event, setEvent] = useState('');
  const [outcome, setOutcome] = useState('');
  const [date, setDate] = useState('');
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (event) params.set('event_type', event);
  if (outcome) params.set('outcome', outcome);
  if (date) params.set('event_date', date);
  const q = useQuery({
    queryKey: ['audit', page, event, outcome, date],
    queryFn: () =>
      apiRequest<{ items: E[]; total_pages: number }>(`/security/audit-events?${params}`),
  });
  return (
    <>
      <PageHeader
        title="Auditoría de seguridad"
        description="Eventos funcionales sin tokens, IP, User-Agent ni timestamps visibles."
      />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} mb={2}>
        <TextField label="Evento" value={event} onChange={(e) => setEvent(e.target.value)} />
        <TextField
          select
          label="Resultado"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {['SUCCESS', 'FAILURE', 'DENIED'].map((x) => (
            <MenuItem key={x} value={x}>
              {x}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          type="date"
          label="Fecha"
          InputLabelProps={{ shrink: true }}
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Stack>
      <DataTable
        label="eventos de auditoría"
        loading={q.isLoading}
        rows={q.data?.items || []}
        columns={[
          { key: 'date', label: 'Fecha', render: (x) => formatDateOnly(x.event_date) },
          { key: 'event', label: 'Evento', render: (x) => x.event_type },
          { key: 'outcome', label: 'Resultado', render: (x) => x.outcome },
          { key: 'resource', label: 'Recurso', render: (x) => x.resource_type || '—' },
          { key: 'description', label: 'Descripción', render: (x) => x.description },
        ]}
      />
      <Pagination
        page={page}
        count={q.data?.total_pages || 0}
        onChange={(_, v) => setPage(v)}
        sx={{ mt: 2 }}
      />
    </>
  );
}
