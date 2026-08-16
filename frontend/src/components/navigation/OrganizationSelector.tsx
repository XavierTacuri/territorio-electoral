import { FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { type ActiveOrganization, useActiveOrganization } from '../../app/OrganizationProvider';
import { useCampaign } from '../../app/CampaignProvider';

export function OrganizationSelector() {
  const { activeOrganization, setActiveOrganization } = useActiveOrganization();
  const { setActive } = useCampaign();
  const { data = [] } = useQuery({
    queryKey: ['organizations'],
    queryFn: () => apiRequest<ActiveOrganization[]>('/organizations'),
  });
  useEffect(() => {
    if (!data.length) return;
    const valid = activeOrganization && data.find((item) => item.id === activeOrganization.id);
    if (!valid) {
      setActiveOrganization(data[0]);
      setActive(null);
    }
  }, [activeOrganization, data, setActive, setActiveOrganization]);
  if (data.length <= 1) {
    const organization = data[0];
    return organization ? (
      <Stack sx={{ minWidth: 150 }}>
        <Typography variant="caption" color="inherit">
          Organización
        </Typography>
        <Typography noWrap fontWeight={700}>
          {organization.name}
        </Typography>
      </Stack>
    ) : null;
  }
  return (
    <FormControl
      size="small"
      sx={{ minWidth: 0, width: { xs: 108, sm: 220 }, flexShrink: { xs: 1, sm: 0 } }}
    >
      <InputLabel id="organization-label">Organización</InputLabel>
      <Select
        labelId="organization-label"
        label="Organización"
        value={activeOrganization?.id ?? ''}
        sx={{ '& .MuiSelect-select': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
        onChange={(event) => {
          setActiveOrganization(data.find((item) => item.id === event.target.value) ?? null);
          setActive(null);
        }}
      >
        {data.map((item) => (
          <MenuItem key={item.id} value={item.id}>
            {item.name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
