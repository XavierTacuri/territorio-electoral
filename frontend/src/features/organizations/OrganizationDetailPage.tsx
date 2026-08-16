import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Skeleton,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useActiveOrganization } from '../../app/OrganizationProvider';
import { useAuth } from '../../auth/AuthProvider';
import { DataTable } from '../../components/tables/DataTable';
import { statusLabels as campaignStatusLabels } from '../campaigns/types';
import {
  auditEventLabels,
  entitlementStatusLabels,
  entitlementTypeLabels,
  featureLabels,
  labelFor,
  memberStatusLabels,
  organizationRoleLabels,
  organizationStatusLabels,
  subscriptionStatusLabels,
} from '../../lib/labels';
import { organizationError } from './errors';
import type { AuditEvent, License, Member, Organization, Subscription, Usage } from './types';

type Campaign = {
  id: string;
  name: string;
  canton_name: string | null;
  province_name: string | null;
  election_name: string;
  status: string;
};
type FoundUser = { id: string; username: string; email: string; display_name: string };
const tabNames = ['Resumen', 'Campañas', 'Usuarios', 'Plan y límites', 'Licencias', 'Auditoría'];
const dateValue = (value: string | null | undefined) => (value ? value.slice(0, 16) : '');

export default function OrganizationDetailPage() {
  const { organizationId } = useParams();
  const { activeOrganization, setActiveOrganization } = useActiveOrganization();
  const id = organizationId ?? activeOrganization?.id;
  const { user } = useAuth();
  const platformAdmin =
    !!user && (user.is_superuser || user.roles.some((role) => role.code === 'ADMIN'));
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [error, setError] = useState('');
  const [memberOpen, setMemberOpen] = useState(false);
  const [subscriptionOpen, setSubscriptionOpen] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const [search, setSearch] = useState('');
  const [found, setFound] = useState<FoundUser | null>(null);
  const [memberRole, setMemberRole] = useState<Member['organization_role']>('MEMBER');
  const [memberStatus, setMemberStatus] = useState<Member['status']>('ACTIVE');
  const detail = useQuery({
    queryKey: ['organization', id],
    queryFn: () => apiRequest<Organization>(`/organizations/${id}`),
    enabled: !!id,
  });
  const usage = useQuery({
    queryKey: ['organization-usage', id],
    queryFn: () => apiRequest<Usage>(`/organizations/${id}/usage`),
    enabled: !!id,
  });
  const subscription = useQuery({
    queryKey: ['organization-subscription', id],
    queryFn: () => apiRequest<Subscription>(`/organizations/${id}/subscription`),
    enabled: !!id,
  });
  const campaigns = useQuery({
    queryKey: ['campaigns', id],
    queryFn: () =>
      apiRequest<{ items: Campaign[] }>(`/campaigns?page_size=100&organization_id=${id}`),
    enabled: !!id,
  });
  const members = useQuery({
    queryKey: ['organization-members', id],
    queryFn: () => apiRequest<Member[]>(`/organizations/${id}/memberships`),
    enabled:
      !!id && (platformAdmin || ['OWNER', 'ADMIN'].includes(detail.data?.current_role ?? '')),
  });
  const licenses = useQuery({
    queryKey: ['organization-licenses', id],
    queryFn: () => apiRequest<License[]>(`/organizations/${id}/licenses`),
    enabled: !!id,
  });
  const audit = useQuery({
    queryKey: ['organization-audit', id],
    queryFn: () => apiRequest<AuditEvent[]>(`/organizations/${id}/audit`),
    enabled:
      !!id && (platformAdmin || ['OWNER', 'ADMIN'].includes(detail.data?.current_role ?? '')),
  });
  useEffect(() => {
    if (detail.data && activeOrganization?.id !== detail.data.id) {
      setActiveOrganization(detail.data);
    }
  }, [activeOrganization?.id, detail.data, setActiveOrganization]);
  const canManageMembers =
    platformAdmin || ['OWNER', 'ADMIN'].includes(detail.data?.current_role ?? '');
  const refresh = async () =>
    Promise.all(
      [
        'organizations',
        'organization',
        'organization-usage',
        'organization-members',
        'organization-subscription',
        'organization-audit',
      ].map((key) => qc.invalidateQueries({ queryKey: [key] })),
    );
  const statusMutation = useMutation({
    mutationFn: (status: 'ACTIVE' | 'SUSPENDED') =>
      apiRequest<Organization>(`/organizations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: async () => {
      setConfirmStatus(false);
      await refresh();
    },
    onError: (reason) => setError(organizationError(reason)),
  });
  const memberMutation = useMutation({
    mutationFn: ({
      userId,
      role,
      status,
    }: {
      userId: string;
      role: Member['organization_role'];
      status: Member['status'];
    }) =>
      apiRequest<Member>(`/organizations/${id}/memberships`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, organization_role: role, status }),
      }),
    onSuccess: async () => {
      setMemberOpen(false);
      setFound(null);
      setSearch('');
      await refresh();
    },
    onError: (reason) => setError(organizationError(reason)),
  });
  const removeMember = useMutation({
    mutationFn: (membershipId: string) =>
      apiRequest(`/organizations/${id}/memberships/${membershipId}`, { method: 'DELETE' }),
    onSuccess: refresh,
    onError: (reason) => setError(organizationError(reason)),
  });
  const [subForm, setSubForm] = useState({
    plan_code: 'STANDARD',
    status: 'ACTIVE',
    starts_at: '',
    expires_at: '',
    trial_ends_at: '',
    max_campaigns: '',
    max_users: '',
  });
  const showSubscription = () => {
    const value = subscription.data;
    if (!value) return;
    setSubForm({
      plan_code: value.plan_code,
      status: value.status,
      starts_at: dateValue(value.starts_at),
      expires_at: dateValue(value.expires_at),
      trial_ends_at: dateValue(value.trial_ends_at),
      max_campaigns: value.max_campaigns?.toString() ?? '',
      max_users: value.max_users?.toString() ?? '',
    });
    setSubscriptionOpen(true);
  };
  const subscriptionMutation = useMutation({
    mutationFn: () =>
      apiRequest<Subscription>(`/organizations/${id}/subscription`, {
        method: 'PUT',
        body: JSON.stringify({
          plan_code: subForm.plan_code,
          status: subForm.status,
          starts_at: subForm.starts_at ? new Date(subForm.starts_at).toISOString() : null,
          expires_at: subForm.expires_at ? new Date(subForm.expires_at).toISOString() : null,
          trial_ends_at: subForm.trial_ends_at
            ? new Date(subForm.trial_ends_at).toISOString()
            : null,
          max_campaigns: subForm.max_campaigns ? Number(subForm.max_campaigns) : null,
          max_users: subForm.max_users ? Number(subForm.max_users) : null,
          metadata: {},
        }),
      }),
    onSuccess: async () => {
      setSubscriptionOpen(false);
      await refresh();
    },
    onError: (reason) => setError(organizationError(reason)),
  });
  const searchUser = async () => {
    try {
      const result = await apiRequest<FoundUser[]>(
        `/organizations/${id}/users/search?query=${encodeURIComponent(search)}`,
      );
      setFound(result[0] ?? null);
      if (!result.length)
        setError('No se encontró un usuario activo con ese email o username exacto.');
    } catch (reason) {
      setError(organizationError(reason));
    }
  };
  if (!id) return <Alert severity="info">Selecciona una organización.</Alert>;
  if (detail.isLoading) return <Skeleton height={240} />;
  if (detail.isError || !detail.data)
    return <Alert severity="error">{organizationError(detail.error)}</Alert>;
  const organization = detail.data;
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
        <Stack>
          <Typography variant="h4">{organization.name}</Typography>
          <Typography color="text.secondary">
            {organization.legal_name || organization.slug}
          </Typography>
        </Stack>
        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
          <Chip
            label={organization.plan_code ?? 'Sin plan'}
            color={organization.plan_code === 'PRO' ? 'primary' : 'default'}
          />
          <Chip
            label={organizationStatusLabels[organization.status]}
            color={organization.status === 'ACTIVE' ? 'success' : 'warning'}
          />
          {subscription.data?.status === 'TRIAL' && (
            <Chip
              label={`Prueba hasta ${subscription.data.trial_ends_at ? new Date(subscription.data.trial_ends_at).toLocaleDateString() : 'sin fecha'}`}
              color="info"
            />
          )}
          {platformAdmin && (
            <Button
              color={organization.status === 'ACTIVE' ? 'error' : 'success'}
              onClick={() => setConfirmStatus(true)}
            >
              {organization.status === 'ACTIVE' ? 'Suspender' : 'Reactivar'}
            </Button>
          )}
        </Stack>
      </Stack>
      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      <Paper sx={{ overflow: 'hidden' }}>
        <Tabs
          value={tab}
          onChange={(_, value) => setTab(value)}
          variant="scrollable"
          scrollButtons="auto"
        >
          {tabNames.map((name) => (
            <Tab key={name} label={name} />
          ))}
        </Tabs>
      </Paper>
      {tab === 0 && (
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
            <Metric
              label="Campañas"
              value={`${usage.data?.campaigns_used ?? organization.campaign_count} / ${usage.data?.campaigns_limit ?? '∞'}`}
            />
            <Metric
              label="Usuarios"
              value={`${usage.data?.users_used ?? organization.user_count} / ${usage.data?.users_limit ?? '∞'}`}
            />
            <Metric label="Consultas IA" value={String(usage.data?.ai_requests_used ?? 0)} />
          </Stack>
          <Paper sx={{ p: 2 }}>
            <Typography>Estado: {organizationStatusLabels[organization.status]}</Typography>
            <Typography>
              Plan actual: {subscription.data?.plan_code ?? 'Sin suscripción'}
            </Typography>
            <Typography>
              Inicio:{' '}
              {subscription.data?.starts_at
                ? new Date(subscription.data.starts_at).toLocaleString()
                : 'Sin fecha'}
            </Typography>
            <Typography>
              Expiración:{' '}
              {subscription.data?.expires_at
                ? new Date(subscription.data.expires_at).toLocaleString()
                : 'Sin vencimiento'}
            </Typography>
          </Paper>
        </Stack>
      )}
      {tab === 1 && (
        <DataTable
          label="campañas de la organización"
          emptyTitle="No hay campañas en esta organización."
          loading={campaigns.isLoading}
          rows={campaigns.data?.items ?? []}
          columns={[
            { key: 'name', label: 'Campaña', render: (row) => row.name },
            {
              key: 'territory',
              label: 'Territorio',
              render: (row) => [row.canton_name, row.province_name].filter(Boolean).join(', '),
            },
            { key: 'election', label: 'Elección', render: (row) => row.election_name },
            {
              key: 'status',
              label: 'Estado',
              render: (row) =>
                campaignStatusLabels[row.status as keyof typeof campaignStatusLabels] ??
                'No disponible',
            },
            {
              key: 'action',
              label: '',
              render: (row) => (
                <Button onClick={() => navigate(`/app/campaigns/${row.id}/dashboard`)}>
                  Abrir campaña
                </Button>
              ),
            },
          ]}
        />
      )}
      {tab === 2 && (
        <Stack spacing={2}>
          {canManageMembers ? (
            <>
              <Stack direction="row" justifyContent="flex-end">
                <Button
                  variant="contained"
                  onClick={() => {
                    setFound(null);
                    setMemberOpen(true);
                  }}
                >
                  Agregar miembro
                </Button>
              </Stack>
              <DataTable
                label="miembros de la organización"
                emptyTitle="No hay usuarios registrados."
                loading={members.isLoading}
                rows={members.data ?? []}
                columns={[
                  {
                    key: 'user',
                    label: 'Usuario',
                    render: (row) => (
                      <Stack>
                        <Typography>{row.display_name || row.username}</Typography>
                        <Typography variant="caption">{row.email}</Typography>
                      </Stack>
                    ),
                  },
                  {
                    key: 'role',
                    label: 'Rol',
                    render: (row) => organizationRoleLabels[row.organization_role],
                  },
                  {
                    key: 'status',
                    label: 'Estado',
                    render: (row) => memberStatusLabels[row.status],
                  },
                  {
                    key: 'actions',
                    label: 'Acciones',
                    render: (row) => (
                      <Stack direction="row">
                        <Button
                          onClick={() => {
                            setFound({
                              id: row.user_id,
                              username: row.username ?? '',
                              email: row.email ?? '',
                              display_name: row.display_name ?? '',
                            });
                            setMemberRole(row.organization_role);
                            setMemberStatus(row.status);
                            setMemberOpen(true);
                          }}
                        >
                          Editar
                        </Button>
                        <Button color="error" onClick={() => removeMember.mutate(row.id)}>
                          Eliminar
                        </Button>
                      </Stack>
                    ),
                  },
                ]}
              />
            </>
          ) : (
            <Alert severity="info">
              Tu rol permite consultar la organización, pero no administrar miembros.
            </Alert>
          )}
        </Stack>
      )}
      {tab === 3 && (
        <Paper sx={{ p: 3 }}>
          <Stack spacing={1}>
            <Typography variant="h6">Suscripción y límites</Typography>
            <Typography>Plan: {subscription.data?.plan_code ?? '—'}</Typography>
            <Typography>
              Estado:{' '}
              {subscription.data
                ? subscriptionStatusLabels[subscription.data.status]
                : 'No disponible'}
            </Typography>
            <Typography>
              Inicio:{' '}
              {subscription.data?.starts_at
                ? new Date(subscription.data.starts_at).toLocaleString()
                : 'Sin fecha'}
            </Typography>
            <Typography>
              Expira:{' '}
              {subscription.data?.expires_at
                ? new Date(subscription.data.expires_at).toLocaleString()
                : 'Sin vencimiento'}
            </Typography>
            <Typography>
              Prueba hasta:{' '}
              {subscription.data?.trial_ends_at
                ? new Date(subscription.data.trial_ends_at).toLocaleString()
                : 'Sin fecha'}
            </Typography>
            <Typography>
              Máximo de campañas: {subscription.data?.max_campaigns ?? 'Sin límite'}
            </Typography>
            <Typography>
              Máximo de usuarios: {subscription.data?.max_users ?? 'Sin límite'}
            </Typography>
            {platformAdmin && (
              <Button
                sx={{ alignSelf: 'flex-start' }}
                variant="contained"
                onClick={showSubscription}
              >
                Editar suscripción
              </Button>
            )}
          </Stack>
        </Paper>
      )}
      {tab === 4 && (
        <Stack spacing={2}>
          <Typography color="text.secondary">
            Las licencias por campaña se administran de forma independiente del plan general de la
            organización.
          </Typography>
          {licenses.isLoading && <Skeleton height={120} />}
          {licenses.data?.length === 0 && (
            <Alert severity="info">No hay campañas con licencias registradas.</Alert>
          )}
          {licenses.data?.map((license) => (
            <Paper key={license.campaign_id} sx={{ p: 2 }}>
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between">
                <Stack>
                  <Typography variant="h6">{license.campaign_name}</Typography>
                  <Typography>{featureLabels.TERRITORY_AI}</Typography>
                  <Typography>
                    Estado:{' '}
                    {license.features[0]
                      ? labelFor(entitlementStatusLabels, license.features[0].status)
                      : 'No habilitada'}
                  </Typography>
                  <Typography color="text.secondary">
                    Tipo:{' '}
                    {license.features[0]
                      ? labelFor(entitlementTypeLabels, license.features[0].entitlement_type)
                      : 'No disponible'}{' '}
                    · Vigencia:{' '}
                    {license.features[0]?.expires_at
                      ? new Date(license.features[0].expires_at).toLocaleString()
                      : 'Sin vencimiento'}
                  </Typography>
                </Stack>
                {platformAdmin && (
                  <Button onClick={() => navigate('/app/admin/feature-entitlements')}>
                    Administrar licencia
                  </Button>
                )}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
      {tab === 5 &&
        (canManageMembers ? (
          <DataTable
            label="auditoría organizacional"
            emptyTitle="No hay eventos de auditoría."
            loading={audit.isLoading}
            rows={audit.data ?? []}
            columns={[
              {
                key: 'date',
                label: 'Fecha',
                render: (row) => new Date(row.created_at).toLocaleString(),
              },
              { key: 'actor', label: 'Actor', render: (row) => row.actor || 'Sistema' },
              {
                key: 'event',
                label: 'Evento',
                render: (row) => auditEventLabels[row.event_type] ?? 'Evento de auditoría',
              },
              { key: 'description', label: 'Resumen', render: (row) => row.description },
            ]}
          />
        ) : (
          <Alert severity="info">
            No tienes permisos para consultar la auditoría organizacional.
          </Alert>
        ))}
      <Dialog open={memberOpen} onClose={() => setMemberOpen(false)} fullWidth>
        <DialogTitle>{found ? 'Editar miembro' : 'Agregar miembro'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} pt={1}>
            {!found && (
              <>
                <TextField
                  label="Email o nombre de usuario exacto"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <Button onClick={searchUser}>Buscar usuario</Button>
              </>
            )}
            {found && (
              <Alert severity="info">
                {found.display_name} · {found.email}
              </Alert>
            )}
            <TextField
              select
              label="Rol organizacional"
              value={memberRole}
              onChange={(event) => setMemberRole(event.target.value as Member['organization_role'])}
            >
              {['OWNER', 'ADMIN', 'MEMBER'].map((value) => (
                <MenuItem key={value} value={value}>
                  {organizationRoleLabels[value as keyof typeof organizationRoleLabels]}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Estado"
              value={memberStatus}
              onChange={(event) => setMemberStatus(event.target.value as Member['status'])}
            >
              {['ACTIVE', 'INACTIVE', 'INVITED'].map((value) => (
                <MenuItem key={value} value={value}>
                  {memberStatusLabels[value as keyof typeof memberStatusLabels]}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMemberOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!found || memberMutation.isPending}
            onClick={() =>
              found &&
              memberMutation.mutate({ userId: found.id, role: memberRole, status: memberStatus })
            }
          >
            Guardar miembro
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={subscriptionOpen} onClose={() => setSubscriptionOpen(false)} fullWidth>
        <DialogTitle>Editar suscripción</DialogTitle>
        <DialogContent>
          <Stack spacing={2} pt={1}>
            <TextField
              select
              label="Plan"
              value={subForm.plan_code}
              onChange={(event) => setSubForm({ ...subForm, plan_code: event.target.value })}
            >
              <MenuItem value="STANDARD">STANDARD</MenuItem>
              <MenuItem value="PRO">PRO</MenuItem>
            </TextField>
            <TextField
              select
              label="Estado de suscripción"
              value={subForm.status}
              onChange={(event) => setSubForm({ ...subForm, status: event.target.value })}
            >
              {['TRIAL', 'ACTIVE', 'PAST_DUE', 'SUSPENDED', 'EXPIRED', 'CANCELLED'].map((value) => (
                <MenuItem key={value} value={value}>
                  {subscriptionStatusLabels[value as keyof typeof subscriptionStatusLabels]}
                </MenuItem>
              ))}
            </TextField>
            {(['starts_at', 'expires_at', 'trial_ends_at'] as const).map((key) => (
              <TextField
                key={key}
                type="datetime-local"
                label={
                  {
                    starts_at: 'Fecha de inicio',
                    expires_at: 'Fecha de expiración',
                    trial_ends_at: 'Prueba hasta',
                  }[key]
                }
                InputLabelProps={{ shrink: true }}
                value={subForm[key]}
                onChange={(event) => setSubForm({ ...subForm, [key]: event.target.value })}
              />
            ))}
            <TextField
              type="number"
              inputProps={{ min: 1 }}
              label="Máximo de campañas"
              value={subForm.max_campaigns}
              onChange={(event) => setSubForm({ ...subForm, max_campaigns: event.target.value })}
            />
            <TextField
              type="number"
              inputProps={{ min: 1 }}
              label="Máximo de usuarios"
              value={subForm.max_users}
              onChange={(event) => setSubForm({ ...subForm, max_users: event.target.value })}
            />
            {['SUSPENDED', 'CANCELLED'].includes(subForm.status) && (
              <Alert severity="warning">
                Este estado bloqueará el acceso operativo. Confirma antes de guardar.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSubscriptionOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => subscriptionMutation.mutate()}>
            Guardar suscripción
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={confirmStatus} onClose={() => setConfirmStatus(false)}>
        <DialogTitle>
          {organization.status === 'ACTIVE' ? 'Suspender organización' : 'Reactivar organización'}
        </DialogTitle>
        <DialogContent>
          <Typography>
            {organization.status === 'ACTIVE'
              ? 'Los usuarios dejarán de operar sus campañas. Los datos no se eliminarán.'
              : 'Los usuarios recuperarán el acceso según sus permisos.'}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmStatus(false)}>Cancelar</Button>
          <Button
            color={organization.status === 'ACTIVE' ? 'error' : 'success'}
            variant="contained"
            onClick={() =>
              statusMutation.mutate(organization.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE')
            }
          >
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Paper sx={{ p: 2, flex: 1 }}>
      <Typography color="text.secondary">{label}</Typography>
      <Typography variant="h4">{value}</Typography>
    </Paper>
  );
}
