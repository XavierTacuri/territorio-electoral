import { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import {
  eventStatusLabel,
  formatEventTime,
  FILTERS,
  isDone,
  matchesFilter,
  type CalendarEvent,
  type CalendarFilterValue,
} from './types';

function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function monthLabel(d: Date) {
  return d.toLocaleDateString('es-EC', { month: 'long', year: 'numeric' });
}
function statusColor(event: CalendarEvent): 'success' | 'info' {
  return isDone(event) ? 'success' : 'info';
}
const WEEKDAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const AGENDA_GROUPS = ['HOY', 'MAÑANA', 'PRÓXIMAMENTE', 'REALIZADAS RECIENTEMENTE'] as const;

function agendaGroupOf(event: CalendarEvent, todayIso: string, tomorrowIso: string): (typeof AGENDA_GROUPS)[number] {
  if (isDone(event)) return 'REALIZADAS RECIENTEMENTE';
  const day = event.starts_at.slice(0, 10);
  if (day === todayIso) return 'HOY';
  if (day === tomorrowIso) return 'MAÑANA';
  return 'PRÓXIMAMENTE';
}

function EventCard({ event, onSelect }: { event: CalendarEvent; onSelect: (event: CalendarEvent) => void }) {
  return (
    <Card variant="outlined">
      <CardContent
        sx={{ cursor: 'pointer' }}
        onClick={() => onSelect(event)}
        role="button"
        aria-label={event.title}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={1}>
          <Box sx={{ minWidth: 0 }}>
            <Typography fontWeight={700}>{event.title}</Typography>
            <Typography color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
              {formatDateOnly(event.starts_at.slice(0, 10))} · {event.start_time ?? 'Hora no registrada'}
              {event.parish_name ? ` · ${event.parish_name}` : ''}
            </Typography>
          </Box>
          <Chip size="small" color={statusColor(event)} label={eventStatusLabel(event)} />
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function CalendarPage() {
  const { campaignId = '' } = useParams();
  const [view, setView] = useState<'MES' | 'AGENDA'>('AGENDA');
  const [anchor, setAnchor] = useState(() => new Date());
  const [filter, setFilter] = useState<CalendarFilterValue>('all');
  const [selected, setSelected] = useState<CalendarEvent | null>(null);
  const today = useMemo(() => new Date(), []);
  const todayIso = ymd(today);
  const tomorrowIso = useMemo(() => {
    const d = new Date(today);
    d.setDate(d.getDate() + 1);
    return ymd(d);
  }, [today]);

  const range = useMemo(() => {
    if (view === 'AGENDA') {
      const from = new Date();
      const to = new Date();
      to.setDate(to.getDate() + 60);
      return { from: ymd(from), to: ymd(to) };
    }
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    return { from: ymd(first), to: ymd(last) };
  }, [view, anchor]);

  const query = useQuery({
    queryKey: ['calendar', campaignId, range.from, range.to],
    queryFn: () =>
      apiRequest<{ events: CalendarEvent[] }>(
        `/campaigns/${campaignId}/calendar?date_from=${range.from}&date_to=${range.to}`,
      ),
  });

  const events = (query.data?.events ?? []).filter((e) => matchesFilter(e, filter, todayIso));
  const emptyMessage =
    filter === 'done'
      ? 'No hay actividades realizadas en este periodo.'
      : 'No hay actividades de campaña programadas para este periodo.';

  const days = useMemo(() => {
    if (view !== 'MES') return [];
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const startOffset = (first.getDay() + 6) % 7;
    const gridStart = new Date(first);
    gridStart.setDate(gridStart.getDate() - startOffset);
    return Array.from({ length: 42 }, (_, i) => {
      const day = new Date(gridStart);
      day.setDate(day.getDate() + i);
      return day;
    });
  }, [view, anchor]);

  const agendaGroups = useMemo(() => {
    if (view !== 'AGENDA') return [];
    const sorted = events.slice().sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    return AGENDA_GROUPS.map((label) => ({
      label,
      items: sorted.filter((e) => agendaGroupOf(e, todayIso, tomorrowIso) === label),
    })).filter((group) => group.items.length > 0);
  }, [view, events, todayIso, tomorrowIso]);

  return (
    <>
      <PageHeader
        title="Calendario de campaña"
        description="Actividades de campaña programadas y realizadas, por parroquia y fecha."
        action={
          <ToggleButtonGroup
            exclusive
            size="small"
            value={view}
            onChange={(_e, value) => value && setView(value)}
          >
            <ToggleButton value="MES">Mes</ToggleButton>
            <ToggleButton value="AGENDA">Agenda</ToggleButton>
          </ToggleButtonGroup>
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        {FILTERS.map((f) => (
          <Chip
            key={f.value}
            label={f.label}
            color={filter === f.value ? 'primary' : 'default'}
            onClick={() => setFilter(f.value)}
            variant={filter === f.value ? 'filled' : 'outlined'}
          />
        ))}
      </Stack>
      {view === 'MES' && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
          <Button
            size="small"
            aria-label="Mes anterior"
            onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))}
          >
            <ChevronLeftIcon />
          </Button>
          <Typography sx={{ textTransform: 'capitalize' }} fontWeight={700}>
            {monthLabel(anchor)}
          </Typography>
          <Button
            size="small"
            aria-label="Mes siguiente"
            onClick={() => setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))}
          >
            <ChevronRightIcon />
          </Button>
        </Stack>
      )}
      {query.isLoading ? (
        <LoadingSkeleton />
      ) : query.isError ? (
        <ErrorState retry={() => query.refetch()} />
      ) : !events.length ? (
        <EmptyState title={emptyMessage} detail="Ajusta el filtro o cambia de periodo para ver más actividades." />
      ) : view === 'AGENDA' ? (
        <Stack spacing={2.5}>
          {agendaGroups.map((group) => (
            <Box key={group.label}>
              <Typography variant="overline" color="text.secondary">
                {group.label}
              </Typography>
              <Stack spacing={1.5} sx={{ mt: 1 }}>
                {group.items.map((event) => (
                  <EventCard key={event.id} event={event} onSelect={setSelected} />
                ))}
              </Stack>
            </Box>
          ))}
        </Stack>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, 1fr)',
            gap: 0.5,
            overflowX: 'auto',
          }}
        >
          {WEEKDAYS.map((w) => (
            <Typography key={w} align="center" fontWeight={700} color="text.secondary">
              {w}
            </Typography>
          ))}
          {days.map((day) => {
            const dayEvents = events.filter((e) => e.starts_at.slice(0, 10) === ymd(day));
            const inMonth = day.getMonth() === anchor.getMonth();
            return (
              <Card
                key={day.toISOString()}
                variant="outlined"
                sx={{ minHeight: 90, opacity: inMonth ? 1 : 0.4, p: 0.5 }}
              >
                <Typography variant="caption" color="text.secondary">
                  {day.getDate()}
                </Typography>
                <Stack spacing={0.25} sx={{ mt: 0.25 }}>
                  {dayEvents.slice(0, 2).map((e) => (
                    <Chip
                      key={e.id}
                      size="small"
                      label={e.title}
                      color={statusColor(e)}
                      onClick={() => setSelected(e)}
                      sx={{ maxWidth: '100%', '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
                    />
                  ))}
                  {dayEvents.length > 2 && (
                    <Typography variant="caption">+{dayEvents.length - 2} más</Typography>
                  )}
                </Stack>
              </Card>
            );
          })}
        </Box>
      )}
      <Dialog open={!!selected} onClose={() => setSelected(null)} fullWidth maxWidth="sm">
        <DialogTitle>{selected?.title}</DialogTitle>
        <DialogContent>
          {selected && (
            <Stack spacing={1}>
              <Chip
                size="small"
                sx={{ alignSelf: 'flex-start' }}
                color={statusColor(selected)}
                label={eventStatusLabel(selected)}
              />
              <Typography>
                {formatDateOnly(selected.starts_at.slice(0, 10))} ·{' '}
                {selected.start_time ?? formatEventTime(selected.starts_at) ?? 'Hora no registrada'}
              </Typography>
              {selected.description && <Typography>{selected.description}</Typography>}
              {selected.parish_name && <Typography>Territorio: {selected.parish_name}</Typography>}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(null)}>Cerrar</Button>
          {selected?.deep_link && (
            <Button variant="contained" component={RouterLink} to={selected.deep_link}>
              Ver detalle
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
}
