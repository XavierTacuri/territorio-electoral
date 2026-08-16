import { useState } from 'react';
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { entitlementStatusLabels, entitlementTypeLabels, labelFor } from '../../lib/labels';
type Feature = {
  enabled: boolean;
  entitlement_type: 'LICENSE' | 'TRIAL' | 'ADMIN_OVERRIDE';
  expires_at: string | null;
  status: string;
};
type License = {
  campaign_id: string;
  campaign_name: string;
  commercial_plan: string;
  features: Feature[];
};
export default function FeatureEntitlementsPage() {
  const list = useQuery({
    queryKey: ['feature-entitlements'],
    queryFn: () => apiRequest<License[]>('/admin/feature-entitlements'),
  });
  const [type, setType] = useState<Feature['entitlement_type']>('TRIAL');
  const [expires, setExpires] = useState('');
  const save = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiRequest(`/admin/campaigns/${id}/feature-entitlements/TERRITORY_AI`, {
        method: 'PUT',
        body: JSON.stringify({
          feature_code: 'TERRITORY_AI',
          enabled,
          entitlement_type: type,
          expires_at: expires ? new Date(expires).toISOString() : null,
        }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feature-entitlements'] }),
  });
  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Licencia y funcionalidades
      </Typography>
      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            select
            label="Tipo"
            value={type}
            onChange={(e) => setType(e.target.value as Feature['entitlement_type'])}
          >
            {Object.entries(entitlementTypeLabels).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            type="datetime-local"
            label="Vigencia hasta"
            value={expires}
            onChange={(e) => setExpires(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </Stack>
      </Paper>
      {save.isError && <Alert severity="error">No se pudo actualizar la licencia.</Alert>}
      {list.data?.map((c) => {
        const f = c.features[0];
        return (
          <Paper key={c.campaign_id} sx={{ p: 3 }}>
            <Typography variant="h6">{c.campaign_name}</Typography>
            <Typography>Plan informativo: {c.commercial_plan}</Typography>
            <Typography>
              Estado: {f ? labelFor(entitlementStatusLabels, f.status) : 'No habilitada'}
            </Typography>
            <Typography color="text.secondary">
              Vigencia:{' '}
              {f?.expires_at ? new Date(f.expires_at).toLocaleString() : 'Sin vencimiento'}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <Button
                variant="contained"
                onClick={() => save.mutate({ id: c.campaign_id, enabled: true })}
              >
                Habilitar
              </Button>
              <Button
                color="error"
                onClick={() => save.mutate({ id: c.campaign_id, enabled: false })}
              >
                Deshabilitar
              </Button>
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}
