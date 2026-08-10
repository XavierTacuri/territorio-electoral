import { useState } from 'react';
import { MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
type Indicator = { id: string; code: string; name: string; unit: string; category: string };
type Observation = {
  id: string;
  reference_year: number;
  value: string;
  geography_level: string;
  canton_id?: number;
  parish_id?: number;
  is_official: boolean;
};
export default function DemographicsPage() {
  const [indicator, setIndicator] = useState('');
  const [year, setYear] = useState('');
  const indicators = useQuery({
    queryKey: ['demographic-indicators'],
    queryFn: () => apiRequest<Indicator[]>('/demographic-indicators'),
  });
  const observations = useQuery({
    queryKey: ['demographic-observations', indicator, year],
    queryFn: () =>
      apiRequest<Observation[]>(
        `/demographic-observations?indicator_id=${indicator}${year ? '&reference_year=' + year : ''}`,
      ),
    enabled: !!indicator,
  });
  if (indicators.isLoading) return <LoadingSkeleton />;
  if (indicators.isError) return <ErrorState retry={() => indicators.refetch()} />;
  const selected = indicators.data?.find((x) => x.id === indicator);
  return (
    <>
      <PageHeader
        title="Demografía"
        description="Indicadores oficiales agregados. No se correlacionan automáticamente con preferencias electorales."
      />
      <Stack direction={{ xs: 'column', md: 'row' }} gap={2} mb={3}>
        <TextField
          select
          label="Indicador"
          value={indicator}
          onChange={(e) => setIndicator(e.target.value)}
          sx={{ minWidth: 300 }}
        >
          <MenuItem value="">Seleccione</MenuItem>
          {indicators.data?.map((x) => (
            <MenuItem key={x.id} value={x.id}>
              {x.name} ({x.unit})
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Año"
          type="number"
          value={year}
          onChange={(e) => setYear(e.target.value)}
          inputProps={{ min: 1900, max: 2200 }}
        />
      </Stack>
      {!indicator ? (
        <EmptyState detail="Seleccione un indicador." />
      ) : observations.data?.length ? (
        <Stack spacing={1}>
          {observations.data.map((x) => (
            <Paper key={x.id} variant="outlined" sx={{ p: 2 }}>
              <Typography variant="h2">
                {x.value} {selected?.unit}
              </Typography>
              <Typography>
                {x.geography_level} · {x.reference_year} ·{' '}
                {x.is_official ? 'Fuente oficial' : 'Dato no oficial'}
              </Typography>
            </Paper>
          ))}
        </Stack>
      ) : observations.isLoading ? (
        <LoadingSkeleton />
      ) : observations.isError ? (
        <ErrorState retry={() => observations.refetch()} />
      ) : (
        <EmptyState detail="No hay observaciones para los filtros elegidos." />
      )}
    </>
  );
}
