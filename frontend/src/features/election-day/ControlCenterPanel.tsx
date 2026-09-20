import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  MenuItem,
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
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import {
  ACT_STATUS_LABELS,
  type ControlCenterPollingPlaceSummary,
  type ControlCenterSummary,
  type ElectionActDetail,
  type ElectionActListResponse,
  type ElectoralBoard,
} from './types';

// §16-21 (Fase 3): consolidado factual NO OFICIAL de actas VALIDATED — nunca
// declara ganador, probabilidad ni proyección. El orden de candidatos y
// recintos respeta el que entrega el backend (ballot_order / nombre), nunca
// se reordena por votos, que convertiría la tabla en un ranking implícito.

function ActValidatedDetail({ campaignId, actId }: { campaignId: string; actId: string }) {
  const detail = useQuery({
    queryKey: ['election-act-detail-readonly', campaignId, actId],
    queryFn: () =>
      apiRequest<ElectionActDetail>(`/campaigns/${campaignId}/election-day/acts/${actId}`),
  });
  if (detail.isLoading) return <Typography variant="body2">Cargando acta…</Typography>;
  if (detail.isError || !detail.data)
    return <Typography variant="body2">No se pudo cargar el detalle del acta.</Typography>;
  const { act, revisions } = detail.data;
  const validated = revisions.find((r) => r.id === act.validated_revision_id);
  if (!validated)
    return <Typography variant="body2">Esta acta aún no tiene una revisión validada.</Typography>;
  return (
    <Stack spacing={0.5} sx={{ pl: 2, py: 1 }}>
      <Typography variant="caption" color="text.secondary">
        Revisión validada #{validated.revision_number} · válidos {validated.valid_ballots ?? '—'} ·
        blancos {validated.blank_ballots} · nulos {validated.null_ballots}
      </Typography>
      <Table size="small">
        <TableBody>
          {validated.results.map((r) => (
            <TableRow key={r.electoral_candidate_id}>
              <TableCell>{r.electoral_candidate_id}</TableCell>
              <TableCell align="right">{r.votes}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Stack>
  );
}

function PollingPlaceDrillDown({
  campaignId,
  place,
}: {
  campaignId: string;
  place: ControlCenterPollingPlaceSummary;
}) {
  const [open, setOpen] = useState(false);
  const [openActId, setOpenActId] = useState<string | null>(null);
  const boards = useQuery({
    queryKey: ['election-day-boards', campaignId, place.polling_place_id],
    queryFn: () =>
      apiRequest<ElectoralBoard[]>(
        `/campaigns/${campaignId}/election-day/polling-places/${place.polling_place_id}/boards`,
      ),
    enabled: open,
  });
  const acts = useQuery({
    queryKey: ['election-acts-by-place-readonly', campaignId, place.polling_place_id],
    queryFn: () =>
      apiRequest<ElectionActListResponse>(
        `/campaigns/${campaignId}/election-day/acts?polling_place_id=${place.polling_place_id}`,
      ),
    enabled: open,
  });
  const boardLabel = (boardId: string) => {
    const b = boards.data?.find((x) => x.id === boardId);
    return b ? `JRV ${b.board_number} (${b.official_code})` : boardId;
  };
  return (
    <>
      <TableRow>
        <TableCell>
          <IconButton
            size="small"
            aria-label={open ? 'Ocultar juntas' : `Ver juntas de ${place.polling_place_name}`}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
          {place.polling_place_name}
        </TableCell>
        <TableCell align="right">{place.expected_boards}</TableCell>
        <TableCell align="right">{place.received}</TableCell>
        <TableCell align="right">{place.validated}</TableCell>
        <TableCell align="right">{place.in_review}</TableCell>
        <TableCell align="right">{place.observed}</TableCell>
        <TableCell align="right">{place.pending}</TableCell>
        <TableCell align="right">{place.coverage_validated_pct}%</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={8} sx={{ py: 0, border: open ? undefined : 'none' }}>
          <Collapse in={open} unmountOnExit>
            {acts.isLoading ? (
              <Typography variant="body2" sx={{ py: 1 }}>
                Cargando juntas…
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Junta</TableCell>
                    <TableCell>Estado del acta</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(acts.data?.items ?? []).map((a) => (
                    <TableRow key={a.id}>
                      <TableCell>{boardLabel(a.electoral_board_id)}</TableCell>
                      <TableCell>{ACT_STATUS_LABELS[a.status]}</TableCell>
                      <TableCell align="right">
                        {a.status === 'VALIDATED' && (
                          <Button
                            size="small"
                            onClick={() => setOpenActId(openActId === a.id ? null : a.id)}
                          >
                            {openActId === a.id ? 'OCULTAR ACTA' : 'VER ACTA VALIDADA'}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {openActId && (
                    <TableRow>
                      <TableCell colSpan={3} sx={{ borderBottom: 'none' }}>
                        <ActValidatedDetail campaignId={campaignId} actId={openActId} />
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

export function ControlCenterPanel({
  campaignId,
  operationStatus,
  isAdminSupport,
}: {
  campaignId: string;
  operationStatus: 'PREPARATION' | 'ACTIVE' | 'SCRUTINY' | 'CLOSED';
  isAdminSupport: boolean;
}) {
  const [selectedContestId, setSelectedContestId] = useState('');

  const query = useQuery({
    queryKey: ['election-day-control-center', campaignId],
    queryFn: () =>
      apiRequest<{ control_center: ControlCenterSummary | null }>(
        `/campaigns/${campaignId}/election-day/control-center`,
      ),
    // 45 s cae dentro del rango de 30-60 s pedido; TanStack Query nunca
    // solapa una nueva ejecución de refetchInterval mientras la anterior
    // sigue en curso para la misma queryKey.
    refetchInterval: operationStatus === 'SCRUTINY' ? 45000 : false,
  });

  const cc = query.data?.control_center;
  const contests = cc?.contests ?? [];
  const activeContest =
    contests.find((c) => c.contest_id === selectedContestId) ?? contests[0] ?? null;

  if (query.isLoading) {
    return <Typography color="text.secondary">Cargando Centro de Control…</Typography>;
  }
  if (!cc) {
    // El aviso de solo lectura es sobre el ESTADO de la jornada, no sobre si
    // hay datos que mostrar — debe seguir viéndose aunque todavía no exista
    // una contienda elegible configurada.
    return (
      <Stack spacing={2} sx={{ mb: 3 }}>
        {operationStatus === 'CLOSED' && (
          <Alert severity="info">
            El Centro de Control queda en modo solo lectura tras el cierre de la jornada.
          </Alert>
        )}
        <Alert severity="info">
          Aún no hay una contienda elegible configurada para el conteo interno de actas.
        </Alert>
      </Stack>
    );
  }

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
          flexWrap="wrap"
          gap={1}
          sx={{ mb: 1 }}
        >
          <Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography component="h2" variant="h2">
                Conteo interno de actas
              </Typography>
              <Chip size="small" color="warning" label="NO OFICIAL" />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Derivado exclusivamente de actas validadas. No es un resultado oficial, no proyecta
              actas faltantes ni declara ganador.
            </Typography>
          </Box>
          <Button size="small" disabled={query.isFetching} onClick={() => query.refetch()}>
            {query.isFetching ? 'ACTUALIZANDO…' : 'ACTUALIZAR'}
          </Button>
        </Stack>

        {isAdminSupport && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Modo soporte administrativo — estos números son idénticos a los que ve el equipo de la
            campaña.
          </Alert>
        )}
        {operationStatus === 'CLOSED' && (
          <Alert severity="info" sx={{ mb: 2 }}>
            El Centro de Control queda en modo solo lectura tras el cierre de la jornada.
          </Alert>
        )}

        {contests.length > 1 && (
          <TextField
            select
            size="small"
            label="Contienda"
            value={activeContest?.contest_id ?? ''}
            onChange={(e) => setSelectedContestId(e.target.value)}
            sx={{ mb: 2, minWidth: 280 }}
          >
            {contests.map((c) => (
              <MenuItem key={c.contest_id} value={c.contest_id}>
                {c.contest_name}
              </MenuItem>
            ))}
          </TextField>
        )}

        {activeContest && (
          <>
            <Typography variant="body2" sx={{ mb: 1 }}>
              Actas validadas: {activeContest.validated_acts} / {activeContest.expected_acts} ·
              Votos válidos: {activeContest.valid_votes} · Blancos: {activeContest.blank_votes} ·
              Nulos: {activeContest.null_votes}
            </Typography>
            <Table size="small" sx={{ mb: 3 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Lista</TableCell>
                  <TableCell>Candidato</TableCell>
                  <TableCell align="right">Votos</TableCell>
                  <TableCell align="right">% sobre válidos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {activeContest.candidates.map((c) => (
                  <TableRow key={c.candidate_id}>
                    <TableCell>{c.list_number ?? '—'}</TableCell>
                    <TableCell>{c.display_name}</TableCell>
                    <TableCell align="right">{c.votes}</TableCell>
                    <TableCell align="right">{c.pct_valid_votes}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}

        <Typography component="h3" variant="h3" sx={{ mb: 1 }}>
          Cobertura de actas por recinto
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Recinto</TableCell>
              <TableCell align="right">Juntas esperadas</TableCell>
              <TableCell align="right">Actas recibidas</TableCell>
              <TableCell align="right">Actas validadas</TableCell>
              <TableCell align="right">Actas en revisión</TableCell>
              <TableCell align="right">Actas observadas</TableCell>
              <TableCell align="right">Actas pendientes</TableCell>
              <TableCell align="right">% validado</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {cc.polling_places.map((p) => (
              <PollingPlaceDrillDown key={p.polling_place_id} campaignId={campaignId} place={p} />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
