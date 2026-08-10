import { Alert, Button, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { canAdministerCampaigns } from '../../auth/permissions';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, formatDateRange } from '../../lib/dates';
import { CampaignRead, Canton, officeLabels, Province, statusLabels } from './types';

type CampaignUser = { id: string; user_id: string; is_active: boolean };
type Parish = { id: number; name: string; is_active: boolean };

export default function CampaignDetailPage() {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const admin = canAdministerCampaigns(user);
  const campaign = useQuery({
    queryKey: ['campaign-detail', campaignId],
    queryFn: () => apiRequest<CampaignRead>(`/campaigns/${campaignId}`),
  });
  const canton = useQuery({
    queryKey: ['canton', campaign.data?.canton_id],
    queryFn: () => apiRequest<Canton>(`/cantons/${campaign.data!.canton_id}`),
    enabled: !!campaign.data,
  });
  const province = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<Province[]>('/provinces'),
  });
  const users = useQuery({
    queryKey: ['campaign-users', campaignId],
    queryFn: () => apiRequest<CampaignUser[]>(`/campaigns/${campaignId}/users`),
  });
  const parishes = useQuery({
    queryKey: ['parishes', campaign.data?.canton_id],
    queryFn: () => apiRequest<Parish[]>(`/parishes?canton_id=${campaign.data!.canton_id}`),
    enabled: !!campaign.data,
  });
  if (campaign.isLoading) return <LoadingSkeleton />;
  if (campaign.isError || !campaign.data)
    return (
      <ErrorState message="No fue posible cargar la campaña." retry={() => campaign.refetch()} />
    );
  const provinceName =
    province.data?.find((item) => item.id === canton.data?.province_id)?.name ?? '—';
  return (
    <>
      <PageHeader
        title={campaign.data.name}
        description="Detalle general y accesos relacionados con la campaña."
        action={
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {admin && (
              <Button
                component={RouterLink}
                to={`/app/campaigns/${campaignId}/edit`}
                variant="outlined"
              >
                Editar campaña
              </Button>
            )}{' '}
            {admin && (
              <Button
                component={RouterLink}
                to={`/app/admin/assignments?campaignId=${campaignId}`}
                variant="outlined"
              >
                Gestionar usuarios/asignaciones
              </Button>
            )}{' '}
            <Button
              component={RouterLink}
              to={`/app/campaigns/${campaignId}/dashboard`}
              variant="contained"
            >
              Ir al Dashboard
            </Button>
          </Stack>
        }
      />
      {!campaign.data.is_active && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Esta campaña está inactiva.
        </Alert>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1}>
                <Typography>
                  <strong>Nombre:</strong> {campaign.data.name}
                </Typography>
                <Typography>
                  <strong>Provincia:</strong> {provinceName}
                </Typography>
                <Typography>
                  <strong>Cantón:</strong> {canton.data?.name ?? '—'}
                </Typography>
                <Typography>
                  <strong>Cargo o dignidad:</strong> {officeLabels[campaign.data.office_type]}
                </Typography>
                <Typography>
                  <strong>Elección:</strong> {campaign.data.election_name}
                </Typography>
                <Typography>
                  <strong>Fecha electoral:</strong> {formatDateOnly(campaign.data.election_date)}
                </Typography>
                <Typography>
                  <strong>Período:</strong>{' '}
                  {formatDateRange(campaign.data.start_date, campaign.data.end_date)}
                </Typography>
                <Typography>
                  <strong>Estado:</strong> {statusLabels[campaign.data.status]} /{' '}
                  {campaign.data.is_active ? 'Activa' : 'Inactiva'}
                </Typography>
                <Typography>
                  <strong>Candidato:</strong>{' '}
                  {campaign.data.candidate?.display_name ?? 'Sin candidato principal'}
                </Typography>
                <Typography>
                  <strong>Descripción:</strong> {campaign.data.description || 'Sin descripción'}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Stack spacing={2}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h2">Usuarios asignados</Typography>
                <Typography>{users.data?.filter((item) => item.is_active).length ?? 0}</Typography>
              </CardContent>
            </Card>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h2">Territorios disponibles</Typography>
                <Typography>
                  {parishes.data?.filter((item) => item.is_active).length ?? 0} parroquias
                </Typography>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </>
  );
}
