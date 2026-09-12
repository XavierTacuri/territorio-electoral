import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Grid,
  Paper,
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
import { useAuth } from '../../auth/AuthProvider';
import { isCoordinatorOnly } from '../../auth/permissions';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { TerritorialProfileContent } from './TerritorialProfileContent';
import {
  Card,
  Metric,
  integer,
  percent,
  type Analysis,
  type Operation,
  type Parish,
} from './territoryShared';

export default function TerritorialIntelligencePage() {
  const { campaignId = '', parishId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isCoordinator = isCoordinatorOnly(user);
  const [comparison, setComparison] = useState<Parish[]>([]);
  const analysis = useQuery({
    queryKey: ['current-election-analysis', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<Analysis>(`/campaigns/${campaignId}/current-election/analysis`, { signal }),
    enabled: !!campaignId,
  });
  // Territory comparison is not part of the coordinator's experience (see
  // below), so its data source is never requested for that role.
  const operation = useQuery({
    queryKey: ['territory-operation-summary', campaignId],
    queryFn: ({ signal }) =>
      apiRequest<{ parishes: Operation[] }>(`/campaigns/${campaignId}/territories/summary`, {
        signal,
      }),
    enabled: !!campaignId && !isCoordinator,
    retry: 1,
  });
  const operationByParish = useMemo(
    () => new Map((operation.data?.parishes ?? []).map((item) => [item.parish_id, item])),
    [operation.data],
  );
  const assignedParishes = analysis.data?.parishes ?? [];
  // A coordinator with exactly one assigned parish never sees a selector:
  // Inteligencia Territorial goes straight to that parish's Expediente
  // Territorial, replacing history so "back" doesn't return to a page the
  // coordinator never meaningfully saw.
  useEffect(() => {
    if (isCoordinator && !parishId && assignedParishes.length === 1) {
      navigate(`/app/campaigns/${campaignId}/territories/${assignedParishes[0].parish_id}`, {
        replace: true,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCoordinator, campaignId, assignedParishes.length, parishId]);

  if (analysis.isLoading) return <LoadingSkeleton />;
  if (analysis.isError || !analysis.data)
    return (
      <ErrorState
        message="No fue posible cargar la inteligencia territorial."
        retry={() => void analysis.refetch()}
      />
    );
  const data = analysis.data;

  if (isCoordinator) {
    if (assignedParishes.length === 0) {
      return (
        <>
          <PageHeader title="INTELIGENCIA TERRITORIAL" />
          <EmptyState
            title="No tienes parroquias asignadas para esta campaña."
            detail="Solicita a tu Campaign Manager o Administrador que registre tu asignación territorial para poder consultar tu Expediente Territorial."
          />
        </>
      );
    }
    if (parishId) {
      return <TerritorialProfileContent campaignId={campaignId} parishId={parishId} />;
    }
    if (assignedParishes.length === 1) {
      // Redirecting via the effect above; render nothing but a loading state
      // in the meantime so the selector/comparison UI never flashes.
      return <LoadingSkeleton />;
    }
    return (
      <>
        <PageHeader
          title="INTELIGENCIA TERRITORIAL"
          description="Seleccione una de sus parroquias asignadas para abrir su Expediente Territorial."
        />
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Autocomplete
            options={assignedParishes}
            getOptionLabel={(item) => `${item.name} · DPA ${item.dpa_code}`}
            isOptionEqualToValue={(a, b) => a.parish_id === b.parish_id}
            onChange={(_, value) =>
              value && navigate(`/app/campaigns/${campaignId}/territories/${value.parish_id}`)
            }
            renderInput={(params) => (
              <TextField
                {...params}
                label="Seleccionar parroquia"
                placeholder="Buscar por nombre o DPA"
              />
            )}
          />
        </Paper>
      </>
    );
  }

  // Candidate/Campaign Manager: seleccionar una parroquia renderiza su
  // Expediente Territorial de inmediato, DEBAJO del mismo selector — sin
  // navegar a una pantalla distinta. El selector permanece visible (con la
  // parroquia activa como valor) para poder cambiar de parroquia sin
  // regresar; la URL sigue reflejando la parroquia seleccionada para que
  // refresh/back/forward/deep link funcionen igual que antes.
  const selectedParish = parishId
    ? (data.parishes.find((item) => String(item.parish_id) === parishId) ?? null)
    : null;

  const selector = (
    <Autocomplete
      options={data.parishes}
      value={selectedParish}
      // Seleccionar una parroquia actualiza de inmediato el Expediente
      // Territorial que se muestra debajo, sin paso intermedio de
      // confirmación ni botón "VER EXPEDIENTE" (§3-6). Limpiar la selección
      // vuelve a la vista comparativa, en la misma página.
      onChange={(_, value) =>
        navigate(
          value
            ? `/app/campaigns/${campaignId}/territories/${value.parish_id}`
            : `/app/campaigns/${campaignId}/territories`,
        )
      }
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
  );

  if (parishId) {
    return (
      <>
        <Typography variant="overline" color="text.secondary">
          INTELIGENCIA TERRITORIAL
        </Typography>
        <Paper variant="outlined" sx={{ p: 2, mb: 2, mt: 0.5 }}>
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
            <Grid size={{ xs: 12, md: 4 }}>{selector}</Grid>
          </Grid>
        </Paper>
        <TerritorialProfileContent campaignId={campaignId} parishId={parishId} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="INTELIGENCIA TERRITORIAL"
        description="Panorama comparado de las parroquias de la campaña. Seleccione una parroquia para abrir de inmediato su Expediente Territorial."
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
          <Grid size={{ xs: 12, md: 4 }}>{selector}</Grid>
        </Grid>
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
  // Comparación simplificada a exactamente 5 indicadores: electores
  // actuales, votantes esperados (proyección V1 ya persistida por el backend
  // — nunca recalculada aquí), población, actividades y necesidades. LOW/HIGH,
  // participación histórica, densidad, crecimiento y grupos etarios quedan
  // fuera de esta tabla (siguen disponibles en el Expediente Territorial).
  const metrics = (p: Parish): Record<string, number | undefined> => ({
    electores: p.registered_voters_current,
    votantes: p.projection?.expected_voters_central,
    poblacion: p.demographics.POP_TOTAL,
    actividades: operations.get(p.parish_id)?.activities ?? 0,
    necesidades: operations.get(p.parish_id)?.needs_open ?? 0,
  });
  const rows: [string, string, 'integer' | 'percent' | 'plain'][] = [
    ['Electores actuales', 'electores', 'integer'],
    ['Votantes esperados', 'votantes', 'integer'],
    ['Población', 'poblacion', 'integer'],
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
