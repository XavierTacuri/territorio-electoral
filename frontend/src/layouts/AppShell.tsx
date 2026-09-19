import { useMemo, useState } from 'react';
import {
  Autocomplete,
  AppBar,
  Avatar,
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
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Stack,
  TextField,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import LogoutIcon from '@mui/icons-material/Logout';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import NotificationsOutlinedIcon from '@mui/icons-material/NotificationsOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import SpaceDashboardOutlinedIcon from '@mui/icons-material/SpaceDashboardOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
import WorkOutlineOutlinedIcon from '@mui/icons-material/WorkOutlineOutlined';
import HowToVoteOutlinedIcon from '@mui/icons-material/HowToVoteOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import TravelExploreOutlinedIcon from '@mui/icons-material/TravelExploreOutlined';
import PollOutlinedIcon from '@mui/icons-material/PollOutlined';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined';
import PublicOutlinedIcon from '@mui/icons-material/PublicOutlined';
import BarChartOutlinedIcon from '@mui/icons-material/BarChartOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import MapOutlinedIcon from '@mui/icons-material/MapOutlined';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import NotificationsActiveOutlinedIcon from '@mui/icons-material/NotificationsActiveOutlined';
import ForumOutlinedIcon from '@mui/icons-material/ForumOutlined';
import EventAvailableOutlinedIcon from '@mui/icons-material/EventAvailableOutlined';
import AssignmentOutlinedIcon from '@mui/icons-material/AssignmentOutlined';
import FlagOutlinedIcon from '@mui/icons-material/FlagOutlined';
import ApartmentOutlinedIcon from '@mui/icons-material/ApartmentOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import FiberManualRecordOutlinedIcon from '@mui/icons-material/FiberManualRecordOutlined';
import type { SvgIconComponent } from '@mui/icons-material';
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { useCampaign } from '../app/CampaignProvider';
import { sidebar } from '../app/theme';
import { useActiveOrganization } from '../app/OrganizationProvider';
import { useAuth } from '../auth/AuthProvider';
import { isCoordinatorOnly } from '../auth/permissions';
import { CampaignSelector } from '../components/navigation/CampaignSelector';
import { OrganizationSelector } from '../components/navigation/OrganizationSelector';
import { useAlertBadgeCount } from '../features/alerts/useAlertBadgeCount';
import { useMyElectionDayNavVisibility } from '../features/election-day/useMyElectionDayNavVisibility';
import { usePendingSyncCount } from '../offline/usePendingSyncCount';
import { useResolvedOrganizationId } from '../offline/useResolvedOrganizationId';
import { buildNavigation, type NavigationGroup } from './navigation';
import { GlobalFooter } from './GlobalFooter';

const width = 264;

// Mapa puramente presentacional: no altera qué ítems existen ni sus rutas
// (eso lo sigue decidiendo buildNavigation por rol), solo les asocia un
// icono coherente. Las etiquetas de Administración no cubiertas aquí caen
// en el icono neutro por defecto en vez de duplicar entradas.
const GROUP_ICONS: Record<string, SvgIconComponent> = {
  Inicio: SpaceDashboardOutlinedIcon,
  Análisis: InsightsOutlinedIcon,
  Operación: WorkOutlineOutlinedIcon,
  Jornada: HowToVoteOutlinedIcon,
  Administración: SettingsOutlinedIcon,
};
const ITEM_ICONS: Record<string, SvgIconComponent> = {
  Dashboard: SpaceDashboardOutlinedIcon,
  'Panorama electoral': InsightsOutlinedIcon,
  'Inteligencia territorial': TravelExploreOutlinedIcon,
  'Encuestas y estudios': PollOutlinedIcon,
  'Territorio IA · PRO': AutoAwesomeOutlinedIcon,
  'Calendario de campaña': CalendarMonthOutlinedIcon,
  'Fuentes públicas': PublicOutlinedIcon,
  'Elección actual': HowToVoteOutlinedIcon,
  'Datos electorales': BarChartOutlinedIcon,
  Demografía: GroupsOutlinedIcon,
  Mapas: MapOutlinedIcon,
  'Centro de Informes': DescriptionOutlinedIcon,
  'Centro de alertas': NotificationsActiveOutlinedIcon,
  'Preparación para debate': ForumOutlinedIcon,
  'Jornada Electoral': HowToVoteOutlinedIcon,
  'Mi Jornada': HowToVoteOutlinedIcon,
  'Operación territorial': WorkOutlineOutlinedIcon,
  Actividades: EventAvailableOutlinedIcon,
  Necesidades: AssignmentOutlinedIcon,
  Campañas: FlagOutlinedIcon,
  'Mi organización': ApartmentOutlinedIcon,
  'Centro de datos': StorageOutlinedIcon,
};
const itemIcon = (label: string) => ITEM_ICONS[label] ?? FiberManualRecordOutlinedIcon;
const initialsOf = (firstName?: string, lastName?: string) =>
  `${firstName?.[0] ?? ''}${lastName?.[0] ?? ''}`.toUpperCase() || '?';

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
  const isFieldCoordinator = isCoordinatorOnly(user);
  const { delegateVisible, validationVisible } = useMyElectionDayNavVisibility(selectedId);
  const groups = buildNavigation(
    user,
    activeOrganization?.current_role ?? null,
    selectedId,
    delegateVisible,
    validationVisible,
  );
  const organizationId = useResolvedOrganizationId(selectedId, active?.organization_id);
  const pendingSyncCount = usePendingSyncCount(
    user && selectedId && organizationId
      ? { user_id: user.id, organization_id: organizationId, campaign_id: selectedId }
      : null,
  );
  const alertBadgeCount = useAlertBadgeCount(isFieldCoordinator ? null : selectedId);
  const requestLogout = () => {
    if (pendingSyncCount > 0) setConfirmLogout(true);
    else void logout();
  };
  const searchOptions = useMemo(
    () =>
      groups.flatMap((group: NavigationGroup) =>
        group.items.map((item) => ({ ...item, group: group.label })),
      ),
    [groups],
  );

  const navigation = (
    <Box
      component="nav"
      aria-label="Navegación principal"
      sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      <Toolbar sx={{ gap: 1.25 }}>
        <Box
          sx={{
            width: 34,
            height: 34,
            borderRadius: 2,
            bgcolor: sidebar.accent,
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
          }}
        >
          <MapOutlinedIcon sx={{ fontSize: 20, color: '#04211D' }} />
        </Box>
        <Typography fontWeight={800} sx={{ color: sidebar.textActive, lineHeight: 1.15 }}>
          Territorio
          <br />
          Electoral
        </Typography>
      </Toolbar>
      <Divider sx={{ borderColor: sidebar.border }} />
      <List sx={{ flexGrow: 1, overflowY: 'auto', py: 1 }}>
        {groups.map((group, index) => {
          const GroupIcon = GROUP_ICONS[group.label] ?? FiberManualRecordOutlinedIcon;
          return (
            <Box component="li" key={group.label} sx={{ listStyle: 'none' }}>
              {index > 0 && <Divider sx={{ my: 1, borderColor: sidebar.border }} />}
              <Stack
                direction="row"
                alignItems="center"
                spacing={1}
                sx={{ px: 2.5, py: 1, color: sidebar.textMuted }}
              >
                <GroupIcon sx={{ fontSize: 16 }} />
                <Typography
                  component="div"
                  variant="overline"
                  sx={{ display: 'block', color: 'inherit', lineHeight: 1 }}
                >
                  {group.label}
                </Typography>
              </Stack>
              {group.items.map(({ label, to }) => {
                const ItemIcon = itemIcon(label);
                return (
                  <ListItemButton
                    key={label}
                    component={NavLink}
                    to={to}
                    onClick={() => setMobileOpen(false)}
                    sx={{
                      mx: 1.5,
                      pl: 1.5,
                      borderRadius: 2,
                      color: sidebar.text,
                      '&:hover': { bgcolor: sidebar.hoverBg },
                      '&.active': {
                        bgcolor: sidebar.activeBg,
                        color: sidebar.textActive,
                        '& .MuiListItemIcon-root': { color: sidebar.accent },
                      },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 34, color: 'inherit' }}>
                      <ItemIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={label}
                      primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: 600 }}
                    />
                  </ListItemButton>
                );
              })}
            </Box>
          );
        })}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        sx={{
          zIndex: theme.zIndex.drawer + 1,
          ml: { md: `${width}px` },
          width: { md: `calc(100% - ${width}px)` },
        }}
      >
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
              display: 'flex',
              gap: { xs: 0.5, sm: 1.5 },
              alignItems: 'center',
              minWidth: 0,
            }}
          >
            <OrganizationSelector hideWhenSingle />
            <CampaignSelector />
          </Box>
          <Autocomplete
            size="small"
            options={searchOptions}
            groupBy={(option) => option.group}
            getOptionLabel={(option) => option.label}
            onChange={(_, option) => option && navigate(option.to)}
            blurOnSelect
            clearOnBlur
            sx={{ width: { xs: 0, md: 220 }, display: { xs: 'none', md: 'block' }, ml: 1.5 }}
            renderInput={(params) => (
              <TextField
                {...params}
                placeholder="Buscar en el sistema…"
                InputProps={{
                  ...params.InputProps,
                  startAdornment: (
                    <SearchOutlinedIcon fontSize="small" sx={{ color: 'text.disabled', mr: 0.5 }} />
                  ),
                }}
              />
            )}
          />
          <Box sx={{ flexGrow: 1 }} />
          {selectedId && !isFieldCoordinator && (
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
          <Button
            color="inherit"
            aria-label="Abrir menú de usuario"
            onClick={(event) => setAccountAnchor(event.currentTarget)}
            sx={{ textTransform: 'none', gap: 1, pl: 0.5, pr: { xs: 0.5, sm: 1 } }}
          >
            <Avatar sx={{ width: 30, height: 30, fontSize: '0.8rem', bgcolor: 'primary.main' }}>
              {initialsOf(user?.first_name, user?.last_name)}
            </Avatar>
            <Typography
              variant="body2"
              fontWeight={700}
              color="inherit"
              noWrap
              sx={{ display: { xs: 'none', sm: 'block' }, maxWidth: 160 }}
            >
              {user?.first_name} {user?.last_name}
            </Typography>
            <KeyboardArrowDownIcon
              fontSize="small"
              sx={{ display: { xs: 'none', sm: 'block' }, color: 'text.secondary' }}
            />
          </Button>
          <Menu
            anchorEl={accountAnchor}
            open={Boolean(accountAnchor)}
            onClose={() => setAccountAnchor(null)}
          >
            <Box sx={{ px: 2, py: 1.25, minWidth: 200 }}>
              <Typography fontWeight={700} noWrap>
                {user?.first_name} {user?.last_name}
              </Typography>
              {user?.roles[0] && (
                <Typography variant="caption" color="text.secondary" display="block">
                  {user.roles[0].name}
                </Typography>
              )}
              {activeOrganization?.name && (
                <Typography variant="caption" color="text.secondary" display="block">
                  {activeOrganization.name}
                </Typography>
              )}
            </Box>
            <Divider />
            <MenuItem
              onClick={() => {
                setAccountAnchor(null);
                navigate('/app/account');
              }}
            >
              Mi cuenta
            </MenuItem>
            <MenuItem
              onClick={() => {
                setAccountAnchor(null);
                requestLogout();
              }}
            >
              <LogoutIcon fontSize="small" sx={{ mr: 1 }} />
              Cerrar sesión
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)}>
        <DialogTitle>Registros pendientes de sincronizar</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Tienes {pendingSyncCount} registro{pendingSyncCount === 1 ? '' : 's'} pendiente
            {pendingSyncCount === 1 ? '' : 's'} de sincronizar. Se mantienen guardados en este
            dispositivo y volverán a estar disponibles la próxima vez que inicies sesión con la
            misma cuenta.
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
        sx={{
          width,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width,
            boxSizing: 'border-box',
            bgcolor: sidebar.bg,
            borderRight: `1px solid ${sidebar.border}`,
          },
        }}
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
