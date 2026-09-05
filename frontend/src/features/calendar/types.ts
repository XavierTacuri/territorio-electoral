export type CalendarEvent = {
  id: string;
  event_type: string;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string | null;
  start_time: string | null;
  parish_id: number | null;
  parish_name: string | null;
  is_official: boolean;
  status: string | null;
  source_name: string | null;
  source_url: string | null;
  deep_link: string | null;
};

export type CalendarFilterValue = 'all' | 'upcoming' | 'done';

export const FILTERS: { value: CalendarFilterValue; label: string }[] = [
  { value: 'all', label: 'Todas' },
  { value: 'upcoming', label: 'Próximas' },
  { value: 'done', label: 'Realizadas' },
];

export function isDone(event: CalendarEvent): boolean {
  return event.status === 'COMPLETED';
}

export function isUpcoming(event: CalendarEvent, todayIso: string): boolean {
  return !isDone(event) && event.starts_at.slice(0, 10) >= todayIso;
}

export function matchesFilter(
  event: CalendarEvent,
  filter: CalendarFilterValue,
  todayIso: string,
): boolean {
  if (filter === 'upcoming') return isUpcoming(event, todayIso);
  if (filter === 'done') return isDone(event);
  return true;
}

export function eventStatusLabel(event: Pick<CalendarEvent, 'status'>): 'Realizada' | 'Próxima' {
  return event.status === 'COMPLETED' ? 'Realizada' : 'Próxima';
}

export function formatEventTime(startsAt: string): string | null {
  const match = /T(\d{2}):(\d{2})/.exec(startsAt);
  return match ? `${match[1]}:${match[2]}` : null;
}
