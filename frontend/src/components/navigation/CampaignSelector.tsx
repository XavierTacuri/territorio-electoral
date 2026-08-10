import {
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canAdministerCampaigns } from '../../auth/permissions';
type Campaigns = { items: { id: string; name: string }[] };
export function CampaignSelector() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const { active, setActive } = useCampaign();
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => apiRequest<Campaigns>('/campaigns?page_size=100'),
  });
  const value = campaignId ?? active?.id ?? '';
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
          if (campaign) navigate('/app/campaigns/' + campaign.id + '/dashboard');
        }}
      >
        <MenuItem value="" disabled>
          Selecciona una campaña
        </MenuItem>
        {data?.items.map((item) => (
          <MenuItem key={item.id} value={item.id}>
            {item.name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
