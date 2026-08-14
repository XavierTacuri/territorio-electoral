import { useState } from 'react';
import {
  AppBar,
  Box,
  Button,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import LogoutIcon from '@mui/icons-material/Logout';
import { NavLink, Outlet, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { canManageUsers } from '../auth/permissions';
import { CampaignSelector } from '../components/navigation/CampaignSelector';
import { RoleBadge } from '../components/data-display/Common';
import { useCampaign } from '../app/CampaignProvider';
const width = 248;
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const theme = useTheme();
  const desktop = useMediaQuery(theme.breakpoints.up('md'));
  const { user, logout } = useAuth();
  const { active } = useCampaign();
  const { campaignId } = useParams();
  const selectedId = campaignId ?? active?.id;
  const base = selectedId ? '/app/campaigns/' + selectedId : '/app/campaigns';
  const items = [
    ['Dashboard', selectedId ? base + '/dashboard' : '/app/campaigns'],
    ['Elección actual', selectedId ? base + '/current-election' : '/app/campaigns'],
    ['Campañas', '/app/campaigns'],
    ['Inteligencia territorial', selectedId ? base + '/territories' : '/app/campaigns'],
    ['Operación territorial', selectedId ? base + '/operations' : '/app/campaigns'],
    ['Actividades', selectedId ? base + '/activities' : '/app/campaigns'],
    ['Necesidades', selectedId ? base + '/needs' : '/app/campaigns'],
    ['Compromisos', selectedId ? base + '/commitments' : '/app/campaigns'],
    ['Encuestas', selectedId ? base + '/surveys' : '/app/campaigns'],
    ['Datos electorales', selectedId ? base + '/electoral' : '/app/campaigns'],
    ['Demografía', selectedId ? base + '/demographics' : '/app/campaigns'],
    ['Mapas', selectedId ? base + '/maps' : '/app/campaigns'],
    ['Informes', selectedId ? base + '/reports' : '/app/campaigns'],
    ['Alertas', selectedId ? base + '/alerts' : '/app/campaigns'],
  ];
  const adminItems = [
    ['Usuarios', '/app/admin/users'],
    ['Roles', '/app/admin/roles'],
    ['Asignaciones', '/app/admin/assignments'],
    ['Fuentes de datos', '/app/admin/data-sources'],
  ];
  const officialDataItems = [
    ['Importar CNE', '/app/admin/official-data/cne'],
    ['Registro electoral', '/app/admin/official-data/cne/roll'],
    ['Importar INEC', '/app/admin/official-data/inec'],
    ['Límites territoriales', '/app/admin/official-data/geography'],
  ];
  const importItems = [
    ['Importaciones', '/app/admin/data-imports'],
    ['Plantillas de informes', '/app/admin/report-templates'],
    ['Auditoría', '/app/admin/security-audit'],
  ];
  const navigation = (
    <Box component="nav" aria-label="Navegación principal">
      <Toolbar>
        <Typography fontWeight={800}>Territorio Electoral</Typography>
      </Toolbar>
      <Divider />
      <List>
        {items.map(([label, to]) => (
          <ListItemButton
            key={label}
            component={NavLink}
            to={to}
            onClick={() => setMobileOpen(false)}
            sx={{
              '&.active': {
                bgcolor: 'action.selected',
                borderRight: 3,
                borderColor: 'primary.main',
              },
            }}
          >
            <ListItemText primary={label} />
          </ListItemButton>
        ))}
        {canManageUsers(user) && (
          <>
            <Divider sx={{ my: 1 }} />
            <Typography component="li" variant="overline" sx={{ px: 2, py: 1, display: 'block' }}>
              Administración
            </Typography>
            {adminItems.map(([label, to]) => (
              <ListItemButton
                key={label}
                component={NavLink}
                to={to}
                onClick={() => setMobileOpen(false)}
                sx={{
                  pl: 3,
                  '&.active': {
                    bgcolor: 'action.selected',
                    borderRight: 3,
                    borderColor: 'primary.main',
                  },
                }}
              >
                <ListItemText primary={label} />
              </ListItemButton>
            ))}
            <Typography component="li" variant="caption" sx={{ px: 3, pt: 1.5, display: 'block' }}>
              Datos oficiales
            </Typography>
            {officialDataItems.map(([label, to]) => (
              <ListItemButton
                key={label}
                component={NavLink}
                to={to}
                onClick={() => setMobileOpen(false)}
                sx={{
                  pl: 4,
                  '&.active': {
                    bgcolor: 'action.selected',
                    borderRight: 3,
                    borderColor: 'primary.main',
                  },
                }}
              >
                <ListItemText primary={label} />
              </ListItemButton>
            ))}
            {importItems.map(([label, to]) => (
              <ListItemButton
                key={label}
                component={NavLink}
                to={to}
                onClick={() => setMobileOpen(false)}
                sx={{
                  pl: 3,
                  '&.active': {
                    bgcolor: 'action.selected',
                    borderRight: 3,
                    borderColor: 'primary.main',
                  },
                }}
              >
                <ListItemText primary={label} />
              </ListItemButton>
            ))}
          </>
        )}
      </List>
    </Box>
  );
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar position="fixed" sx={{ zIndex: theme.zIndex.drawer + 1 }}>
        <Toolbar sx={{ gap: 2 }}>
          <IconButton
            color="inherit"
            aria-label="Abrir menú"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Box sx={{ flexGrow: 1 }}>
            <CampaignSelector />
          </Box>
          <Box sx={{ display: { xs: 'none', sm: 'flex' }, gap: 1, alignItems: 'center' }}>
            <Typography>
              {user?.first_name} {user?.last_name}
            </Typography>
            {user?.roles.slice(0, 1).map((r) => (
              <RoleBadge key={r.code} value={r.code} />
            ))}
          </Box>
          <Button
            color="inherit"
            startIcon={<LogoutIcon />}
            onClick={logout}
            aria-label="Cerrar sesión"
          >
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
              Cerrar sesión
            </Box>
          </Button>
        </Toolbar>
      </AppBar>
      <Drawer
        variant={desktop ? 'permanent' : 'temporary'}
        open={desktop || mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{ width, flexShrink: 0, '& .MuiDrawer-paper': { width, boxSizing: 'border-box' } }}
      >
        {navigation}
      </Drawer>
      <Box
        component="main"
        id="contenido"
        tabIndex={-1}
        sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, sm: 3 }, mt: 8, ml: { md: 0 } }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
