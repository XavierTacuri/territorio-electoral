import type { SessionUser } from '../auth/permissions';

export type OrganizationRole = 'OWNER' | 'ADMIN' | 'MEMBER' | null;
export type NavigationItem = { label: string; to: string };
export type NavigationGroup = { label: string; items: NavigationItem[] };

const hasAnyRole = (user: SessionUser | null, roles: string[]) =>
  !!user && (user.is_superuser || user.roles.some((role) => roles.includes(role.code)));
// Unlike hasAnyRole, this never treats a superuser as implicitly holding the
// role: it is used to detect a genuinely coordinator-only profile, and a
// superuser (or a user who also literally holds a broader role) must keep
// the fuller navigation their other role/privilege grants.
const hasLiteralRole = (user: SessionUser | null, role: string) =>
  !!user && user.roles.some((r) => r.code === role);

export const canSeeCampaignAdministration = (user: SessionUser | null) =>
  hasAnyRole(user, ['ADMIN']);

// Jornada Electoral (Centro de Control) es exclusivo del equipo ejecutivo de
// campaña (§5/§12): ni Coordinator ni Analyst la ven, y ADMIN no la ve como
// operación normal de campaña — solo entra vía "Soporte Jornada Electoral"
// en Administración.
const canSeeElectionDayControlCenterLink = (user: SessionUser | null) =>
  hasLiteralRole(user, 'CANDIDATE') || hasLiteralRole(user, 'CAMPAIGN_MANAGER');

export function buildNavigation(
  user: SessionUser | null,
  organizationRole: OrganizationRole,
  campaignId?: string,
  myJornadaVisible?: boolean,
  validationVisible?: boolean,
): NavigationGroup[] {
  const campaignPath = (path: string) =>
    campaignId ? `/app/campaigns/${campaignId}/${path}` : '/app/campaigns';
  const platformAdmin = hasAnyRole(user, ['ADMIN']);
  const analyst = hasAnyRole(user, ['ANALYST']);
  const isFieldCoordinator =
    !platformAdmin &&
    !analyst &&
    !hasLiteralRole(user, 'CANDIDATE') &&
    !hasLiteralRole(user, 'CAMPAIGN_MANAGER') &&
    hasLiteralRole(user, 'TERRITORIAL_COORDINATOR');
  const operational = hasAnyRole(user, [
    'CANDIDATE',
    'CAMPAIGN_MANAGER',
    'TERRITORIAL_COORDINATOR',
    'ANALYST',
  ]);
  const detailedAnalysis = platformAdmin || analyst;
  const jornadaItems: NavigationItem[] = [
    ...(myJornadaVisible ? [{ label: 'Mi Jornada', to: campaignPath('election-day/my') }] : []),
    ...(validationVisible
      ? [{ label: 'Validación de actas', to: campaignPath('election-day/validation') }]
      : []),
  ];

  // TERRITORIAL_COORDINATOR gets a dedicated, reduced product surface: it is
  // an operational territorial role, not an executive/analyst/admin one, so
  // it does not share the general "Análisis" menu built below. It has no
  // access to Jornada Electoral itself (§12) — only to a personal
  // assignment it may separately hold as operational staff.
  if (isFieldCoordinator) {
    return [
      {
        label: 'Inicio',
        items: [{ label: 'Dashboard', to: campaignPath('dashboard') }],
      },
      {
        label: 'Análisis',
        items: [
          { label: 'Panorama electoral', to: campaignPath('panorama') },
          { label: 'Inteligencia territorial', to: campaignPath('territories') },
          { label: 'Calendario de campaña', to: campaignPath('calendar') },
        ],
      },
      {
        label: 'Operación',
        items: [
          { label: 'Operación territorial', to: campaignPath('operations') },
          { label: 'Actividades', to: campaignPath('activities') },
          { label: 'Necesidades', to: campaignPath('needs') },
        ],
      },
      { label: 'Jornada', items: jornadaItems },
    ].filter((group) => group.items.length > 0);
  }

  const groups: NavigationGroup[] = [
    {
      label: 'Inicio',
      items: [{ label: 'Dashboard', to: campaignPath('dashboard') }],
    },
    {
      label: 'Análisis',
      items: [
        { label: 'Panorama electoral', to: campaignPath('panorama') },
        { label: 'Inteligencia territorial', to: campaignPath('territories') },
        { label: 'Encuestas y estudios', to: campaignPath('surveys') },
        { label: 'Territorio IA · PRO', to: campaignPath('territory-ai') },
        { label: 'Calendario de campaña', to: campaignPath('calendar') },
        ...(detailedAnalysis
          ? [
              { label: 'Fuentes públicas', to: campaignPath('public-intelligence') },
              { label: 'Elección actual', to: campaignPath('current-election') },
              { label: 'Datos electorales', to: campaignPath('electoral') },
              { label: 'Demografía', to: campaignPath('demographics') },
              { label: 'Mapas', to: campaignPath('maps') },
            ]
          : []),
        ...(hasAnyRole(user, ['ADMIN', 'ANALYST', 'CANDIDATE', 'CAMPAIGN_MANAGER'])
          ? [{ label: 'Centro de Informes', to: campaignPath('reports') }]
          : []),
        ...(hasAnyRole(user, ['ADMIN', 'ANALYST', 'CANDIDATE', 'CAMPAIGN_MANAGER'])
          ? [{ label: 'Centro de alertas', to: campaignPath('alerts') }]
          : []),
        ...(hasAnyRole(user, ['ADMIN', 'ANALYST', 'CANDIDATE', 'CAMPAIGN_MANAGER'])
          ? [{ label: 'Preparación para debate', to: campaignPath('debate') }]
          : []),
        ...(canSeeElectionDayControlCenterLink(user)
          ? [{ label: 'Jornada Electoral', to: campaignPath('election-day') }]
          : []),
      ],
    },
    ...(operational
      ? [
          {
            label: 'Operación',
            items: [
              { label: 'Operación territorial', to: campaignPath('operations') },
              { label: 'Actividades', to: campaignPath('activities') },
              { label: 'Necesidades', to: campaignPath('needs') },
            ],
          },
        ]
      : []),
    { label: 'Jornada', items: jornadaItems },
  ];

  const administration: NavigationItem[] = [
    ...(canSeeCampaignAdministration(user) ? [{ label: 'Campañas', to: '/app/campaigns' }] : []),
    ...(platformAdmin || organizationRole === 'OWNER' || organizationRole === 'ADMIN'
      ? [{ label: 'Mi organización', to: '/app/organization' }]
      : []),
    ...(platformAdmin || analyst ? [{ label: 'Centro de datos', to: '/app/admin/data-hub' }] : []),
    ...(platformAdmin
      ? [{ label: 'Calendario electoral oficial', to: '/app/admin/electoral-milestones' }]
      : []),
    ...(platformAdmin
      ? [
          { label: 'Organizaciones', to: '/app/admin/organizations' },
          { label: 'Usuarios', to: '/app/admin/users' },
          { label: 'Roles', to: '/app/admin/roles' },
          { label: 'Asignaciones', to: '/app/admin/assignments' },
          { label: 'Fuentes de datos', to: '/app/admin/data-sources' },
          { label: 'Licencia y funcionalidades', to: '/app/admin/feature-entitlements' },
          { label: 'Importar CNE', to: '/app/admin/official-data/cne' },
          { label: 'Registro electoral', to: '/app/admin/official-data/cne/roll' },
          { label: 'Importar INEC', to: '/app/admin/official-data/inec' },
          { label: 'Límites territoriales', to: '/app/admin/official-data/geography' },
          { label: 'Importaciones', to: '/app/admin/data-imports' },
          { label: 'Soporte Jornada Electoral', to: '/app/admin/election-day-support' },
          { label: 'Plantillas de informes', to: '/app/admin/report-templates' },
          { label: 'Auditoría', to: '/app/admin/security-audit' },
          { label: 'Configuración de IA', to: '/app/admin/ai-configuration' },
        ]
      : []),
  ];
  if (administration.length) groups.push({ label: 'Administración', items: administration });
  return groups.filter((group) => group.items.length > 0);
}
