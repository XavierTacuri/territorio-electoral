import { useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { PageHeader } from '../../components/layout/PageHeader';
import {
  OPERATION_STATUS_LABELS,
  type ElectionDayAdminSupportCampaignOption,
  type ElectionDayAdminSupportSession,
} from '../election-day/types';

function extractDetail(error: unknown): string | undefined {
  if (
    error instanceof ApiError &&
    error.detail &&
    typeof error.detail === 'object' &&
    'detail' in error.detail
  ) {
    const detail = (error.detail as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return undefined;
}

function optionLabel(option: ElectionDayAdminSupportCampaignOption) {
  return `${option.campaign_name} · ${OPERATION_STATUS_LABELS[option.operation_status]}`;
}

export default function ElectionDaySupportPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [campaignId, setCampaignId] = useState('');
  const [reason, setReason] = useState('');
  const [startError, setStartError] = useState<string | null>(null);

  // Fase 3.1 §7: nunca GET /campaigns?page_size=200 — este listado ya viene
  // filtrado a campañas con Jornada configurada y solo lo sirve el backend a
  // un ADMIN, sin depender de la organización activa del conmutador global.
  const campaigns = useQuery({
    queryKey: ['admin-election-day-support-campaigns'],
    queryFn: () =>
      apiRequest<ElectionDayAdminSupportCampaignOption[]>('/election-day/admin-support/campaigns'),
  });
  const options = campaigns.data ?? [];
  const selected = options.find((o) => o.campaign_id === campaignId) ?? null;

  const session = useQuery({
    queryKey: ['admin-election-day-support', campaignId, 'current'],
    queryFn: () =>
      apiRequest<ElectionDayAdminSupportSession | null>(
        `/campaigns/${campaignId}/election-day/admin-support/current`,
      ),
    enabled: !!campaignId,
    retry: false,
  });
  const active = session.data ?? null;

  const start = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayAdminSupportSession>(
        `/campaigns/${campaignId}/election-day/admin-support/start`,
        { method: 'POST', body: JSON.stringify({ reason: reason.trim() || undefined }) },
      ),
    onError: (error) => {
      setStartError(extractDetail(error) ?? 'No fue posible iniciar el modo soporte.');
    },
    onSuccess: () => {
      setStartError(null);
      qc.invalidateQueries({ queryKey: ['admin-election-day-support', campaignId, 'current'] });
    },
  });

  const end = useMutation({
    mutationFn: () =>
      apiRequest<ElectionDayAdminSupportSession>(
        `/campaigns/${campaignId}/election-day/admin-support/end`,
        { method: 'POST' },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-election-day-support', campaignId, 'current'] });
    },
  });

  return (
    <>
      <PageHeader
        title="Soporte Jornada Electoral"
        description="Modo soporte administrativo explícito: un ADMIN nunca opera la jornada por privilegio implícito. Solo consulta el Centro de Control y valida actas mientras mantiene una sesión de soporte activa para una campaña a la vez."
      />
      <Card variant="outlined" sx={{ mb: 3, maxWidth: 560 }}>
        <CardContent>
          <Autocomplete
            options={options}
            getOptionLabel={optionLabel}
            isOptionEqualToValue={(option, value) => option.campaign_id === value.campaign_id}
            value={selected}
            loading={campaigns.isLoading}
            noOptionsText="No hay campañas con Jornada Electoral configurada."
            onChange={(_event, value) => {
              setCampaignId(value?.campaign_id ?? '');
              setStartError(null);
            }}
            filterOptions={(items, state) => {
              const input = state.inputValue.trim().toLowerCase();
              if (!input) return items;
              return items.filter(
                (o) =>
                  o.campaign_name.toLowerCase().includes(input) ||
                  o.organization_name.toLowerCase().includes(input),
              );
            }}
            renderOption={(props, option) => (
              <Box component="li" {...props} key={option.campaign_id}>
                <Box>
                  <Typography variant="body2">{optionLabel(option)}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {option.organization_name}
                  </Typography>
                </Box>
              </Box>
            )}
            renderInput={(params) => <TextField {...params} label="Campaña" />}
            sx={{ mb: 2 }}
          />

          {!campaignId && (
            <Typography color="text.secondary">Selecciona una campaña para continuar.</Typography>
          )}

          {campaignId && selected && !active && (
            <Stack spacing={2}>
              <Typography color="text.secondary">
                No tienes una sesión de soporte activa en esta campaña. Estado actual de la jornada:{' '}
                {OPERATION_STATUS_LABELS[selected.operation_status]}.
              </Typography>
              <TextField
                label="Motivo (opcional)"
                multiline
                minRows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              {startError && <Alert severity="error">{startError}</Alert>}
              <Button variant="contained" disabled={start.isPending} onClick={() => start.mutate()}>
                INICIAR MODO SOPORTE
              </Button>
            </Stack>
          )}

          {campaignId && selected && active && (
            <Stack spacing={2}>
              <Alert severity="warning">
                <Typography fontWeight={700}>Modo soporte administrativo activo</Typography>
                <Typography variant="body2">Campaña: {selected.campaign_name}</Typography>
                <Typography variant="body2">
                  Estado: {OPERATION_STATUS_LABELS[selected.operation_status]}
                </Typography>
                {active.reason && <Typography variant="body2">Motivo: {active.reason}</Typography>}
              </Alert>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                <Button
                  variant="contained"
                  onClick={() =>
                    navigate(`/app/campaigns/${campaignId}/election-day/control-center`)
                  }
                >
                  ENTRAR AL CENTRO DE CONTROL
                </Button>
                <Button
                  variant="contained"
                  onClick={() => navigate(`/app/campaigns/${campaignId}/election-day/validation`)}
                >
                  VALIDACIÓN DE ACTAS
                </Button>
                <Button
                  variant="outlined"
                  color="warning"
                  disabled={end.isPending}
                  onClick={() => end.mutate()}
                >
                  SALIR DEL MODO SOPORTE
                </Button>
              </Stack>
            </Stack>
          )}
        </CardContent>
      </Card>
    </>
  );
}
