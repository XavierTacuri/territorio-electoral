import { BottomNavigation, BottomNavigationAction, Box, Paper, Typography } from '@mui/material';
import HomeIcon from '@mui/icons-material/Home';
import EventNoteIcon from '@mui/icons-material/EventNote';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import DescriptionIcon from '@mui/icons-material/Description';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ConnectionStatus, OfflineBanner } from './ConnectionStatus';
import { useOfflineCatalog } from './useOfflineCatalog';

const tabs = [
  { label: 'Inicio', icon: <HomeIcon />, suffix: 'field' },
  { label: 'Agenda', icon: <EventNoteIcon />, suffix: 'field/agenda' },
  { label: 'Registrar', icon: <AddCircleIcon />, suffix: 'field/activities/new' },
  { label: 'Pendientes', icon: <DescriptionIcon />, suffix: 'field/drafts' },
];

export function FieldLayout() {
  const { campaignId = '' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const base = `/app/campaigns/${campaignId}`;
  const current = tabs.findIndex((tab) => location.pathname === `${base}/${tab.suffix}`);
  // Warm the reference-catalog cache as soon as Field is opened online, so a
  // coordinator who only ever opened Field once with connectivity still has
  // activity-type/need-category options available the next time they are
  // offline, even if they never happened to open a form first.
  useOfflineCatalog('activity-types');
  useOfflineCatalog('need-categories');

  return (
    <Box sx={{ maxWidth: 480, mx: 'auto', pb: { xs: 9, sm: 0 } }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h1" sx={{ fontSize: '1.3rem' }}>
          Operación de campo
        </Typography>
        <ConnectionStatus />
      </Box>
      <OfflineBanner />
      <Outlet />
      <Paper
        elevation={3}
        sx={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          display: { xs: 'block', sm: 'none' },
          zIndex: 10,
        }}
      >
        <BottomNavigation
          showLabels
          value={current === -1 ? false : current}
          onChange={(_, index) => navigate(`${base}/${tabs[index].suffix}`)}
        >
          {tabs.map((tab) => (
            <BottomNavigationAction key={tab.suffix} label={tab.label} icon={tab.icon} />
          ))}
        </BottomNavigation>
      </Paper>
    </Box>
  );
}
