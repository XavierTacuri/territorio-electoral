import { useState } from 'react';
import { Alert, Box, Button, Chip, Paper, Snackbar, Stack, Typography } from '@mui/material';
import AddTaskIcon from '@mui/icons-material/AddTask';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import EventNoteIcon from '@mui/icons-material/EventNote';
import DescriptionIcon from '@mui/icons-material/Description';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SyncIcon from '@mui/icons-material/Sync';
import { useNavigate, useParams } from 'react-router-dom';
import { LoadingSkeleton } from '../../components/feedback/States';
import { todayDateOnly } from '../../lib/dates';
import { useOnlineStatus } from '../../offline/useOnlineStatus';
import { useFieldAgenda } from './useFieldAgenda';
import { useFieldContext } from './useFieldContext';
import { useFieldData } from './useFieldData';
import { SyncNowButton } from './SyncNowButton';

export default function FieldHomePage() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const field = useFieldContext();
  const agenda = useFieldAgenda(field.scope);
  const { pendingCount, refresh } = useFieldData(field.scope);
  const online = useOnlineStatus();
  const [offlineIaNotice, setOfflineIaNotice] = useState(false);
  const base = `/app/campaigns/${campaignId}`;

  if (field.loading) return <LoadingSkeleton />;
  if (field.error) return <Alert severity="info">{field.error}</Alert>;

  const today = todayDateOnly();
  const todayCount = agenda.items.filter((item) => item.activity_date === today).length;

  return (
    <Stack spacing={2}>
      {field.fromCache && (
        <Alert severity="info">
          Mostrando la última información guardada en este dispositivo
          {field.cachedAt ? ` (${new Date(field.cachedAt).toLocaleString('es-EC')})` : ''}.
        </Alert>
      )}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="overline" color="text.secondary">
          Territorio
        </Typography>
        <Typography variant="h2" sx={{ fontSize: '1.1rem', mb: 1 }}>
          {field.campaignName ?? 'Campaña'}
        </Typography>
        {field.parishes.length === 0 ? (
          <Typography color="text.secondary">No tienes parroquias asignadas activas.</Typography>
        ) : (
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {field.parishes.map((p) => (
              <Chip key={p.parish_id} label={p.parish_name} />
            ))}
          </Stack>
        )}
      </Paper>

      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
        <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
          <Typography variant="h2" sx={{ fontSize: '2rem' }}>
            {agenda.loading ? '…' : todayCount}
          </Typography>
          <Typography color="text.secondary">Hoy: actividades</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
          <Typography variant="h2" sx={{ fontSize: '2rem' }}>
            {pendingCount}
          </Typography>
          <Typography color="text.secondary">Pendientes de sincronizar</Typography>
        </Paper>
      </Box>

      <Stack spacing={1.5}>
        <Button
          variant="contained"
          size="large"
          startIcon={<AddTaskIcon />}
          onClick={() => navigate(`${base}/field/activities/new`)}
          disabled={field.parishes.length === 0}
        >
          Registrar actividad
        </Button>
        <Button
          variant="contained"
          size="large"
          color="secondary"
          startIcon={<ReportProblemIcon />}
          onClick={() => navigate(`${base}/field/needs/new`)}
          disabled={field.parishes.length === 0}
        >
          Registrar necesidad
        </Button>
        <Button
          size="large"
          startIcon={<EventNoteIcon />}
          onClick={() => navigate(`${base}/field/agenda`)}
        >
          Mi agenda
        </Button>
        <Button
          size="large"
          startIcon={<DescriptionIcon />}
          onClick={() => navigate(`${base}/field/drafts`)}
        >
          Borradores {pendingCount > 0 ? `(${pendingCount})` : ''}
        </Button>
        <SyncNowButton
          scope={field.scope}
          onDone={refresh}
          icon={<SyncIcon />}
          pendingCount={pendingCount}
        />
        <Button
          size="large"
          startIcon={<SmartToyIcon />}
          onClick={() => {
            if (online) navigate(`${base}/territory-ai`);
            else setOfflineIaNotice(true);
          }}
        >
          Territorio IA
        </Button>
      </Stack>
      <Snackbar
        open={offlineIaNotice}
        autoHideDuration={4000}
        onClose={() => setOfflineIaNotice(false)}
      >
        <Alert severity="info" onClose={() => setOfflineIaNotice(false)} sx={{ width: '100%' }}>
          Territorio IA necesita conexión a internet.
        </Alert>
      </Snackbar>
    </Stack>
  );
}
