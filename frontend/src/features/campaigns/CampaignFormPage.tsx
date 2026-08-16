import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  TextField,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useCampaign } from '../../app/CampaignProvider';
import { useOptionalOrganization } from '../../app/OrganizationProvider';
import { useAuth } from '../../auth/AuthProvider';
import { canAdministerCampaigns } from '../../auth/permissions';
import { PageHeader } from '../../components/layout/PageHeader';
import { LoadingSkeleton } from '../../components/feedback/States';
import { formatDateOnly } from '../../lib/dates';
import { campaignFormSchema, CampaignFormValues, slugify, toCampaignPayload } from './campaignForm';
import {
  CampaignRead,
  CampaignSummary,
  Canton,
  officeLabels,
  Province,
  statusLabels,
} from './types';

const defaults: CampaignFormValues = {
  name: '',
  slug: '',
  province_id: '',
  canton_id: '',
  office_type: 'MAYOR',
  election_name: '',
  election_date: '',
  start_date: '',
  end_date: '',
  status: 'DRAFT',
  description: '',
  is_active: true,
};

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return 'No se pudo guardar la campaña.';
  const detail = error.detail as { detail?: unknown } | undefined;
  if (error.status === 409) return 'Ya existe una campaña con este identificador.';
  if (error.status === 403) return 'No tienes permisos para administrar campañas.';
  if (error.status === 404) return 'La campaña o el cantón seleccionado no existe.';
  if (error.status === 422) return 'Revisa los campos indicados.';
  return typeof detail?.detail === 'string' ? detail.detail : error.message;
}

export default function CampaignFormPage() {
  const { campaignId } = useParams();
  const editing = !!campaignId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setActive } = useCampaign();
  const activeOrganization = useOptionalOrganization()?.activeOrganization ?? null;
  const { user } = useAuth();
  const [error, setError] = useState('');
  const [slugEdited, setSlugEdited] = useState(false);
  const form = useForm<CampaignFormValues>({
    resolver: zodResolver(campaignFormSchema),
    defaultValues: defaults,
  });
  const provinces = useQuery({
    queryKey: ['provinces'],
    queryFn: () => apiRequest<Province[]>('/provinces'),
  });
  const campaign = useQuery({
    queryKey: ['campaign-detail', campaignId],
    queryFn: () => apiRequest<CampaignRead>(`/campaigns/${campaignId}`),
    enabled: editing,
  });
  const campaignCanton = useQuery({
    queryKey: ['canton', campaign.data?.canton_id],
    queryFn: () => apiRequest<Canton>(`/cantons/${campaign.data!.canton_id}`),
    enabled: !!campaign.data,
  });
  const provinceId = form.watch('province_id');
  const cantons = useQuery({
    queryKey: ['cantons', provinceId],
    queryFn: () => apiRequest<Canton[]>(`/cantons?province_id=${provinceId}`),
    enabled: !!provinceId,
  });

  useEffect(() => {
    if (!campaign.data || !campaignCanton.data) return;
    form.reset({
      name: campaign.data.name,
      slug: campaign.data.slug,
      province_id: String(campaignCanton.data.province_id),
      canton_id: String(campaign.data.canton_id),
      office_type: campaign.data.office_type,
      election_name: campaign.data.election_name,
      election_date: formatDateOnly(campaign.data.election_date),
      start_date: campaign.data.start_date ? formatDateOnly(campaign.data.start_date) : '',
      end_date: campaign.data.end_date ? formatDateOnly(campaign.data.end_date) : '',
      status: campaign.data.status,
      description: campaign.data.description ?? '',
      is_active: campaign.data.is_active,
    });
    setSlugEdited(true);
  }, [campaign.data, campaignCanton.data, form]);

  const validCantons = useMemo(
    () => (cantons.data ?? []).filter((item) => item.is_active),
    [cantons.data],
  );
  const save = useMutation({
    mutationFn: (values: CampaignFormValues) =>
      apiRequest<CampaignSummary>(editing ? `/campaigns/${campaignId}` : '/campaigns', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify({
          ...toCampaignPayload(values, editing),
          ...(!editing && activeOrganization ? { organization_id: activeOrganization.id } : {}),
        }),
      }),
    onSuccess: async (created) => {
      setError('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['campaigns'] }),
        queryClient.invalidateQueries({ queryKey: ['campaign-list'] }),
        queryClient.invalidateQueries({ queryKey: ['campaign-detail', created.id] }),
      ]);
      setActive(created);
      navigate(`/app/campaigns/${created.id}/dashboard`, {
        replace: true,
        state: {
          message: editing ? 'Campaña actualizada correctamente.' : 'Campaña creada correctamente.',
        },
      });
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.status === 422) {
        const detail = (reason.detail as { detail?: Array<{ loc?: unknown[]; msg?: string }> })
          ?.detail;
        const fields = new Set(Object.keys(defaults));
        detail?.forEach((issue) => {
          const field = issue.loc?.at(-1);
          if (typeof field === 'string' && fields.has(field))
            form.setError(field as keyof CampaignFormValues, {
              message: issue.msg ?? 'Valor inválido.',
            });
        });
      }
      setError(errorMessage(reason));
    },
  });

  const canCreateInOrganization =
    activeOrganization?.current_role === 'OWNER' || activeOrganization?.current_role === 'ADMIN';
  if (!canAdministerCampaigns(user) && !canCreateInOrganization)
    return <Navigate to="/403" replace />;
  if (editing && (campaign.isLoading || campaignCanton.isLoading)) return <LoadingSkeleton />;
  return (
    <>
      <PageHeader
        title={editing ? 'Editar campaña' : 'Crear campaña'}
        description="Los datos territoriales provienen de los catálogos oficiales disponibles en el sistema."
      />
      <Paper
        component="form"
        variant="outlined"
        sx={{ p: { xs: 2, md: 3 }, maxWidth: 900 }}
        onSubmit={form.handleSubmit((values) => save.mutate(values))}
      >
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Nombre de campaña"
            {...form.register('name', {
              onChange: (event) => {
                if (!slugEdited)
                  form.setValue('slug', slugify(event.target.value), { shouldValidate: true });
              },
            })}
            error={!!form.formState.errors.name}
            helperText={form.formState.errors.name?.message}
          />
          <TextField
            label="Identificador (slug)"
            {...form.register('slug', { onChange: () => setSlugEdited(true) })}
            error={!!form.formState.errors.slug}
            helperText={
              form.formState.errors.slug?.message ?? 'Único, en minúsculas y sin espacios.'
            }
          />
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              select
              fullWidth
              label="Provincia"
              disabled={editing || provinces.isLoading}
              value={provinceId}
              onChange={(event) => {
                form.setValue('province_id', event.target.value, { shouldValidate: true });
                form.setValue('canton_id', '', { shouldValidate: true });
              }}
              error={!!form.formState.errors.province_id}
              helperText={
                editing
                  ? 'El territorio no puede cambiarse mediante el endpoint de edición.'
                  : form.formState.errors.province_id?.message
              }
            >
              {(provinces.data ?? [])
                .filter((item) => item.is_active)
                .map((item) => (
                  <MenuItem key={item.id} value={String(item.id)}>
                    {item.name}
                  </MenuItem>
                ))}
            </TextField>
            <TextField
              select
              fullWidth
              label="Cantón"
              disabled={editing || !provinceId || cantons.isLoading}
              value={form.watch('canton_id')}
              onChange={(event) =>
                form.setValue('canton_id', event.target.value, { shouldValidate: true })
              }
              error={!!form.formState.errors.canton_id}
              helperText={form.formState.errors.canton_id?.message}
            >
              {editing &&
                campaignCanton.data &&
                !validCantons.some((item) => String(item.id) === form.watch('canton_id')) && (
                  <MenuItem value={String(campaignCanton.data.id)}>
                    {campaignCanton.data.name}
                  </MenuItem>
                )}
              {validCantons.map((item) => (
                <MenuItem key={item.id} value={String(item.id)}>
                  {item.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              select
              fullWidth
              label="Cargo o dignidad"
              value={form.watch('office_type')}
              onChange={(event) =>
                form.setValue(
                  'office_type',
                  event.target.value as CampaignFormValues['office_type'],
                  { shouldValidate: true },
                )
              }
            >
              {Object.entries(officeLabels).map(([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              fullWidth
              label="Tipo o nombre de elección"
              {...form.register('election_name')}
              error={!!form.formState.errors.election_name}
              helperText={form.formState.errors.election_name?.message}
            />
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              fullWidth
              label="Fecha electoral"
              placeholder="DD/MM/AAAA"
              {...form.register('election_date')}
              error={!!form.formState.errors.election_date}
              helperText={form.formState.errors.election_date?.message}
            />
            <TextField
              fullWidth
              label="Fecha de inicio"
              placeholder="DD/MM/AAAA"
              {...form.register('start_date')}
              error={!!form.formState.errors.start_date}
              helperText={form.formState.errors.start_date?.message}
            />
            <TextField
              fullWidth
              label="Fecha de finalización"
              placeholder="DD/MM/AAAA"
              {...form.register('end_date')}
              error={!!form.formState.errors.end_date}
              helperText={form.formState.errors.end_date?.message}
            />
          </Stack>
          <TextField
            select
            label="Estado"
            value={form.watch('status')}
            onChange={(event) =>
              form.setValue('status', event.target.value as CampaignFormValues['status'])
            }
          >
            {Object.entries(statusLabels).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Descripción (opcional)"
            multiline
            minRows={3}
            {...form.register('description')}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={form.watch('is_active')}
                onChange={(event) => form.setValue('is_active', event.target.checked)}
              />
            }
            label="Campaña activa"
          />
          <Stack direction="row" justifyContent="flex-end" spacing={1}>
            <Button
              onClick={() => navigate(editing ? `/app/campaigns/${campaignId}` : '/app/campaigns')}
            >
              Cancelar
            </Button>
            <Button type="submit" variant="contained" disabled={save.isPending}>
              {save.isPending ? 'Guardando…' : 'Guardar campaña'}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </>
  );
}
