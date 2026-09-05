import { useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiRequest } from '../../api/client';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { ageKeys, Card, Metric, integer, percent, type Analysis, type Operation, type Parish } from './territoryShared';

export default function TerritorialIntelligencePage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const [comparison, setComparison] = useState<Parish[]>([]);
  const [chosen, setChosen] = useState<Parish | null>(null);
  const analysis = useQuery({
    queryKey: ['current-election-analysis', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`, { signal }),
    enabled: !!campaignId,
  });
  const operation = useQuery({
    queryKey: ['territory-operation-summary', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<{ parishes: Operation[] }>(`/campaigns/${campaignId}/territories/summary`, {
        signal,
      }),
    enabled: !!campaignId,
    retry: 1,
  });
  const operationByParish = useMemo(
    () => new Map((operation.data?.parishes ?? []).map((item) => [item.parish_id, item])),
    [operation.data],
  );
  if (analysis.isLoading) return <LoadingSkeleton />;
  if (analysis.isError || !analysis.data)
    return (
      <ErrorState
        message="No fue posible cargar la inteligencia territorial."
        retry={() => void analysis.refetch()}
      />
    );
  const data = analysis.data;
  const goToExpediente = (parish: Parish) =>
    navigate(`/app/campaigns/${campaignId}/territories/${parish.parish_id}`);
  return (
    <>
      <PageHeader
        title="INTELIGENCIA TERRITORIAL"
        description="Panorama comparado de las parroquias de la campaña. Seleccione una parroquia para abrir su Expediente Territorial."
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, md: 3 }}>
            <Metric label="CAMPAÑA" value={data.context.campaign_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 2 }}>
            <Metric label="CANTÓN" value={data.context.canton_name} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <Metric label="PROCESO" value={data.context.election_name} />
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <Autocomplete
              options={data.parishes}
              value={chosen}
              onChange={(_, value) => setChosen(value)}
              getOptionLabel={(item) => `${item.name} · DPA ${item.dpa_code}`}
              isOptionEqualToValue={(a, b) => a.parish_id === b.parish_id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Seleccionar parroquia"
                  placeholder="Buscar por nombre o DPA"
                />
              )}
            />
          </Grid>
        </Grid>
        {chosen && (
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            alignItems={{ sm: 'center' }}
            justifyContent="space-between"
            sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 2 }}
          >
            <Typography>
              {chosen.name} · Padrón {integer(chosen.registered_voters_current)} · Población{' '}
              {chosen.demographics.POP_TOTAL != null
                ? integer(chosen.demographics.POP_TOTAL)
                : 'Sin datos disponibles'}
            </Typography>
            <Button variant="contained" onClick={() => goToExpediente(chosen)}>
              VER EXPEDIENTE
            </Button>
          </Stack>
        )}
      </Paper>
      <Comparison
        parishes={data.parishes}
        selected={comparison}
        onChange={setComparison}
        operations={operationByParish}
      />
    </>
  );
}

function Comparison({
  parishes,
  selected,
  onChange,
  operations,
}: {
  parishes: Parish[];
  selected: Parish[];
  onChange: (value: Parish[]) => void;
  operations: Map<number, Operation>;
}) {
  const metrics = (p: Parish): Record<string, number | undefined> => ({
    electores: p.registered_voters_current,
    '2019': p.historical_2019?.turnout_rate ?? undefined,
    '2023': p.historical_2023?.turnout_rate ?? undefined,
    low: p.projection?.low,
    central: p.projection?.central,
    high: p.projection?.high,
    votantes: p.projection?.expected_voters_central,
    poblacion: p.demographics.POP_TOTAL,
    crecimiento: p.population_growth_2010_2022 ?? undefined,
    densidad: p.demographics.POPULATION_DENSITY ?? p.demographics.DENSITY,
    ...Object.fromEntries(
      ageKeys.map(([label, key]) => [
        label,
        (p.demographics[key] ?? 0) / (p.demographics.POP_TOTAL ?? 1),
      ]),
    ),
    actividades: operations.get(p.parish_id)?.activities ?? 0,
    necesidades: operations.get(p.parish_id)?.needs_open ?? 0,
  });
  const rows: [string, string, 'integer' | 'percent' | 'plain'][] = [
    ['Electores actuales', 'electores', 'integer'],
    ['Participación 2019', '2019', 'percent'],
    ['Participación 2023', '2023', 'percent'],
    ['LOW', 'low', 'percent'],
    ['CENTRAL', 'central', 'percent'],
    ['HIGH', 'high', 'percent'],
    ['Votantes centrales', 'votantes', 'integer'],
    ['Población', 'poblacion', 'integer'],
    ['Crecimiento', 'crecimiento', 'percent'],
    ['Densidad', 'densidad', 'plain'],
    ...ageKeys.map(([label]) => [`${label} %`, label, 'percent'] as [string, string, 'percent']),
    ['Actividades', 'actividades', 'integer'],
    ['Necesidades', 'necesidades', 'integer'],
  ];
  return (
    <Card title="COMPARAR TERRITORIOS">
      <Alert severity="info" sx={{ mb: 2 }}>
        Comparación descriptiva. No constituye un ranking ni una recomendación de prioridad
        electoral.
      </Alert>
      <Autocomplete
        multiple
        options={parishes}
        value={selected}
        limitTags={3}
        getOptionLabel={(p) => `${p.name} · ${p.dpa_code}`}
        isOptionEqualToValue={(a, b) => a.parish_id === b.parish_id}
        getOptionDisabled={(option) =>
          selected.length >= 3 && !selected.some((p) => p.parish_id === option.parish_id)
        }
        onChange={(_, value) => onChange(value.slice(0, 3))}
        renderInput={(params) => (
          <TextField {...params} label="Seleccione entre 2 y 3 parroquias" />
        )}
      />
      {selected.length < 2 ? (
        <Alert severity="info" sx={{ mt: 2 }}>
          Seleccione al menos dos parroquias.
        </Alert>
      ) : (
        <>
          <TableContainer sx={{ mt: 2, maxWidth: '100%', overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 650 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Indicador</TableCell>
                  {selected.map((p) => (
                    <TableCell key={p.parish_id}>{p.name}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map(([label, key, kind]) => (
                  <TableRow key={label}>
                    <TableCell>{label}</TableCell>
                    {selected.map((p) => {
                      const value = metrics(p)[key] as number | undefined;
                      return (
                        <TableCell key={p.parish_id}>
                          {value == null
                            ? '—'
                            : kind === 'percent'
                              ? percent(value)
                              : kind === 'integer'
                                ? integer(value)
                                : String(value)}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Box sx={{ height: 240, minWidth: 0, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <BarChart
                data={selected.map((p) => ({
                  name: p.name,
                  Electores: p.registered_voters_current,
                  Población: p.demographics.POP_TOTAL ?? 0,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Electores" fill="#1565c0" />
                <Bar dataKey="Población" fill="#607d8b" />
              </BarChart>
            </ResponsiveContainer>
          </Box>
        </>
      )}
    </Card>
  );
}
