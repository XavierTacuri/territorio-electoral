import { Button, Card, CardContent, Chip, Grid, Stack, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { PageHeader } from '../components/layout/PageHeader';
import { EmptyState, ErrorState, LoadingSkeleton } from '../components/feedback/States';
import { formatDateOnly } from '../lib/dates';
type Props = {
  title: string;
  description: string;
  endpoint: (campaignId: string) => string;
  admin?: boolean;
  createLabel?: string;
};
function normalize(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  if (data && typeof data === 'object') {
    const object = data as Record<string, unknown>;
    if (Array.isArray(object.items)) return object.items as Record<string, unknown>[];
    return [object];
  }
  return [];
}
const label = (key: string) =>
  ({
    title: 'Título',
    name: 'Nombre',
    status: 'Estado',
    activity_date: 'Fecha',
    due_date: 'Vencimiento',
    event_date: 'Fecha',
    description: 'Descripción',
    severity: 'Severidad',
    code: 'Código',
  })[key] ?? key.replaceAll('_', ' ');
export default function ModulePage(props: Props) {
  const { campaignId = '' } = useParams();
  const path = props.endpoint(campaignId);
  const query = useQuery({
    queryKey: ['campaign', campaignId, path],
    queryFn: ({ signal }) => apiRequest<unknown>(path, { signal }),
    enabled: !!path,
  });
  const rows = normalize(query.data);
  return (
    <>
      <PageHeader
        title={props.title}
        description={props.description}
        action={
          props.createLabel && (
            <Button startIcon={<AddIcon />} variant="contained">
              {props.createLabel}
            </Button>
          )
        }
      />
      {query.isLoading ? (
        <LoadingSkeleton />
      ) : query.isError ? (
        <ErrorState retry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState />
      ) : (
        <Grid container spacing={2}>
          {rows.slice(0, 100).map((row, index) => (
            <Grid key={String(row.id ?? index)} size={{ xs: 12, md: 6, xl: 4 }}>
              <Card variant="outlined">
                <CardContent>
                  <Stack spacing={1}>
                    {Object.entries(row)
                      .filter(
                        ([key, value]) =>
                          value !== null &&
                          [
                            'title',
                            'name',
                            'status',
                            'activity_date',
                            'due_date',
                            'event_date',
                            'description',
                            'severity',
                            'code',
                          ].includes(key),
                      )
                      .slice(0, 6)
                      .map(([key, value]) => (
                        <Stack key={key} direction="row" gap={1} justifyContent="space-between">
                          <Typography color="text.secondary">{label(key)}</Typography>
                          {key.includes('date') ? (
                            <Typography>{formatDateOnly(String(value))}</Typography>
                          ) : key === 'status' || key === 'severity' ? (
                            <Chip size="small" label={String(value)} />
                          ) : (
                            <Typography textAlign="right">{String(value)}</Typography>
                          )}
                        </Stack>
                      ))}
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
