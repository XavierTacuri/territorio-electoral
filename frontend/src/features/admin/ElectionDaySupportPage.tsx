import { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { PageHeader } from '../../components/layout/PageHeader';
import type { ElectionDayAdminSupportSession } from '../election-day/types';

type CampaignOption = { id: string; name: string };

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

export default function ElectionDaySupportPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [campaignId, setCampaignId] = useState('');
  const [reason, setReason] = useState('');
  const [startError, setStartError] = useState<string | null>(null);

  const campaigns = useQuery({
    queryKey: ['admin-election-day-support-campaigns'],
    queryFn: () => apiRequest<{ items: CampaignOption[] }>('/campaigns?page_size=200'),
  });

  const session = useQuery({
    queryKey: ['admin-election-day-support', campaignId, 'current'],
    queryFn: () =>
      apiRequest<ElectionDayAdminSupportSession | null>(
        `/campaigns/${campaignId}/election-day/admin-support/current`,
      ),
    enabled: !!campaignId,
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
        description="Modo soporte administrativo explícito: un ADMIN nunca opera la jornada por privilegio implícito. Solo consulta el Centro de Control mientras mantiene una sesión de soporte activa para una campaña a la vez."
      />
      <Card variant="outlined" sx={{ mb: 3, maxWidth: 520 }}>
        <CardContent>
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel id="ed-support-campaign">Campaña</InputLabel>
            <Select
              labelId="ed-support-campaign"
              label="Campaña"
              value={campaignId}
              onChange={(e) => {
                setCampaignId(e.target.value);
                setStartError(null);
              }}
            >
              {(campaigns.data?.items ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {!campaignId && (
            <Typography color="text.secondary">Selecciona una campaña para continuar.</Typography>
          )}

          {campaignId && !active && (
            <Stack spacing={2}>
              <Typography color="text.secondary">
                No tienes una sesión de soporte activa en esta campaña. Si aún no existe una Jornada
                Electoral configurada (solo el Candidato o Jefe de Campaña puede crearla), el
                intento de inicio lo indicará.
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

          {campaignId && active && (
            <Stack spacing={2}>
              <Alert severity="info">
                Modo soporte administrativo activo.
                {active.reason ? ` Motivo: ${active.reason}.` : ''}
              </Alert>
              <Button
                variant="contained"
                onClick={() => navigate(`/app/campaigns/${campaignId}/election-day/control-center`)}
              >
                ENTRAR AL CENTRO DE CONTROL
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
          )}
        </CardContent>
      </Card>
    </>
  );
}
