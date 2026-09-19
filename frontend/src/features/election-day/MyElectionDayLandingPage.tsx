import { Button, Card, CardContent, Chip, Grid, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import {
  OPERATION_STATUS_LABELS,
  STAFF_TYPE_LABELS,
  type ElectionDayMyContextSummary,
} from './types';

export default function MyElectionDayLandingPage() {
  const contexts = useQuery({
    queryKey: ['election-day-my-contexts'],
    queryFn: () => apiRequest<ElectionDayMyContextSummary[]>('/election-day/my-contexts'),
  });

  if (contexts.isLoading) return <LoadingSkeleton />;
  if (contexts.isError) return <ErrorState retry={() => contexts.refetch()} />;

  const items = contexts.data ?? [];

  return (
    <>
      <PageHeader
        title="Mis jornadas electorales"
        description="Campañas donde tienes una asignación activa de personal de Jornada Electoral."
      />
      {items.length === 0 ? (
        <EmptyState
          title="No tienes ninguna jornada asignada todavía."
          detail="Cuando aceptes una invitación de personal de Jornada, aparecerá aquí."
        />
      ) : (
        <Grid container spacing={2}>
          {items.map((context) => (
            <Grid key={context.campaign_id} size={{ xs: 12, md: 6 }}>
              <Card variant="outlined">
                <CardContent>
                  <Typography component="h2" variant="h2" sx={{ mb: 0.5 }}>
                    {context.campaign_name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Fecha: {formatDateOnly(context.election_date)}
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
                    <Chip size="small" label={OPERATION_STATUS_LABELS[context.operation_status]} />
                    {context.staff_types.map((type) => (
                      <Chip
                        key={type}
                        size="small"
                        variant="outlined"
                        label={STAFF_TYPE_LABELS[type]}
                      />
                    ))}
                  </Stack>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {context.staff_types.includes('POLLING_PLACE_DELEGATE') && (
                      <Button
                        variant="contained"
                        component={RouterLink}
                        to={`/app/campaigns/${context.campaign_id}/election-day/my`}
                      >
                        MI JORNADA
                      </Button>
                    )}
                    {context.staff_types.includes('ACT_VALIDATOR') && (
                      <Button
                        variant="contained"
                        component={RouterLink}
                        to={`/app/campaigns/${context.campaign_id}/election-day/validation`}
                      >
                        VALIDACIÓN DE ACTAS
                      </Button>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </>
  );
}
