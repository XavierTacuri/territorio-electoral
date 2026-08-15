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
import { canAdministerCampaigns } from '../../auth/permissions';
import type { ActiveCampaign } from '../../app/CampaignProvider';
type Campaigns = { items: ActiveCampaign[] };
export function CampaignSelector() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const pathCampaignId = location.pathname.match(/^\/app\/campaigns\/([^/]+)/)?.[1];
  const routeCampaignId = campaignId ?? (pathCampaignId === 'new' ? undefined : pathCampaignId);
  const { active, setActive } = useCampaign();
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => apiRequest<Campaigns>('/campaigns?page_size=100'),
  });
  const value = routeCampaignId ?? active?.id ?? '';
  useEffect(() => {
    if (!data) return;
    if (routeCampaignId) {
      const routeCampaign = data.items.find((item) => item.id === routeCampaignId);
      if (!routeCampaign) {
        setActive(null);
        navigate('/403', { replace: true });
      } else if (active?.id !== routeCampaign.id) setActive(routeCampaign);
    } else if (active && !data.items.some((item) => item.id === active.id)) setActive(null);
  }, [active, data, navigate, routeCampaignId, setActive]);
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
    <FormControl size="small" sx={{ minWidth: { xs: 180, sm: 240 } }}>
      <InputLabel id="campaign-label">Campaña</InputLabel>
      <Select
        labelId="campaign-label"
        label="Campaña"
        value={value}
        onChange={(event) => {
          const campaign = data?.items.find((item) => item.id === event.target.value) ?? null;
          setActive(campaign);
          if (campaign) {
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
