import {
  Alert,
  Button,
  Card,
  CardActionArea,
  CardContent,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { organizationError } from './errors';
import { statusLabels as campaignStatusLabels } from '../campaigns/types';
import { subscriptionStatusLabels } from '../../lib/labels';

type User = { id: string; username: string; email: string; first_name: string; last_name: string };
type Province = { id: number; name: string };
type Canton = { id: number; name: string; province_id: number; is_active: boolean };
const steps = [
  'Organización',
  'Propietario',
  'Plan',
  'Campaña inicial',
  'Provincia / Cantón',
  'Confirmación',
];
const initial = {
  organization: {
    name: '',
    slug: '',
    legal_name: '',
    contact_email: '',
    contact_phone: '',
    country: 'EC',
    timezone: 'America/Guayaquil',
    status: 'ACTIVE',
  },
  owner_user_id: '',
  plan_code: 'STANDARD',
  subscription_status: 'ACTIVE',
  trial_ends_at: '',
  max_campaigns: '3',
  max_users: '10',
  campaign: {
    name: '',
    slug: '',
    office_type: 'MAYOR',
    election_name: '',
    election_date: '',
    status: 'DRAFT',
  },
  province_id: '',
  canton_id: '',
};

export default function OrganizationOnboardingPage() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(initial);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const users = useQuery({
    queryKey: ['admin-users', 'onboarding'],
    queryFn: () => apiRequest<{ items: User[] }>('/users?page=1&page_size=100'),
  });
  const provinces = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<Province[]>('/provinces'),
  });
  const cantons = useQuery({
    queryKey: ['cantons', form.province_id],
    queryFn: () => apiRequest<Canton[]>(`/cantons?province_id=${form.province_id}`),
    enabled: !!form.province_id,
  });
  const selectedOwner = users.data?.items.find((user) => user.id === form.owner_user_id);
  const selectedProvince = provinces.data?.find(
    (province) => String(province.id) === form.province_id,
  );
  const selectedCanton = cantons.data?.find((canton) => String(canton.id) === form.canton_id);
  const valid = useMemo(
    () =>
      [
        !!form.organization.name &&
          /^[a-z0-9-]+$/.test(form.organization.slug) &&
          (!form.organization.contact_email ||
            /^[^@]+@[^@]+\.[^@]+$/.test(form.organization.contact_email)),
        !!form.owner_user_id,
        !!form.plan_code &&
          Number(form.max_campaigns) > 0 &&
          Number(form.max_users) > 0 &&
          (form.subscription_status !== 'TRIAL' || !!form.trial_ends_at),
        !!form.campaign.name &&
          !!form.campaign.slug &&
          !!form.campaign.election_name &&
          !!form.campaign.election_date,
        !!form.province_id && !!form.canton_id,
        true,
      ][step],
    [form, step],
  );
  const save = useMutation({
    mutationFn: () =>
      apiRequest<{ organization: { id: string } }>('/organizations/onboarding', {
        method: 'POST',
        body: JSON.stringify({
          organization: {
            ...form.organization,
            legal_name: form.organization.legal_name || null,
            contact_email: form.organization.contact_email || null,
            contact_phone: form.organization.contact_phone || null,
          },
          owner_user_id: form.owner_user_id,
          subscription: {
            plan_code: form.plan_code,
            status: form.subscription_status,
            trial_ends_at: form.trial_ends_at ? new Date(form.trial_ends_at).toISOString() : null,
            max_campaigns: Number(form.max_campaigns),
            max_users: Number(form.max_users),
            metadata: {},
          },
          campaign: {
            ...form.campaign,
            canton_id: Number(form.canton_id),
            election_date: form.campaign.election_date,
          },
        }),
      }),
    onSuccess: (data) => navigate(`/app/admin/organizations/${data.organization.id}`),
    onError: (reason) => setError(organizationError(reason)),
  });
  const orgField = (key: keyof typeof form.organization) => ({
    value: form.organization[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, organization: { ...form.organization, [key]: event.target.value } }),
  });
  const campaignField = (key: keyof typeof form.campaign) => ({
    value: form.campaign[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, campaign: { ...form.campaign, [key]: event.target.value } }),
  });
  return (
    <Stack spacing={3}>
      <Stack>
        <Typography variant="h4">Onboarding de organización</Typography>
        <Typography color="text.secondary">
          Paso {step + 1} de 6 · {steps[step]}
        </Typography>
      </Stack>
      <Stepper activeStep={step} alternativeLabel sx={{ display: { xs: 'none', md: 'flex' } }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
      {error && <Alert severity="error">{error}</Alert>}
      <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 900 }}>
        {step === 0 && (
          <Stack spacing={2}>
            <TextField required label="Nombre" {...orgField('name')} />
            <TextField
              required
              label="Slug"
              inputProps={{ pattern: '[a-z0-9-]+' }}
              {...orgField('slug')}
            />
            <TextField label="Nombre legal" {...orgField('legal_name')} />
            <TextField type="email" label="Email de contacto" {...orgField('contact_email')} />
            <TextField label="Teléfono" {...orgField('contact_phone')} />
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
              <TextField label="País" {...orgField('country')} />
              <TextField label="Zona horaria" {...orgField('timezone')} />
            </Stack>
          </Stack>
        )}
        {step === 1 && (
          <Stack spacing={2}>
            <Typography>
              Selecciona un usuario existente como propietario. No se solicitan credenciales.
            </Typography>
            <TextField
              select
              required
              label="Propietario"
              value={form.owner_user_id}
              onChange={(event) => setForm({ ...form, owner_user_id: event.target.value })}
            >
              {users.data?.items.map((user) => (
                <MenuItem key={user.id} value={user.id}>
                  {user.first_name} {user.last_name} · {user.email}
                </MenuItem>
              ))}
            </TextField>
            {users.isLoading && <Typography>Cargando usuarios…</Typography>}
            {users.data?.items.length === 0 && (
              <Alert severity="info">
                No hay usuarios disponibles. Créalo primero en Administración → Usuarios.
              </Alert>
            )}
          </Stack>
        )}
        {step === 2 && (
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
              {(['STANDARD', 'PRO'] as const).map((plan) => (
                <Card
                  key={plan}
                  variant={form.plan_code === plan ? 'elevation' : 'outlined'}
                  sx={{
                    flex: 1,
                    borderColor: form.plan_code === plan ? 'primary.main' : undefined,
                  }}
                >
                  <CardActionArea onClick={() => setForm({ ...form, plan_code: plan })}>
                    <CardContent>
                      <Typography variant="h5">{plan}</Typography>
                      <Typography color="text.secondary">
                        {plan === 'PRO'
                          ? 'Incluye Territorio IA según entitlements de campaña.'
                          : 'Plataforma base V2.1–V2.7.'}
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
            <TextField
              select
              label="Estado"
              value={form.subscription_status}
              onChange={(event) => setForm({ ...form, subscription_status: event.target.value })}
            >
              {['ACTIVE', 'TRIAL', 'PAST_DUE', 'SUSPENDED', 'EXPIRED', 'CANCELLED'].map((value) => (
                <MenuItem key={value} value={value}>
                  {subscriptionStatusLabels[value as keyof typeof subscriptionStatusLabels]}
                </MenuItem>
              ))}
            </TextField>
            {form.subscription_status === 'TRIAL' && (
              <TextField
                type="datetime-local"
                label="Prueba hasta"
                InputLabelProps={{ shrink: true }}
                value={form.trial_ends_at}
                onChange={(event) => setForm({ ...form, trial_ends_at: event.target.value })}
              />
            )}
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
              <TextField
                type="number"
                inputProps={{ min: 1 }}
                label="Máximo de campañas"
                value={form.max_campaigns}
                onChange={(event) => setForm({ ...form, max_campaigns: event.target.value })}
              />
              <TextField
                type="number"
                inputProps={{ min: 1 }}
                label="Máximo de usuarios"
                value={form.max_users}
                onChange={(event) => setForm({ ...form, max_users: event.target.value })}
              />
            </Stack>
          </Stack>
        )}
        {step === 3 && (
          <Stack spacing={2}>
            <TextField required label="Nombre de campaña" {...campaignField('name')} />
            <TextField required label="Slug de campaña" {...campaignField('slug')} />
            <TextField select label="Tipo de cargo" {...campaignField('office_type')}>
              <MenuItem value="MAYOR">Alcaldía</MenuItem>
              <MenuItem value="URBAN_COUNCILOR">Concejalía urbana</MenuItem>
              <MenuItem value="RURAL_COUNCILOR">Concejalía rural</MenuItem>
              <MenuItem value="PARISH_BOARD">Junta parroquial</MenuItem>
            </TextField>
            <TextField required label="Elección" {...campaignField('election_name')} />
            <TextField
              required
              type="date"
              label="Fecha electoral"
              InputLabelProps={{ shrink: true }}
              {...campaignField('election_date')}
            />
            <TextField select label="Estado" {...campaignField('status')}>
              {['DRAFT', 'ACTIVE'].map((value) => (
                <MenuItem key={value} value={value}>
                  {campaignStatusLabels[value as keyof typeof campaignStatusLabels]}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        )}
        {step === 4 && (
          <Stack spacing={2}>
            <TextField
              select
              required
              label="Provincia"
              value={form.province_id}
              onChange={(event) =>
                setForm({ ...form, province_id: event.target.value, canton_id: '' })
              }
            >
              {provinces.data?.map((province) => (
                <MenuItem key={province.id} value={String(province.id)}>
                  {province.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              required
              label="Cantón"
              value={form.canton_id}
              disabled={!form.province_id}
              onChange={(event) => setForm({ ...form, canton_id: event.target.value })}
            >
              {cantons.data
                ?.filter((canton) => canton.is_active)
                .map((canton) => (
                  <MenuItem key={canton.id} value={String(canton.id)}>
                    {canton.name}
                  </MenuItem>
                ))}
            </TextField>
          </Stack>
        )}
        {step === 5 && (
          <Stack spacing={1}>
            <Typography variant="h6">Resumen</Typography>
            <Typography>Organización: {form.organization.name}</Typography>
            <Typography>
              Propietario:{' '}
              {selectedOwner
                ? `${selectedOwner.first_name} ${selectedOwner.last_name} · ${selectedOwner.email}`
                : '—'}
            </Typography>
            <Typography>
              Plan: {form.plan_code} ·{' '}
              {
                subscriptionStatusLabels[
                  form.subscription_status as keyof typeof subscriptionStatusLabels
                ]
              }
            </Typography>
            <Typography>
              Límites: {form.max_campaigns} campañas · {form.max_users} usuarios
            </Typography>
            <Typography>
              Campaña: {form.campaign.name} · {form.campaign.election_name}
            </Typography>
            <Typography>
              Territorio: {selectedCanton?.name}, {selectedProvince?.name}
            </Typography>
          </Stack>
        )}
        <Stack direction="row" justifyContent="space-between" mt={3}>
          <Button disabled={step === 0 || save.isPending} onClick={() => setStep(step - 1)}>
            Anterior
          </Button>
          {step < 5 ? (
            <Button variant="contained" disabled={!valid} onClick={() => setStep(step + 1)}>
              Siguiente
            </Button>
          ) : (
            <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>
              Crear organización
            </Button>
          )}
        </Stack>
      </Paper>
    </Stack>
  );
}
