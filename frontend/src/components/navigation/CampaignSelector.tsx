import {
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canAdministerCampaigns, isElectionDayStaffOnly } from '../../auth/permissions';
import type { ActiveCampaign } from '../../app/CampaignProvider';
import { type ActiveOrganization, useOptionalOrganization } from '../../app/OrganizationProvider';
type Campaigns = { items: ActiveCampaign[] };
export function CampaignSelector() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const pathCampaignId = location.pathname.match(/^\/app\/campaigns\/([^/]+)/)?.[1];
  const routeCampaignId = campaignId ?? (pathCampaignId === 'new' ? undefined : pathCampaignId);
  const { active, setActive } = useCampaign();
  const { user } = useAuth();
  const platformAdmin =
    !!user && (user.is_superuser || user.roles.some((role) => role.code === 'ADMIN'));
  const organization = useOptionalOrganization();
  const organizationId = organization?.activeOrganization?.id;
  const organizations = useQuery({
    queryKey: ['organizations'],
    queryFn: () => apiRequest<ActiveOrganization[]>('/organizations'),
    enabled: !!organization,
  });
  const { data } = useQuery({
    queryKey: ['campaigns', routeCampaignId || platformAdmin ? 'all' : (organizationId ?? 'all')],
    queryFn: () =>
      apiRequest<Campaigns>(
        `/campaigns?page_size=100${organizationId && !routeCampaignId && !platformAdmin ? `&organization_id=${organizationId}` : ''}`,
      ),
    // Personal de Jornada sin CampaignUser nunca aparece aquí — no tiene
    // sentido consultarla para ese perfil.
    enabled: !isElectionDayStaffOnly(user),
  });
  const value = routeCampaignId ?? active?.id ?? '';
  useEffect(() => {
    if (!data) return;
    if (routeCampaignId) {
      const routeCampaign = data.items.find((item) => item.id === routeCampaignId);
      if (!routeCampaign) {
        // Personal de Jornada sin CampaignUser (Fase 1B §18/§22) nunca
        // aparece en /campaigns — su acceso a las rutas de Jornada Electoral
        // lo decide el backend vía ElectionDayAssignment, no esta lista
        // general. No lo redirijas a /403 solo por no estar en ella.
        if (isElectionDayStaffOnly(user)) return;
        setActive(null);
        navigate('/403', { replace: true });
      } else {
        if (active?.id !== routeCampaign.id) setActive(routeCampaign);
        if (organization && organization.activeOrganization?.id !== routeCampaign.organization_id) {
          const routeOrganization = organizations.data?.find(
            (item) => item.id === routeCampaign.organization_id,
          );
          if (routeOrganization) organization.setActiveOrganization(routeOrganization);
        }
      }
    } else if (active && !data.items.some((item) => item.id === active.id)) setActive(null);
  }, [active, data, navigate, organization, organizations.data, routeCampaignId, setActive, user]);
  // Personal de Jornada sin CampaignUser (Fase 1B §4): nunca aparece en
  // /campaigns, así que el selector general no tiene nada que ofrecerle. En
  // vez de "No existen campañas" (que sugiere un problema) se muestra el
  // contexto real en el que opera, y nunca se resuelve creándole un
  // CampaignUser solo para que la lista deje de estar vacía.
  if (isElectionDayStaffOnly(user))
    return (
      <Typography color="inherit" fontWeight={700}>
        Jornada Electoral
      </Typography>
    );
  if (data && data.items.length === 0)
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography color="inherit">No existen campañas</Typography>
        {canAdministerCampaigns(user) && (
          <Button color="inherit" size="small" onClick={() => navigate('/app/campaigns/new')}>
            Crear primera campaña
          </Button>
        )}
      </Stack>
    );
  return (
    <FormControl
      size="small"
      sx={{ minWidth: 0, width: { xs: 148, sm: 240 }, flexShrink: { xs: 1, sm: 0 } }}
    >
      <InputLabel id="campaign-label">Campaña</InputLabel>
      <Select
        labelId="campaign-label"
        label="Campaña"
        value={value}
        sx={{ '& .MuiSelect-select': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
        onChange={(event) => {
          const campaign = data?.items.find((item) => item.id === event.target.value) ?? null;
          setActive(campaign);
          if (campaign) {
            if (organization && organization.activeOrganization?.id !== campaign.organization_id) {
              const selectedOrganization = organizations.data?.find(
                (item) => item.id === campaign.organization_id,
              );
              if (selectedOrganization) organization.setActiveOrganization(selectedOrganization);
            }
            const currentPrefix = routeCampaignId ? `/app/campaigns/${routeCampaignId}` : null;
            navigate(
              currentPrefix && location.pathname.startsWith(currentPrefix)
                ? location.pathname.replace(currentPrefix, `/app/campaigns/${campaign.id}`) +
                    location.search
                : `/app/campaigns/${campaign.id}/dashboard`,
            );
          }
        }}
      >
        <MenuItem value="" disabled>
          Selecciona una campaña
        </MenuItem>
        {data?.items.map((item) => (
          <MenuItem key={item.id} value={item.id}>
            <Stack>
              <Typography>{item.name}</Typography>
              <Typography variant="caption" color="text.secondary">
                {[item.canton_name, item.province_name].filter(Boolean).join(' · ')}
              </Typography>
            </Stack>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
