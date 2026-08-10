import { useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';

type Process = {
  id: string;
  code: string;
  name: string;
  year: number;
  election_date: string;
  status: string;
  is_final: boolean;
};
type Contest = {
  id: string;
  name: string;
  office_type: string;
  vote_method: string;
  canton_id: number | null;
};
type Parish = { id: number; canton_id: number; dpa_code: string; name: string; is_active: boolean };
type Canton = { id: number; name: string; dpa_code: string };
type Geography = {
  id: string;
  level: string;
  external_code: string;
  name: string;
  parish_id: number | null;
  canton_id: number | null;
  is_mapped: boolean;
};
type Turnout = {
  id: string;
  electoral_geography_id: string;
  aggregation_level: string;
  registered_voters: number;
  ballots_cast: number;
  absentee_count: number;
  valid_votes: number;
  blank_votes: number;
  null_votes: number;
};
type Candidate = {
  id: string;
  external_code: string;
  full_name: string;
  display_name?: string | null;
  list_number?: string | null;
};
type Organization = {
  id: string;
  name: string;
  short_name?: string | null;
  list_number?: string | null;
};
type CandidateResult = {
  candidate: Candidate;
  organization: Organization | null;
  votes: number;
  geography_id: string | null;
  geography_code: string | null;
  geography_name: string | null;
  geography_level: string | null;
};

type ParishRow = {
  geography: Geography;
  parish: Parish | undefined;
  turnout: Turnout | undefined;
  results: CandidateResult[];
};
type CandidateTotal = {
  candidate: Candidate;
  organization: Organization | null;
  votes: number;
  percentage: number;
};

const numberFormatter = new Intl.NumberFormat('es-EC', { maximumFractionDigits: 0 });
const percentFormatter = new Intl.NumberFormat('es-EC', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const number = (value: number) => numberFormatter.format(value);
const percent = (value: number | null) =>
  value === null || !Number.isFinite(value) ? '—' : `${percentFormatter.format(value)} %`;
const rate = (numerator: number, denominator: number) =>
  denominator ? (numerator * 100) / denominator : null;

function kpis(turnouts: Turnout[]) {
  const registered = turnouts.reduce((sum, row) => sum + row.registered_voters, 0);
  const ballots = turnouts.reduce((sum, row) => sum + row.ballots_cast, 0);
  const valid = turnouts.reduce((sum, row) => sum + row.valid_votes, 0);
  const blank = turnouts.reduce((sum, row) => sum + row.blank_votes, 0);
  const nullVotes = turnouts.reduce((sum, row) => sum + row.null_votes, 0);
  return {
    registered,
    ballots,
    absentee: registered - ballots,
    participation: rate(ballots, registered),
    valid,
    blank,
    nullVotes,
  };
}

function candidateTotals(rows: CandidateResult[], voteMethod: string): CandidateTotal[] {
  const totals = new Map<
    string,
    { candidate: Candidate; organization: Organization | null; votes: number }
  >();
  rows.forEach((row) => {
    const current = totals.get(row.candidate.id);
    totals.set(row.candidate.id, {
      candidate: row.candidate,
      organization: row.organization,
      votes: (current?.votes ?? 0) + row.votes,
    });
  });
  const items = [...totals.values()].sort((left, right) => right.votes - left.votes);
  const denominator = items.reduce((sum, item) => sum + item.votes, 0);
  return items.map((item) => ({
    ...item,
    percentage: voteMethod === 'SINGLE_CHOICE' ? (item.votes * 100) / denominator : 0,
  }));
}

function organizationLabel(organization: Organization | null) {
  if (!organization) return 'Organización no indicada';
  return organization.short_name || organization.name;
}

function candidateLabel(candidate: Candidate) {
  return candidate.display_name || candidate.full_name;
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h2" sx={{ mt: 0.5 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

function TurnoutBlock({ data }: { data: Turnout | undefined }) {
  if (!data) return <Alert severity="warning">No existe participación para esta parroquia.</Alert>;
  return (
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Electores" value={number(data.registered_voters)} />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Sufragantes" value={number(data.ballots_cast)} />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard
          label="Participación"
          value={percent(rate(data.ballots_cast, data.registered_voters))}
        />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Ausentismo" value={number(data.absentee_count)} />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Votos válidos" value={number(data.valid_votes)} />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Blancos" value={number(data.blank_votes)} />
      </Grid>
      <Grid size={{ xs: 6, md: 2.4 }}>
        <KpiCard label="Nulos" value={number(data.null_votes)} />
      </Grid>
    </Grid>
  );
}

function CandidateTable({ rows, voteMethod }: { rows: CandidateResult[]; voteMethod: string }) {
  const totals = candidateTotals(rows, voteMethod);
  if (!totals.length) return <EmptyState detail="No existen resultados por candidatura." />;
  return (
    <Table size="small" aria-label="Resultados por candidatura">
      <TableHead>
        <TableRow>
          <TableCell>Posición</TableCell>
          <TableCell>Candidato</TableCell>
          <TableCell>Organización</TableCell>
          <TableCell>Lista</TableCell>
          <TableCell align="right">Votos</TableCell>
          <TableCell align="right">%</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {totals.map((row, index) => (
          <TableRow key={row.candidate.id}>
            <TableCell>{index + 1}</TableCell>
            <TableCell>
              <Typography fontWeight={700}>{candidateLabel(row.candidate)}</Typography>
              {row.candidate.display_name &&
                row.candidate.display_name !== row.candidate.full_name && (
                  <Typography variant="caption" color="text.secondary">
                    {row.candidate.full_name}
                  </Typography>
                )}
            </TableCell>
            <TableCell>{organizationLabel(row.organization)}</TableCell>
            <TableCell>
              {row.organization?.list_number || row.candidate.list_number || '—'}
            </TableCell>
            <TableCell align="right">{number(row.votes)}</TableCell>
            <TableCell align="right">{percent(row.percentage)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function WinnerCard({
  rows,
  voteMethod,
  final,
}: {
  rows: CandidateResult[];
  voteMethod: string;
  final: boolean;
}) {
  const totals = candidateTotals(rows, voteMethod);
  const winner = totals[0];
  const second = totals[1];
  if (!winner) return null;
  const margin = winner.votes - (second?.votes ?? 0);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="overline" color="text.secondary">
        {final ? 'Ganador oficial histórico' : 'Resultado histórico destacado'}
      </Typography>
      <Typography variant="h2">{candidateLabel(winner.candidate)}</Typography>
      <Typography>
        {organizationLabel(winner.organization)} · {number(winner.votes)} votos ·{' '}
        {percent(winner.percentage)}
      </Typography>
      <Typography color="text.secondary">
        Diferencia con segundo lugar: {number(margin)} votos (
        {percent(
          rate(
            margin,
            totals.reduce((sum, row) => sum + row.votes, 0),
          ),
        )}
        )
      </Typography>
    </Paper>
  );
}

function DifferenceWarning({
  turnout,
  results,
}: {
  turnout: Turnout | undefined;
  results: CandidateResult[];
}) {
  if (!turnout) return null;
  const difference = turnout.valid_votes - results.reduce((sum, row) => sum + row.votes, 0);
  if (!difference) return null;
  return (
    <Alert severity="warning" variant="outlined">
      Los votos válidos registrados difieren en {number(Math.abs(difference))} de la suma de
      resultados por candidatura.
    </Alert>
  );
}

export default function ElectoralPage() {
  const [processId, setProcessId] = useState('');
  const [contestId, setContestId] = useState('');
  const [parishId, setParishId] = useState('');
  const processes = useQuery({
    queryKey: ['electoral-processes'],
    queryFn: () => apiRequest<Process[]>('/electoral-processes'),
  });
  const contests = useQuery({
    queryKey: ['electoral-contests', processId],
    queryFn: () => apiRequest<Contest[]>(`/electoral-processes/${processId}/contests`),
    enabled: !!processId,
  });
  useEffect(() => {
    if (!processId && processes.data?.length) setProcessId(processes.data[0].id);
  }, [processId, processes.data]);
  useEffect(() => {
    if (processId && !contestId && contests.data?.length) setContestId(contests.data[0].id);
  }, [contestId, contests.data, processId]);
  const selectedContest = contests.data?.find((contest) => contest.id === contestId);
  const geographies = useQuery({
    queryKey: ['electoral-geographies', processId, selectedContest?.canton_id],
    queryFn: () =>
      apiRequest<Geography[]>(
        `/electoral-processes/${processId}/geographies?aggregation_level=PARISH`,
      ),
    enabled: !!selectedContest,
  });
  const parishes = useQuery({
    queryKey: ['parishes', selectedContest?.canton_id],
    queryFn: () => apiRequest<Parish[]>(`/parishes?canton_id=${selectedContest!.canton_id}`),
    enabled: !!selectedContest?.canton_id,
  });
  const canton = useQuery({
    queryKey: ['canton', selectedContest?.canton_id],
    queryFn: () => apiRequest<Canton>(`/cantons/${selectedContest!.canton_id}`),
    enabled: !!selectedContest?.canton_id,
  });
  const turnout = useQuery({
    queryKey: ['turnout', processId, contestId],
    queryFn: () =>
      apiRequest<Turnout[]>(
        `/electoral-processes/${processId}/contests/${contestId}/turnout?aggregation_level=PARISH`,
      ),
    enabled: !!contestId,
  });
  const results = useQuery({
    queryKey: ['candidate-results', processId, contestId],
    queryFn: () =>
      apiRequest<CandidateResult[]>(
        `/electoral-processes/${processId}/contests/${contestId}/candidate-results?aggregation_level=PARISH`,
      ),
    enabled: !!contestId,
  });
  const selectedProcess = processes.data?.find((process) => process.id === processId);
  const rows = useMemo<ParishRow[]>(() => {
    if (!geographies.data) return [];
    const parishMap = new Map((parishes.data ?? []).map((parish) => [parish.id, parish]));
    const turnoutMap = new Map(
      (turnout.data ?? []).map((item) => [item.electoral_geography_id, item]),
    );
    return geographies.data
      .filter(
        (geography) =>
          geography.level === 'PARISH' && geography.canton_id === selectedContest?.canton_id,
      )
      .filter(
        (geography) =>
          !parishId ||
          (parishId.startsWith('geo:')
            ? geography.id === parishId.slice(4)
            : String(geography.parish_id) === parishId.replace(/^parish:/, '')),
      )
      .map((geography) => ({
        geography,
        parish: geography.parish_id ? parishMap.get(geography.parish_id) : undefined,
        turnout: turnoutMap.get(geography.id),
        results: (results.data ?? []).filter((result) => result.geography_id === geography.id),
      }))
      .sort((left, right) =>
        left.geography.external_code.localeCompare(right.geography.external_code),
      );
  }, [
    geographies.data,
    parishId,
    parishes.data,
    results.data,
    selectedContest?.canton_id,
    turnout.data,
  ]);
  const allRows = useMemo(() => {
    if (!geographies.data) return [];
    const parishMap = new Map((parishes.data ?? []).map((parish) => [parish.id, parish]));
    const turnoutMap = new Map(
      (turnout.data ?? []).map((item) => [item.electoral_geography_id, item]),
    );
    return geographies.data
      .filter(
        (geography) =>
          geography.level === 'PARISH' && geography.canton_id === selectedContest?.canton_id,
      )
      .map((geography) => ({
        geography,
        parish: geography.parish_id ? parishMap.get(geography.parish_id) : undefined,
        turnout: turnoutMap.get(geography.id),
        results: (results.data ?? []).filter((result) => result.geography_id === geography.id),
      }))
      .sort((left, right) =>
        left.geography.external_code.localeCompare(right.geography.external_code),
      );
  }, [geographies.data, parishes.data, results.data, selectedContest?.canton_id, turnout.data]);
  const aggregateTurnout = kpis(allRows.flatMap((row) => (row.turnout ? [row.turnout] : [])));
  const aggregateResults = allRows.flatMap((row) => row.results);
  const cantonCandidates = candidateTotals(
    aggregateResults,
    selectedContest?.vote_method ?? 'SINGLE_CHOICE',
  );
  const chartData = cantonCandidates.map((row) => ({
    name: candidateLabel(row.candidate),
    votos: row.votes,
  }));
  const visibleResults = rows.flatMap((row) => row.results);
  const parishOptions = allRows.map((row) => ({
    id: row.parish?.id ?? row.geography.parish_id,
    value: row.parish?.id ? `parish:${row.parish.id}` : `geo:${row.geography.id}`,
    name: row.parish?.name,
    code: row.parish?.dpa_code ?? row.geography.external_code,
  }));
  const loadingDetail =
    !!contestId &&
    (geographies.isLoading ||
      parishes.isLoading ||
      canton.isLoading ||
      turnout.isLoading ||
      results.isLoading);

  if (processes.isLoading) return <LoadingSkeleton />;
  if (processes.isError) return <ErrorState retry={() => processes.refetch()} />;
  return (
    <>
      <PageHeader
        title="Datos electorales"
        description="Resultados históricos oficiales, sin predicciones ni territorios favorables."
      />
      <Stack direction={{ xs: 'column', md: 'row' }} gap={2} mb={3}>
        <TextField
          select
          label="Proceso"
          value={processId}
          onChange={(event) => {
            setProcessId(event.target.value);
            setContestId('');
            setParishId('');
          }}
          sx={{ minWidth: 280 }}
        >
          <MenuItem value="">Seleccione</MenuItem>
          {processes.data?.map((process) => (
            <MenuItem key={process.id} value={process.id}>
              {process.name} · {formatDateOnly(process.election_date)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Contienda"
          value={contestId}
          onChange={(event) => {
            setContestId(event.target.value);
            setParishId('');
          }}
          sx={{ minWidth: 280 }}
          disabled={!processId}
        >
          <MenuItem value="">Seleccione</MenuItem>
          {contests.data?.map((contest) => (
            <MenuItem key={contest.id} value={contest.id}>
              {contest.name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Parroquia"
          value={parishId}
          onChange={(event) => setParishId(event.target.value)}
          sx={{ minWidth: 280 }}
          disabled={!contestId || geographies.isLoading}
        >
          <MenuItem value="">Todas</MenuItem>
          {parishOptions.map((parish) => (
            <MenuItem key={parish.value} value={parish.value}>
              {parish.name || `Parroquia sin mapear · DPA ${parish.code}`}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {!contestId ? (
        <EmptyState detail="Seleccione un proceso y una contienda." />
      ) : loadingDetail ? (
        <LoadingSkeleton />
      ) : (
        <Stack spacing={3}>
          <Typography variant="h1">
            {parishId
              ? `Datos de ${rows[0]?.parish?.name ?? `Parroquia sin mapear · DPA ${rows[0]?.geography.external_code ?? ''}`}`
              : `Resumen cantonal — ${canton.data?.name ?? 'Cantón seleccionado'}`}
          </Typography>
          {parishId ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="h2">Participación de la parroquia</Typography>
              <TurnoutBlock data={rows[0]?.turnout} />
            </Paper>
          ) : (
            <Grid container spacing={1.5}>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard
                  label="Electores registrados"
                  value={number(aggregateTurnout.registered)}
                />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Sufragantes" value={number(aggregateTurnout.ballots)} />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Participación" value={percent(aggregateTurnout.participation)} />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Ausentismo" value={number(aggregateTurnout.absentee)} />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Votos válidos" value={number(aggregateTurnout.valid)} />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Blancos" value={number(aggregateTurnout.blank)} />
              </Grid>
              <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                <KpiCard label="Nulos" value={number(aggregateTurnout.nullVotes)} />
              </Grid>
            </Grid>
          )}
          <WinnerCard
            rows={visibleResults}
            voteMethod={selectedContest?.vote_method ?? 'SINGLE_CHOICE'}
            final={!!selectedProcess?.is_final}
          />
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h2">
              {parishId ? 'Resultados de la parroquia' : 'Resultados cantonales'}
            </Typography>
            {!parishId && chartData.length > 0 && (
              <Box sx={{ width: '100%', height: Math.max(220, chartData.length * 52), mt: 2 }}>
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                  <BarChart data={chartData} layout="vertical" margin={{ left: 24, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tickFormatter={(value) => number(value)} />
                    <YAxis type="category" dataKey="name" width={130} />
                    <Tooltip formatter={(value: number) => number(value)} />
                    <Bar dataKey="votos" fill="#1565c0" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            )}
            <CandidateTable
              rows={visibleResults}
              voteMethod={selectedContest?.vote_method ?? 'SINGLE_CHOICE'}
            />
          </Paper>
          {!parishId && (
            <Stack spacing={1}>
              <Typography variant="h2">Resultados por parroquia</Typography>
              {rows.map((row) => {
                const title =
                  row.parish?.name ?? `Parroquia sin mapear · DPA ${row.geography.external_code}`;
                return (
                  <Accordion key={row.geography.id}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Stack>
                        <Typography fontWeight={700}>{title}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          Nivel {row.geography.level} · DPA{' '}
                          {row.parish?.dpa_code ?? row.geography.external_code}
                        </Typography>
                      </Stack>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={2}>
                        <TurnoutBlock data={row.turnout} />
                        <DifferenceWarning turnout={row.turnout} results={row.results} />
                        <CandidateTable
                          rows={row.results}
                          voteMethod={selectedContest?.vote_method ?? 'SINGLE_CHOICE'}
                        />
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Stack>
          )}
          {parishId && <DifferenceWarning turnout={rows[0]?.turnout} results={visibleResults} />}
        </Stack>
      )}
    </>
  );
}
