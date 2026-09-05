import { useState } from 'react';
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { DataTable } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import { commercialErrorMessages } from '../../lib/labels';
import { parishOptionLabel } from '../../lib/territoryLabels';

type Campaign = { id: string; name: string; canton_id: number };
type User = { id: string; username: string; first_name: string; last_name: string };
type Parish = {
  id: number;
  name: string;
  canton_id: number;
  dpa_code?: string;
  parish_type?: 'URBAN' | 'RURAL';
};
type Community = { id: string; name: string; parish_id: number };
type Sector = { id: string; name: string; community_id: string };
type Assignment = {
  id: string;
  user_id: string;
  parish_id: number;
  community_id: string | null;
  sector_id: string | null;
  is_active: boolean;
};
type CampaignUser = { id: string; user_id: string; is_active: boolean };

export function assignmentPayload(
  userId: string,
  parishId: string,
  communityId: string,
  sectorId: string,
) {
  if (!userId || !parishId) throw new Error('Seleccione usuario y parroquia.');
  if (sectorId && !communityId) throw new Error('Un sector requiere una comunidad.');
  return {
    user_id: userId,
    parish_id: Number(parishId),
    community_id: communityId || null,
    sector_id: sectorId || null,
  };
}

export function assignmentError(error: unknown) {
  if (error instanceof ApiError) {
    const responseDetail =
      error.detail && typeof error.detail === 'object' && 'detail' in error.detail
        ? error.detail.detail
        : error.detail;
    const code =
      responseDetail && typeof responseDetail === 'object' && 'code' in responseDetail
        ? String(responseDetail.code)
        : '';
    if (code in commercialErrorMessages) return commercialErrorMessages[code];
    return (
      {
        403: 'No tienes permisos para asignar usuarios a esta campaña.',
        404: 'Territorio no encontrado.',
        409: 'La asignacion ya existe.',
        422: 'Revise la jerarquia territorial.',
      }[error.status] ?? error.message
    );
  }
  return 'No se pudo modificar la asignacion.';
}

export default function AssignmentsPage() {
  const qc = useQueryClient();
  const [campaignId, setCampaignId] = useState('');
  const [userId, setUserId] = useState('');
  const [parishId, setParishId] = useState('');
  const [communityId, setCommunityId] = useState('');
  const [sectorId, setSectorId] = useState('');
  const [error, setError] = useState('');
  const campaigns = useQuery({
    queryKey: ['admin-campaigns'],
    queryFn: () => apiRequest<{ items: Campaign[] }>('/campaigns?page_size=100'),
  });
  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiRequest<{ items: User[] }>('/users?page=1&page_size=100'),
  });
  const selectedCampaign = campaigns.data?.items.find((x) => x.id === campaignId);
  const parishes = useQuery({
    queryKey: ['parishes', selectedCampaign?.canton_id],
    queryFn: () => apiRequest<Parish[]>('/parishes?canton_id=' + selectedCampaign!.canton_id),
    enabled: !!selectedCampaign,
  });
  const communities = useQuery({
    queryKey: ['communities', parishId],
    queryFn: () =>
      apiRequest<{ items: Community[] }>('/communities?parish_id=' + parishId + '&page_size=100'),
    enabled: !!parishId,
  });
  const sectors = useQuery({
    queryKey: ['sectors', communityId],
    queryFn: () =>
      apiRequest<{ items: Sector[] }>('/sectors?community_id=' + communityId + '&page_size=100'),
    enabled: !!communityId,
  });
  const campaignUsers = useQuery({
    queryKey: ['campaign-users', campaignId],
    queryFn: () => apiRequest<CampaignUser[]>(`/campaigns/${campaignId}/users`),
    enabled: !!campaignId,
  });
  const assignments = useQuery({
    queryKey: ['territorial-assignments', campaignId],
    queryFn: () => apiRequest<Assignment[]>(`/campaigns/${campaignId}/territorial-assignments`),
    enabled: !!campaignId,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['campaign-users', campaignId] });
    qc.invalidateQueries({ queryKey: ['territorial-assignments', campaignId] });
  };
  const mutate = useMutation({
    mutationFn: ({
      path,
      method = 'POST',
      body,
    }: {
      path: string;
      method?: string;
      body?: unknown;
    }) => apiRequest(path, { method, body: body ? JSON.stringify(body) : undefined }),
    onSuccess: () => {
      setError('');
      refresh();
    },
    onError: (reason) => setError(assignmentError(reason)),
  });
  const userName = (id: string) => {
    const u = users.data?.items.find((x) => x.id === id);
    return u ? `${u.first_name} ${u.last_name} (${u.username})` : id;
  };
  const parishName = (id: number) => parishes.data?.find((x) => x.id === id)?.name ?? String(id);
  const communityName = (id: string | null) =>
    id ? (communities.data?.items.find((x) => x.id === id)?.name ?? id) : 'Toda la parroquia';
  const sectorName = (id: string | null) =>
    id ? (sectors.data?.items.find((x) => x.id === id)?.name ?? id) : 'Todos los sectores';
  return (
    <>
      <PageHeader
        title="Asignaciones"
        description="Acceso de usuarios a campanas y alcance territorial jerarquico."
      />
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <TextField
        select
        fullWidth
        label="Campana"
        value={campaignId}
        onChange={(e) => {
          setCampaignId(e.target.value);
          setUserId('');
          setParishId('');
          setCommunityId('');
          setSectorId('');
        }}
        sx={{ mb: 2 }}
      >
        {(campaigns.data?.items ?? []).map((x) => (
          <MenuItem key={x.id} value={x.id}>
            {x.name}
          </MenuItem>
        ))}
      </TextField>
      {!campaignId ? (
        <Alert severity="info">Seleccione una campana para administrar sus asignaciones.</Alert>
      ) : (
        <Stack spacing={3}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h2" gutterBottom>
              Usuarios de campana
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} gap={2} mb={2} alignItems="flex-start">
              <TextField
                select
                fullWidth
                label="Usuario"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
              >
                {(users.data?.items ?? []).map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {userName(u.id)}
                  </MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                disabled={!userId || mutate.isPending}
                onClick={() =>
                  mutate.mutate({
                    path: `/campaigns/${campaignId}/users`,
                    body: { user_id: userId },
                  })
                }
              >
                Asignar a campana
              </Button>
            </Stack>
            <DataTable
              label="Usuarios asignados"
              rows={campaignUsers.data ?? []}
              loading={campaignUsers.isLoading}
              columns={[
                { key: 'user_id', label: 'Usuario', render: (x) => userName(x.user_id) },
                {
                  key: 'is_active',
                  label: 'Estado',
                  render: (x) => (x.is_active ? 'Activa' : 'Inactiva'),
                },
                {
                  key: 'id',
                  label: 'Acciones',
                  render: (x) => (
                    <Button
                      color="error"
                      onClick={() => {
                        if (confirm('Quitar al usuario de la campana?'))
                          mutate.mutate({
                            path: `/campaigns/${campaignId}/users/${x.user_id}`,
                            method: 'DELETE',
                          });
                      }}
                    >
                      Quitar
                    </Button>
                  ),
                },
              ]}
            />
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h2" gutterBottom>
              Alcance territorial
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} gap={2} mb={2} alignItems="flex-start">
              <TextField
                select
                fullWidth
                label="Usuario coordinador"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
              >
                {(campaignUsers.data ?? []).map((cu) => (
                  <MenuItem key={cu.user_id} value={cu.user_id}>
                    {userName(cu.user_id)}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                fullWidth
                label="Parroquia"
                value={parishId}
                disabled={parishes.isLoading}
                onChange={(e) => {
                  setParishId(e.target.value);
                  setCommunityId('');
                  setSectorId('');
                }}
              >
                {(parishes.data ?? []).map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {parishOptionLabel(p, parishes.data ?? [])}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                fullWidth
                label="Comunidad (opcional)"
                value={communityId}
                disabled={!parishId || communities.isLoading}
                helperText={!parishId ? 'Seleccione primero una parroquia' : ''}
                onChange={(e) => {
                  setCommunityId(e.target.value);
                  setSectorId('');
                }}
              >
                <MenuItem value="">Toda la parroquia</MenuItem>
                {(communities.data?.items ?? []).map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                fullWidth
                label="Sector (opcional)"
                value={sectorId}
                disabled={!communityId || sectors.isLoading}
                helperText={!communityId ? 'Seleccione primero una comunidad' : ''}
                onChange={(e) => setSectorId(e.target.value)}
              >
                <MenuItem value="">Toda la comunidad</MenuItem>
                {(sectors.data?.items ?? []).map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
              </TextField>
              <Button
                sx={{ minWidth: 180 }}
                variant="contained"
                disabled={!userId || !parishId || mutate.isPending}
                onClick={() =>
                  mutate.mutate({
                    path: `/campaigns/${campaignId}/territorial-assignments`,
                    body: assignmentPayload(userId, parishId, communityId, sectorId),
                  })
                }
              >
                Asignar territorio
              </Button>
            </Stack>
            <DataTable
              label="Asignaciones territoriales"
              rows={assignments.data ?? []}
              loading={assignments.isLoading}
              columns={[
                { key: 'user_id', label: 'Usuario', render: (x) => userName(x.user_id) },
                { key: 'parish_id', label: 'Parroquia', render: (x) => parishName(x.parish_id) },
                {
                  key: 'community_id',
                  label: 'Comunidad',
                  render: (x) => communityName(x.community_id),
                },
                { key: 'sector_id', label: 'Sector', render: (x) => sectorName(x.sector_id) },
                {
                  key: 'is_active',
                  label: 'Estado',
                  render: (x) => (x.is_active ? 'Activa' : 'Inactiva'),
                },
                {
                  key: 'id',
                  label: 'Acciones',
                  render: (x) => (
                    <Button
                      color="error"
                      onClick={() => {
                        if (confirm('Eliminar la asignacion territorial?'))
                          mutate.mutate({
                            path: `/campaigns/${campaignId}/territorial-assignments/${x.id}`,
                            method: 'DELETE',
                          });
                      }}
                    >
                      Eliminar
                    </Button>
                  ),
                },
              ]}
            />
          </Paper>
        </Stack>
      )}
    </>
  );
}
