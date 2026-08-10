import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Pagination,
  Stack,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { formatDateRange } from '../../lib/dates';
import type { Survey, SurveyPage } from './types';
type Form = {
  title: string;
  slug: string;
  description: string;
  instructions: string;
  start_date: string;
  end_date: string;
  target_scope: string;
  allow_multiple_submissions: boolean;
  anonymous_only: true;
  show_progress: boolean;
  thank_you_message: string;
};
export default function SurveysPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'surveys', page, status],
    queryFn: () =>
      apiRequest<SurveyPage>(
        '/campaigns/' +
          campaignId +
          '/surveys?page=' +
          page +
          '&page_size=20' +
          (status ? '&status=' + status : ''),
      ),
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<Form>({
    defaultValues: {
      title: '',
      slug: '',
      description: '',
      instructions: '',
      start_date: '',
      end_date: '',
      target_scope: 'CANTON',
      allow_multiple_submissions: true,
      anonymous_only: true,
      show_progress: true,
      thank_you_message: 'Gracias por participar.',
    },
  });
  const create = useMutation({
    mutationFn: (v: Form) =>
      apiRequest<Survey>('/campaigns/' + campaignId + '/surveys', {
        method: 'POST',
        body: JSON.stringify({
          ...v,
          start_date: v.start_date || null,
          end_date: v.end_date || null,
          anonymous_only: true,
        }),
      }),
    onSuccess: (survey) => {
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'surveys'] });
      setOpen(false);
      navigate('/app/campaigns/' + campaignId + '/surveys/' + survey.id + '/build');
    },
  });
  return (
    <>
      <PageHeader
        title="Encuestas"
        description="Encuestas anónimas y resultados exclusivamente agregados."
        action={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => {
              reset();
              setOpen(true);
            }}
          >
            Crear encuesta
          </Button>
        }
      />
      <TextField
        select
        label="Estado"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        sx={{ mb: 2, minWidth: 190 }}
      >
        <MenuItem value="">Todos</MenuItem>
        {['DRAFT', 'PUBLISHED', 'CLOSED', 'ARCHIVED'].map((x) => (
          <MenuItem key={x} value={x}>
            {x}
          </MenuItem>
        ))}
      </TextField>
      {list.isError ? (
        <ErrorState retry={() => list.refetch()} />
      ) : (
        <DataTable
          label="encuestas"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Título', render: (x) => x.title },
            { key: 'status', label: 'Estado', render: (x) => <StatusBadge value={x.status} /> },
            {
              key: 'period',
              label: 'Período',
              render: (x) => formatDateRange(x.start_date, x.end_date),
            },
            { key: 'scope', label: 'Alcance', render: (x) => x.target_scope },
          ]}
          onView={(x) => navigate('/app/campaigns/' + campaignId + '/surveys/' + x.id)}
          onEdit={(x) => navigate('/app/campaigns/' + campaignId + '/surveys/' + x.id + '/build')}
        />
      )}
      <Pagination
        sx={{ mt: 2 }}
        page={page}
        count={list.data?.total_pages ?? 0}
        onChange={(_, v) => setPage(v)}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Crear encuesta</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" {...register('title', { required: true })} />
            <TextField
              label="Slug"
              helperText="Identificador sin información personal"
              {...register('slug', { required: true })}
            />
            <TextField label="Descripción" multiline {...register('description')} />
            <TextField label="Instrucciones" multiline {...register('instructions')} />
            <TextField
              type="date"
              label="Fecha inicial"
              InputLabelProps={{ shrink: true }}
              {...register('start_date')}
            />
            <TextField
              type="date"
              label="Fecha final"
              InputLabelProps={{ shrink: true }}
              {...register('end_date')}
            />
            <TextField select label="Alcance" defaultValue="CANTON" {...register('target_scope')}>
              {['CANTON', 'PARISH', 'COMMUNITY', 'SECTOR', 'ACTIVITY'].map((x) => (
                <MenuItem key={x} value={x}>
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Mensaje de agradecimiento" {...register('thank_you_message')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={isSubmitting}
            onClick={handleSubmit(async (v) => {
              try {
                await create.mutateAsync(v);
              } catch {
                setError('No se pudo crear la encuesta.');
              }
            })}
          >
            Crear y diseñar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
