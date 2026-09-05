import { Alert, Chip, List, ListItemButton, ListItemText, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { LoadingSkeleton } from '../../components/feedback/States';
import { formatDateOnly, todayDateOnly } from '../../lib/dates';
import { operationStatusLabel } from '../operations/statusLabels';
import { useFieldAgenda } from './useFieldAgenda';
import { useFieldContext } from './useFieldContext';

type OfficialMilestone = { id: string; title: string; starts_at: string };

// Read-only, session-cached (React Query), never written to the offline
// outbox: there is no field UI to create/edit a milestone, so there is
// nothing to sync. Scoped to this campaign's own calendar range, not a
// national download.
function useOfficialMilestones(campaignId: string, online: boolean) {
  const from = todayDateOnly();
  const to = todayDateOnly(new Date(Date.now() + 30 * 86400000));
  const query = useQuery({
    queryKey: ['field-official-milestones', campaignId, from, to],
    queryFn: () =>
      apiRequest<{ events: { id: string; event_type: string; title: string; starts_at: string }[] }>(
        `/campaigns/${campaignId}/calendar?date_from=${from}&date_to=${to}`,
      ),
    enabled: online && !!campaignId,
    staleTime: 15 * 60 * 1000,
  });
  const items: OfficialMilestone[] = (query.data?.events ?? [])
    .filter((e) => e.event_type === 'OFFICIAL_ELECTORAL_MILESTONE')
    .map((e) => ({ id: e.id, title: e.title, starts_at: e.starts_at }));
  return { items, fetchedAt: query.dataUpdatedAt || null };
}

function bucket(date: string, today: string, tomorrow: string): 'Hoy' | 'Mañana' | 'Próximos días' {
  if (date === today) return 'Hoy';
  if (date === tomorrow) return 'Mañana';
  return 'Próximos días';
}

export default function FieldAgendaPage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const field = useFieldContext();
  const agenda = useFieldAgenda(field.scope);
  const milestones = useOfficialMilestones(campaignId, field.online);

  if (field.loading || agenda.loading) return <LoadingSkeleton />;

  const today = todayDateOnly();
  const tomorrow = todayDateOnly(new Date(Date.now() + 86400000));
  const groups: Record<string, typeof agenda.items> = { Hoy: [], Mañana: [], 'Próximos días': [] };
  for (const item of [...agenda.items].sort((a, b) => a.activity_date.localeCompare(b.activity_date))) {
    groups[bucket(item.activity_date, today, tomorrow)].push(item);
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h2" sx={{ fontSize: '1.2rem' }}>
        Mi agenda
      </Typography>
      {agenda.fromCache && (
        <Alert severity="info">
          Última actualización:{' '}
          {agenda.fetchedAt ? new Date(agenda.fetchedAt).toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' }) : 'no disponible'}
          . No se actualiza en tiempo real sin conexión.
        </Alert>
      )}
      {Object.entries(groups).map(([label, items]) => (
        <Stack key={label} spacing={1}>
          <Typography variant="h3" sx={{ fontSize: '1rem' }}>
            {label}
          </Typography>
          {items.length === 0 ? (
            <Typography color="text.secondary" variant="body2">
              Sin actividades.
            </Typography>
          ) : (
            <List disablePadding>
              {items.map((item) => (
                <ListItemButton
                  key={item.id}
                  divider
                  onClick={() => navigate(`/app/campaigns/${campaignId}/field/activities/${item.id}`)}
                >
                  <ListItemText
                    primary={item.title}
                    secondary={`${formatDateOnly(item.activity_date)} · ${item.parish_name ?? 'Sin parroquia'}`}
                  />
                  <Chip
                    size="small"
                    label={operationStatusLabel(
                      item.approval_status === 'PENDING_APPROVAL' ? item.approval_status : item.status,
                    )}
                  />
                </ListItemButton>
              ))}
            </List>
          )}
        </Stack>
      ))}
      {milestones.items.length > 0 && (
        <Stack spacing={1}>
          <Typography variant="h3" sx={{ fontSize: '1rem' }}>
            Hitos electorales oficiales
          </Typography>
          <List disablePadding>
            {milestones.items.map((item) => (
              <ListItemButton key={item.id} divider disableRipple sx={{ cursor: 'default' }}>
                <ListItemText primary={item.title} secondary={formatDateOnly(item.starts_at.slice(0, 10))} />
                <Chip size="small" color="primary" label="Oficial" />
              </ListItemButton>
            ))}
          </List>
          {milestones.fetchedAt && (
            <Typography variant="caption" color="text.secondary">
              Última actualización:{' '}
              {new Date(milestones.fetchedAt).toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}
            </Typography>
          )}
        </Stack>
      )}
    </Stack>
  );
}
