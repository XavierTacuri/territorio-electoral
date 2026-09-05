import { useState } from 'react';
import {
  AppBar,
  Badge,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Menu,
  MenuItem,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import LogoutIcon from '@mui/icons-material/Logout';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';
import NotificationsOutlinedIcon from '@mui/icons-material/NotificationsOutlined';
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { useCampaign } from '../app/CampaignProvider';
import { useActiveOrganization } from '../app/OrganizationProvider';
import { useAuth } from '../auth/AuthProvider';
import { CampaignSelector } from '../components/navigation/CampaignSelector';
import { OrganizationSelector } from '../components/navigation/OrganizationSelector';
import { RoleBadge } from '../components/data-display/Common';
import { useAlertBadgeCount } from '../features/alerts/useAlertBadgeCount';
import { usePendingSyncCount } from '../offline/usePendingSyncCount';
import { useResolvedOrganizationId } from '../offline/useResolvedOrganizationId';
import { buildNavigation } from './navigation';
import { GlobalFooter } from './GlobalFooter';

const width = 248;

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountAnchor, setAccountAnchor] = useState<HTMLElement | null>(null);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const navigate = useNavigate();
  const theme = useTheme();
  const desktop = useMediaQuery(theme.breakpoints.up('md'));
  const { user, logout } = useAuth();
  const { active } = useCampaign();
  const { activeOrganization } = useActiveOrganization();
  const { campaignId } = useParams();
  const selectedId = campaignId ?? active?.id;
  const groups = buildNavigation(user, activeOrganization?.current_role ?? null, selectedId);
  const organizationId = useResolvedOrganizationId(selectedId, active?.organization_id);
  const pendingSyncCount = usePendingSyncCount(
    user && selectedId && organizationId
      ? { user_id: user.id, organization_id: organizationId, campaign_id: selectedId }
      : null,
  );
  const alertBadgeCount = useAlertBadgeCount(selectedId);
  const requestLogout = () => {
    if (pendingSyncCount > 0) setConfirmLogout(true);
    else void logout();
  };

  const navigation = (
    <Box component="nav" aria-label="Navegación principal">
      <Toolbar>
        <Typography fontWeight={800}>Territorio Electoral</Typography>
      </Toolbar>
      <Divider />
      <List>
        {groups.map((group, index) => (
          <Box component="li" key={group.label} sx={{ listStyle: 'none' }}>
            {index > 0 && <Divider sx={{ my: 1 }} />}
            <Typography component="div" variant="overline" sx={{ px: 2, py: 1, display: 'block' }}>
              {group.label}
            </Typography>
            {group.items.map(({ label, to }) => (
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
          </Box>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar position="fixed" sx={{ zIndex: theme.zIndex.drawer + 1 }}>
        <Toolbar sx={{ gap: { xs: 0.5, sm: 2 }, px: { xs: 0.5, sm: 3 } }}>
          <IconButton
            color="inherit"
            aria-label="Abrir menú"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Box
            sx={{
              flexGrow: 1,
              display: 'flex',
              gap: { xs: 0.5, sm: 1.5 },
              alignItems: 'center',
              minWidth: 0,
            }}
          >
            <OrganizationSelector />
            <CampaignSelector />
          </Box>
          <Box sx={{ display: { xs: 'none', sm: 'flex' }, gap: 1, alignItems: 'center' }}>
            <Typography>
              {user?.first_name} {user?.last_name}
            </Typography>
            {user?.roles.slice(0, 1).map((role) => (
              <RoleBadge key={role.code} value={role.code} />
            ))}
          </Box>
          {selectedId && (
            <IconButton
              color="inherit"
              aria-label="Centro de alertas"
              onClick={() => navigate(`/app/campaigns/${selectedId}/alerts`)}
            >
              <Badge badgeContent={alertBadgeCount} color="error" max={99}>
                <NotificationsOutlinedIcon />
              </Badge>
            </IconButton>
          )}
          <IconButton color="inherit" aria-label="Abrir menú de usuario" onClick={(event) => setAccountAnchor(event.currentTarget)}>
            <AccountCircleIcon />
          </IconButton>
          <Menu anchorEl={accountAnchor} open={Boolean(accountAnchor)} onClose={() => setAccountAnchor(null)}>
            <MenuItem onClick={() => { setAccountAnchor(null); navigate('/app/account'); }}>Mi cuenta</MenuItem>
            <MenuItem onClick={() => { setAccountAnchor(null); requestLogout(); }}>
              <LogoutIcon fontSize="small" sx={{ mr: 1 }} />Cerrar sesión
            </MenuItem>
          </Menu>
          <Button color="inherit" startIcon={<LogoutIcon />} onClick={requestLogout} aria-label="Cerrar sesión">
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>Cerrar sesión</Box>
          </Button>
        </Toolbar>
      </AppBar>
      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)}>
        <DialogTitle>Registros pendientes de sincronizar</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Tienes {pendingSyncCount} registro{pendingSyncCount === 1 ? '' : 's'} pendiente
            {pendingSyncCount === 1 ? '' : 's'} de sincronizar. Se mantienen guardados en este dispositivo y
            volverán a estar disponibles la próxima vez que inicies sesión con la misma cuenta.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)}>Cancelar</Button>
          <Button
            color="warning"
            onClick={() => {
              setConfirmLogout(false);
              void logout();
            }}
          >
            Cerrar sesión de todas formas
          </Button>
        </DialogActions>
      </Dialog>
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
        sx={{
          display: 'flex',
          flexDirection: 'column',
          flexGrow: 1,
          minWidth: 0,
          minHeight: { xs: 'calc(100vh - 56px)', sm: 'calc(100vh - 64px)' },
          p: { xs: 2, sm: 3 },
          mt: { xs: 7, sm: 8 },
          ml: { md: 0 },
        }}
      >
        <Outlet />
        <GlobalFooter />
      </Box>
    </Box>
  );
}
