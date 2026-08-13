import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { PageHeader } from '../../components/layout/PageHeader';
import { DataTable } from '../../components/tables/DataTable';
import { ErrorState } from '../../components/feedback/States';
import { StatusBadge } from '../../components/data-display/Common';
import type { Survey, SurveyPage } from './types';

export default function QuestionnairesPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [slug, setSlug] = useState('');
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['campaign', campaignId, 'questionnaires'],
    queryFn: () => apiRequest<SurveyPage>(`/campaigns/${campaignId}/surveys?page=1&page_size=100`),
  });
  const create = useMutation({
    mutationFn: () =>
      apiRequest<Survey>(`/campaigns/${campaignId}/surveys`, {
        method: 'POST',
        body: JSON.stringify({
          title,
          slug,
          description: '',
          instructions: '',
          start_date: null,
          end_date: null,
          target_scope: 'CANTON',
          allow_multiple_submissions: true,
          anonymous_only: true,
          show_progress: true,
          thank_you_message: 'Gracias por participar.',
        }),
      }),
    onSuccess: (survey) => navigate(`/app/campaigns/${campaignId}/surveys/${survey.id}/build`),
  });
  return (
    <>
      <PageHeader
        title="CUESTIONARIOS"
        description="Constructor histórico de cuestionarios anónimos, separado de los estudios agregados."
        action={
          <Stack direction="row" spacing={1}>
            <Button onClick={() => navigate(`/app/campaigns/${campaignId}/surveys`)}>
              Encuestas y estudios
            </Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
              Crear cuestionario
            </Button>
          </Stack>
        }
      />
      {list.isError ? (
        <ErrorState retry={() => void list.refetch()} />
      ) : list.data?.items.length === 0 ? (
        <Alert severity="info">No hay cuestionarios registrados.</Alert>
      ) : (
        <DataTable
          label="cuestionarios"
          loading={list.isLoading}
          rows={list.data?.items ?? []}
          columns={[
            { key: 'title', label: 'Título', render: (x) => x.title },
            { key: 'status', label: 'Estado', render: (x) => <StatusBadge value={x.status} /> },
            { key: 'scope', label: 'Alcance', render: (x) => x.target_scope },
          ]}
          onView={(x) => navigate(`/app/campaigns/${campaignId}/surveys/${x.id}`)}
          onEdit={(x) => navigate(`/app/campaigns/${campaignId}/surveys/${x.id}/build`)}
        />
      )}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Crear cuestionario</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error">{error}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" value={title} onChange={(e) => setTitle(e.target.value)} />
            <TextField label="Slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!title || !slug || create.isPending}
            onClick={async () => {
              try {
                setError('');
                await create.mutateAsync();
              } catch {
                setError('No se pudo crear el cuestionario.');
              }
            }}
          >
            Crear y diseñar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
