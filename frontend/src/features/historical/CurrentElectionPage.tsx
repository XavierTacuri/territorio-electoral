import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiRequest } from '../../api/client';
import { downloadReport } from '../../api/downloads';
import { useCampaign } from '../../app/CampaignProvider';
import { PageHeader } from '../../components/layout/PageHeader';
import { formatDateOnly } from '../../lib/dates';
import { todayDateOnly } from '../../lib/dates';
import { formatIntegerEsEc, formatPercentEsEc } from '../../lib/formatEsEc';
import { CurrentElectionMap } from './CurrentElectionMap';

type Historical = { registered_voters: number; ballots_cast: number; turnout_rate: number | null };
type ParishRow = {
  parish_id: number;
  name: string;
  dpa_code: string;
  registered_voters_current: number;
  male_voters: number | null;
  female_voters: number | null;
  juntas: number | null;
  historical_2019?: Historical;
  historical_2023?: Historical;
  projection?: {
    low: number;
    central: number;
    high: number;
    expected_voters_low: number;
    expected_voters_central: number;
    expected_voters_high: number;
  };
  data_quality_status: string;
  demographics: Record<string, number>;
};
type Analysis = {
  snapshot: {
    id: string;
    snapshot_date: string;
    registered_voters: number;
    male_voters: number;
    female_voters: number;
    juntas: number;
  };
  historical: Record<string, Historical>;
  projection: {
    model_code: string;
    model_version: string;
    parameters: Record<string, string>;
    expected_voters_low: number;
    expected_voters_central: number;
    expected_voters_high: number;
  };
  warnings: { code: string; message: string }[];
  parishes: ParishRow[];
  demographics: { year: number; parishes: ParishRow[] };
};

const integer = formatIntegerEsEc;
const pct = formatPercentEsEc;
const date = (value?: string) => formatDateOnly(value);
const quality = (value: string) =>
  ({ HIGH: 'Alta', MEDIUM: 'Media', LOW: 'Baja', INSUFFICIENT_DATA: 'Datos insuficientes' })[
    value
  ] ?? value;

export default function CurrentElectionPage() {
  const { campaignId } = useParams();
  const { active } = useCampaign();
  const id = campaignId ?? active?.id ?? '';
  const [detail, setDetail] = useState<ParishRow | null>(null);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [sort, setSort] = useState('registered_voters_current');
  const [reportStatus, setReportStatus] = useState('');
  const [generatedFormat, setGeneratedFormat] = useState<'PDF' | 'XLSX' | null>(null);
  const analysis = useQuery({
    queryKey: ['current-election-analysis', id],
    queryFn: () => apiRequest<Analysis>(`/campaigns/${id}/current-election/analysis`),
    enabled: !!id,
  });
  const data = analysis.data;
  const value = (row: ParishRow) =>
    sort === 'name'
      ? row.name
      : sort === 'central'
        ? (row.projection?.central ?? 0)
        : sort === 'expected_voters_central'
          ? (row.projection?.expected_voters_central ?? 0)
          : sort === 'historical_2019'
            ? (row.historical_2019?.turnout_rate ?? 0)
            : sort === 'historical_2023'
              ? (row.historical_2023?.turnout_rate ?? 0)
              : row.registered_voters_current;
  const sorted = [...(data?.parishes ?? [])].sort((a, b) =>
    typeof value(a) === 'string'
      ? String(value(a)).localeCompare(String(value(b)))
      : Number(value(b)) - Number(value(a)),
  );
  if (analysis.isLoading) return <Typography>Cargando auditoría…</Typography>;
  if (analysis.isError || !data)
    return <Alert severity="info">No existe una corrida completa de elección actual.</Alert>;
  const current = data.snapshot;
  const central = data.projection.expected_voters_central;
  const scenarios = [
    [
      'Escenario bajo',
      data.projection.expected_voters_low,
      current.registered_voters
        ? data.projection.expected_voters_low / current.registered_voters
        : 0,
    ],
    ['Escenario central', central, central / current.registered_voters],
    [
      'Escenario alto',
      data.projection.expected_voters_high,
      current.registered_voters
        ? data.projection.expected_voters_high / current.registered_voters
        : 0,
    ],
  ] as const;
  const registration = [
    { year: '2019', voters: data.historical['2019']?.registered_voters ?? 0 },
    { year: '2023', voters: data.historical['2023']?.registered_voters ?? 0 },
    { year: '2026', voters: current.registered_voters },
  ];
  const registrationChanges = registration.slice(1).map((item, index) => ({
    label: `${registration[index].year} → ${item.year}`,
    absolute: item.voters - registration[index].voters,
    percent: registration[index].voters
      ? (item.voters - registration[index].voters) / registration[index].voters
      : 0,
  }));
  const age = ['AGE_0_14', 'AGE_15_29', 'AGE_30_44', 'AGE_45_64', 'AGE_65_PLUS'];
  const cantonDemographics = age.map((key) => ({
    name:
      (
        {
          AGE_0_14: '0–14',
          AGE_15_29: '15–29',
          AGE_30_44: '30–44',
          AGE_45_64: '45–64',
          AGE_65_PLUS: '65+',
        } as Record<string, string>
      )[key] ?? key,
    value: data.parishes.reduce((sum, row) => sum + (row.demographics[key] ?? 0), 0),
  }));
  const cantonPopulation = data.parishes.reduce(
    (sum, row) => sum + (row.demographics.POP_TOTAL ?? 0),
    0,
  );
  const cantonMale = data.parishes.reduce((sum, row) => sum + (row.demographics.POP_MALE ?? 0), 0);
  const cantonFemale = data.parishes.reduce(
    (sum, row) => sum + (row.demographics.POP_FEMALE ?? 0),
    0,
  );
  return (
    <>
      <PageHeader
        title="Elección actual"
        description="Análisis agregado, explicable y auditable de participación. No predice candidatos, ganadores ni intención individual."
      />
      <Stack spacing={3}>
        {data.warnings.map((warning) => (
          <Alert key={warning.code} severity="warning">
            <strong>{warning.code}</strong>: {warning.message}
          </Alert>
        ))}
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">
            REGISTRO ELECTORAL ACTUAL{' '}
            <Typography component="span" variant="caption">
              OBSERVADO · CNE
            </Typography>
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {[
              ['Electores', current.registered_voters],
              ['Hombres', current.male_voters],
              ['Mujeres', current.female_voters],
              ['Juntas', current.juntas],
            ].map(([label, value]) => (
              <Grid key={String(label)} size={{ xs: 6, md: 3 }}>
                <Typography variant="caption">{label}</Typography>
                <Typography variant="h2">{integer(Number(value))}</Typography>
              </Grid>
            ))}
          </Grid>
          <Typography>
            Hombres: {pct(current.male_voters / current.registered_voters)} · Mujeres:{' '}
            {pct(current.female_voters / current.registered_voters)}
          </Typography>
          <Typography>Fecha del corte: {date(current.snapshot_date)}</Typography>
        </Paper>
        <CurrentElectionMap
          campaignId={id}
          parishes={data.parishes}
          onSelect={(parishId) =>
            setDetail(data.parishes.find((row) => row.parish_id === parishId) ?? null)
          }
        />
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">
            PARTICIPACIÓN HISTÓRICA{' '}
            <Typography component="span" variant="caption">
              OBSERVADO · OFICIAL CNE
            </Typography>
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {['2019', '2023'].map((year) => (
              <Grid key={year} size={{ xs: 12, md: 6 }}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="h3">{year}</Typography>
                  <Typography>
                    Electores: {integer(data.historical[year]?.registered_voters ?? 0)}
                  </Typography>
                  <Typography>
                    Sufragantes: {integer(data.historical[year]?.ballots_cast ?? 0)}
                  </Typography>
                  <Typography>Participación: {pct(data.historical[year]?.turnout_rate)}</Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">EVOLUCIÓN DEL REGISTRO ELECTORAL</Typography>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={registration}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="year" />
              <YAxis />
              <Tooltip />
              <Line dataKey="voters" name="Electores habilitados" stroke="#1565c0" />
            </LineChart>
          </ResponsiveContainer>
          {registrationChanges.map((change) => (
            <Typography key={change.label}>
              {change.label}: {change.absolute > 0 ? '+' : ''}
              {integer(change.absolute)} ({pct(change.percent)})
            </Typography>
          ))}
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="h2">
              PROYECCIÓN DE PARTICIPACIÓN{' '}
              <Typography component="span" variant="caption">
                PROYECTADO · TERRITORIO ELECTORAL
              </Typography>
            </Typography>
          </Stack>
          <Typography>
            Modelo: {data.projection.model_code} · Versión {data.projection.model_version}
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {scenarios.map(([label, voters, rate]) => (
              <Grid key={label} size={{ xs: 12, md: 4 }}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Typography>{label}</Typography>
                  <Typography variant="h2">{integer(voters)}</Typography>
                  <Typography>{pct(rate)}</Typography>
                  <Typography>
                    {label === 'Escenario central'
                      ? 'Referencia central'
                      : `${voters - central > 0 ? '+' : ''}${integer(voters - central)} frente al central`}
                  </Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>
          <Typography sx={{ mt: 2 }}>
            Esta estimación proyecta participación electoral agregada. No estima intención de voto,
            resultados por candidato ni probabilidad de victoria.
          </Typography>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">CONTEXTO TERRITORIAL · INEC CPV 2022</Typography>
          <Typography>
            Contexto territorial. No interviene en la fórmula de participación V1.
          </Typography>
          <Typography>
            Población censada: {integer(cantonPopulation)} · Hombres: {integer(cantonMale)} ·
            Mujeres: {integer(cantonFemale)}
          </Typography>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={cantonDemographics}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#607d8b" />
            </BarChart>
          </ResponsiveContainer>
        </Paper>
        <Paper sx={{ p: 3, overflow: 'auto' }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="h2">POR PARROQUIA</Typography>
            <Select size="small" value={sort} onChange={(event) => setSort(event.target.value)}>
              <MenuItem value="registered_voters_current">Electores</MenuItem>
              <MenuItem value="name">Nombre</MenuItem>
              <MenuItem value="historical_2019">Tasa 2019</MenuItem>
              <MenuItem value="historical_2023">Tasa 2023</MenuItem>
              <MenuItem value="central">Central</MenuItem>
              <MenuItem value="expected_voters_central">Votantes centrales</MenuItem>
            </Select>
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                {[
                  ['name', 'Parroquia'],
                  ['registered_voters_current', 'Electores actuales'],
                  ['historical_2019', 'Participación 2019'],
                  ['historical_2023', 'Participación 2023'],
                  ['low', 'Baja'],
                  ['central', 'Central'],
                  ['high', 'Alta'],
                  ['expected_voters_central', 'Votantes central'],
                ].map(([key, label]) => (
                  <TableCell key={key}>
                    <TableSortLabel active={sort === key} onClick={() => setSort(key)}>
                      {label}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell>Calidad</TableCell>
                <TableCell>Detalles</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((row) => (
                <TableRow key={row.parish_id}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{integer(row.registered_voters_current)}</TableCell>
                  <TableCell>{pct(row.historical_2019?.turnout_rate)}</TableCell>
                  <TableCell>{pct(row.historical_2023?.turnout_rate)}</TableCell>
                  <TableCell>{pct(row.projection?.low)}</TableCell>
                  <TableCell>{pct(row.projection?.central)}</TableCell>
                  <TableCell>{pct(row.projection?.high)}</TableCell>
                  <TableCell>{integer(row.projection?.expected_voters_central ?? 0)}</TableCell>
                  <TableCell>
                    {quality(row.data_quality_status)}{' '}
                    <Button size="small" onClick={() => setDetail(row)}>
                      ¿POR QUÉ?
                    </Button>
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => setDetail(row)}>
                      ¿CÓMO SE CALCULÓ?
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">COMPARAR PARROQUIAS</Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Comparación descriptiva de métricas agregadas; no es un ranking electoral.
          </Typography>
          <Select
            multiple
            size="small"
            value={compareIds}
            onChange={(event) => setCompareIds((event.target.value as number[]).slice(0, 3))}
            renderValue={(selected) =>
              (selected as number[])
                .map((id) => data.parishes.find((row) => row.parish_id === id)?.name)
                .filter(Boolean)
                .join(', ')
            }
            sx={{ minWidth: 280 }}
          >
            {data.parishes.map((row) => (
              <MenuItem key={row.parish_id} value={row.parish_id}>
                {row.name}
              </MenuItem>
            ))}
          </Select>
          {compareIds.length > 0 && (
            <Table size="small" sx={{ mt: 2 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Variable</TableCell>
                  {compareIds.map((id) => (
                    <TableCell key={id}>
                      {data.parishes.find((row) => row.parish_id === id)?.name}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {[
                  [
                    'Electores actuales',
                    (row: ParishRow) => integer(row.registered_voters_current),
                  ],
                  [
                    'Participación 2019',
                    (row: ParishRow) => pct(row.historical_2019?.turnout_rate),
                  ],
                  [
                    'Participación 2023',
                    (row: ParishRow) => pct(row.historical_2023?.turnout_rate),
                  ],
                  ['Proyección central', (row: ParishRow) => pct(row.projection?.central)],
                  ['Población INEC', (row: ParishRow) => integer(row.demographics.POP_TOTAL ?? 0)],
                ].map(([label, formatter]) => (
                  <TableRow key={String(label)}>
                    <TableCell>{String(label)}</TableCell>
                    {compareIds.map((id) => {
                      const row = data.parishes.find((item) => item.parish_id === id);
                      return (
                        <TableCell key={id}>
                          {row ? (formatter as (item: ParishRow) => string)(row) : '—'}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h2">DESCARGAR INFORME EJECUTIVO</Typography>
          <Typography sx={{ mb: 2 }}>Generado desde la corrida V1 almacenada.</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={1}>
            {(
              [
                { format: 'PDF', label: 'GENERAR INFORME PDF' },
                { format: 'XLSX', label: 'GENERAR INFORME XLSX' },
              ] as const
            ).map(({ format, label }) => (
              <Button
                key={format}
                variant="contained"
                onClick={async () => {
                  try {
                    setReportStatus('Preparando…');
                    setGeneratedFormat(null);
                    const run = await apiRequest<{
                      id: string;
                      artifact?: { original_download_name: string };
                    }>(`/campaigns/${id}/reports/generate`, {
                      method: 'POST',
                      body: JSON.stringify({
                        template_code: 'CURRENT_ELECTION_EXECUTIVE',
                        format,
                        title: 'Informe ejecutivo — Elección actual',
                        report_date: todayDateOnly(),
                        period: 'LAST_30_DAYS',
                        survey_ids: [],
                        electoral_process_ids: [],
                        demographic_indicator_codes: [],
                        include_comparisons: true,
                      }),
                    });
                    setReportStatus('Generado');
                    setGeneratedFormat(format);
                    await downloadReport(
                      `/campaigns/${id}/reports/${run.id}/download`,
                      run.artifact?.original_download_name ??
                        `informe-eleccion-actual.${format.toLowerCase()}`,
                      false,
                    );
                  } catch {
                    setReportStatus('Error');
                  }
                }}
              >
                {label}
              </Button>
            ))}
          </Stack>
          {reportStatus && <Typography sx={{ mt: 1 }}>Estado: {reportStatus}</Typography>}
          {reportStatus === 'Generado' && generatedFormat && (
            <Typography>Informe {generatedFormat} generado correctamente.</Typography>
          )}
        </Paper>
      </Stack>
      <Dialog open={!!detail} onClose={() => setDetail(null)} fullWidth maxWidth="md">
        <DialogTitle>Auditoría: {detail?.name}</DialogTitle>
        <DialogContent>
          {detail && (
            <Stack spacing={1}>
              <Typography>Registro actual: {integer(detail.registered_voters_current)}</Typography>
              <Typography>
                2019: {pct(detail.historical_2019?.turnout_rate)} · 2023:{' '}
                {pct(detail.historical_2023?.turnout_rate)}
              </Typography>
              <Typography>
                35 % × tasa 2019 + 65 % × tasa 2023 = {pct(detail.projection?.central)}
              </Typography>
              <Typography>
                {integer(detail.registered_voters_current)} × {pct(detail.projection?.central)} ={' '}
                {integer(detail.projection?.expected_voters_central ?? 0)} votantes esperados
              </Typography>
              <Typography>
                LOW: {pct(detail.projection?.low)} · HIGH: {pct(detail.projection?.high)}
              </Typography>
              <Typography>Calidad: {quality(detail.data_quality_status)}</Typography>
              <Typography sx={{ mt: 2 }}>CONTEXTO DEMOGRÁFICO · OFICIAL INEC CPV 2022</Typography>
              {Object.entries(detail.demographics).map(([key, value]) => (
                <Typography key={key}>
                  {key}: {integer(value)}
                </Typography>
              ))}
            </Stack>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
