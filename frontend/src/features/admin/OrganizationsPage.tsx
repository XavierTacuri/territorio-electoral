import { Add, RocketLaunch } from '@mui/icons-material';
import {
  Alert,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Grid,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import type { Organization } from '../organizations/types';
import { organizationStatusLabels } from '../../lib/labels';

export default function OrganizationsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const platformAdmin =
    !!user && (user.is_superuser || user.roles.some((role) => role.code === 'ADMIN'));
  const organizations = useQuery({
    queryKey: ['organizations'],
    queryFn: () => apiRequest<Organization[]>('/organizations'),
  });
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
        <Stack>
          <Typography variant="h4">Organizaciones</Typography>
          <Typography color="text.secondary">Clientes, estado y plan comercial.</Typography>
        </Stack>
        {platformAdmin && (
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
            <Button
              startIcon={<Add />}
              variant="outlined"
              onClick={() => navigate('/app/admin/organizations/new')}
            >
              Nueva organización
            </Button>
            <Button
              startIcon={<RocketLaunch />}
              variant="contained"
              onClick={() => navigate('/app/admin/organizations/onboarding')}
            >
              Configuración guiada
            </Button>
          </Stack>
        )}
      </Stack>
      {organizations.isLoading && (
        <Stack gap={1}>
          <Skeleton height={100} />
          <Skeleton height={100} />
        </Stack>
      )}
      {organizations.isError && (
        <Alert severity="error">No fue posible cargar las organizaciones.</Alert>
      )}
      {organizations.data?.length === 0 && (
        <Alert severity="info">No hay organizaciones registradas.</Alert>
      )}
      <Grid container spacing={2}>
        {organizations.data?.map((organization) => (
          <Grid key={organization.id} size={{ xs: 12, md: 6, xl: 4 }}>
            <Card>
              <CardActionArea
                onClick={() => navigate(`/app/admin/organizations/${organization.id}`)}
              >
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" gap={1}>
                    <Typography variant="h6">{organization.name}</Typography>
                    <Chip
                      size="small"
                      label={organizationStatusLabels[organization.status]}
                      color={organization.status === 'ACTIVE' ? 'success' : 'warning'}
                    />
                  </Stack>
                  <Typography color="text.secondary">
                    {organization.legal_name || organization.slug}
                  </Typography>
                  <Stack direction="row" gap={1} mt={2}>
                    <Chip
                      label={organization.plan_code ?? 'Sin plan'}
                      color={organization.plan_code === 'PRO' ? 'primary' : 'default'}
                    />
                    <Typography>
                      {organization.campaign_count} campañas · {organization.user_count} usuarios
                    </Typography>
                  </Stack>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}
