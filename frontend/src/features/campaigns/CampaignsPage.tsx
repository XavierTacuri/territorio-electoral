import AddIcon from '@mui/icons-material/Add';
import { useEffect } from 'react';
import {
  Alert,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canAdministerCampaigns } from '../../auth/permissions';
import { canSeeCampaignAdministration } from '../../layouts/navigation';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly, formatDateRange } from '../../lib/dates';
import {
  CampaignListResponse,
  CampaignRead,
  Canton,
  officeLabels,
  Province,
  statusLabels,
} from './types';

export default function CampaignsPage() {
  const { user } = useAuth();
  const admin = canAdministerCampaigns(user);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { active, setActive } = useCampaign();
  const campaigns = useQuery({
    queryKey: ['campaign-list'],
    queryFn: () => apiRequest<CampaignListResponse>('/campaigns?page=1&page_size=100'),
  });
  const provinces = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<Province[]>('/provinces'),
  });
  const cantons = useQuery({
    queryKey: ['cantons', 'all'],
    queryFn: () => apiRequest<Canton[]>('/cantons'),
  });
  const details = useQueries({
    queries: (campaigns.data?.items ?? []).map((item) => ({
      queryKey: ['campaign-detail', item.id],
      queryFn: () => apiRequest<CampaignRead>(`/campaigns/${item.id}`),
    })),
  });
  useEffect(() => {
    const onlyCampaign = campaigns.data?.items[0];
    if (campaigns.data?.items.length === 1 && onlyCampaign && !canSeeCampaignAdministration(user)) {
      setActive(onlyCampaign);
      navigate(`/app/campaigns/${onlyCampaign.id}/dashboard`, { replace: true });
    }
  }, [campaigns.data?.items, navigate, setActive, user]);
  const location = (cantonId: number) => {
    const canton = cantons.data?.find((item) => item.id === cantonId);
    const province = provinces.data?.find((item) => item.id === canton?.province_id);
    return { canton: canton?.name ?? '—', province: province?.name ?? '—' };
  };
  const toggle = async (campaign: CampaignRead) => {
    await apiRequest(`/campaigns/${campaign.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !campaign.is_active }),
    });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['campaign-list'] }),
      queryClient.invalidateQueries({ queryKey: ['campaigns'] }),
      queryClient.invalidateQueries({ queryKey: ['campaign-detail', campaign.id] }),
    ]);
  };
  return (
    <>
      <PageHeader
        title="Campañas"
        description="Selecciona una campaña para trabajar o administra sus datos generales."
        action={
          admin ? (
            <Button
              component={RouterLink}
              to="/app/campaigns/new"
              startIcon={<AddIcon />}
              variant="contained"
            >
              Crear campaña
            </Button>
          ) : undefined
        }
      />
      {campaigns.isLoading ? (
        <LoadingSkeleton />
      ) : campaigns.isError ? (
        <ErrorState retry={() => campaigns.refetch()} />
      ) : !campaigns.data?.items.length ? (
        <Stack spacing={2}>
          <EmptyState
            title="No existen campañas registradas."
            detail={
              admin
                ? 'Crea la primera campaña para comenzar la carga de información real.'
                : 'No tienes campañas asignadas.'
            }
          />
          {admin && (
            <Button
              component={RouterLink}
              to="/app/campaigns/new"
              variant="contained"
              sx={{ alignSelf: 'center' }}
            >
              Crear primera campaña
            </Button>
          )}
        </Stack>
      ) : (
        <Grid container spacing={2}>
          {campaigns.data.items.map((summary, index) => {
            const detail = details[index]?.data as CampaignRead | undefined;
            const place = location(summary.canton_id);
            const selected = active?.id === summary.id;
            return (
              <Grid key={summary.id} size={{ xs: 12, lg: 6 }}>
                <Card
                  variant="outlined"
                  sx={selected ? { borderColor: 'primary.main', borderWidth: 2 } : undefined}
                >
                  <CardContent>
                    <Stack spacing={1}>
                      <Stack direction="row" justifyContent="space-between" gap={1}>
                        <Typography variant="h2">{summary.name}</Typography>
                        <Stack direction="row" gap={1}>
                          <Chip label={statusLabels[summary.status]} />
                          <Chip
                            color={summary.is_active ? 'success' : 'default'}
                            label={summary.is_active ? 'Activa' : 'Inactiva'}
                          />
                        </Stack>
                      </Stack>
                      <Typography>
                        <strong>Elección:</strong> {summary.election_name}
                      </Typography>
                      <Typography>
                        <strong>Cargo:</strong> {officeLabels[summary.office_type]}
                      </Typography>
                      <Typography>
                        <strong>Provincia / cantón:</strong> {place.province} / {place.canton}
                      </Typography>
                      <Typography>
                        <strong>Fecha electoral:</strong> {formatDateOnly(summary.election_date)}
                      </Typography>
                      <Typography>
                        <strong>Período:</strong>{' '}
                        {formatDateRange(detail?.start_date, detail?.end_date)}
                      </Typography>
                      <Typography>
                        <strong>Candidato:</strong>{' '}
                        {detail?.candidate?.display_name ?? 'Sin candidato principal'}
                      </Typography>
                      {selected && <Alert severity="info">Campaña activa en esta sesión.</Alert>}
                    </Stack>
                  </CardContent>
                  <CardActions sx={{ flexWrap: 'wrap' }}>
                    <Button component={RouterLink} to={`/app/campaigns/${summary.id}`}>
                      Ver
                    </Button>
                    {admin && (
                      <Button component={RouterLink} to={`/app/campaigns/${summary.id}/edit`}>
                        Editar
                      </Button>
                    )}
                    <Button
                      onClick={() => {
                        setActive(summary);
                        navigate(`/app/campaigns/${summary.id}/dashboard`);
                      }}
                    >
                      Seleccionar como activa
                    </Button>
                    {admin && detail && (
                      <Button
                        color={detail.is_active ? 'warning' : 'success'}
                        onClick={() => toggle(detail)}
                      >
                        {detail.is_active ? 'Desactivar' : 'Activar'}
                      </Button>
                    )}
                  </CardActions>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}
    </>
  );
}
