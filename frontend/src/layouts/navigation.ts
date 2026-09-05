import type { SessionUser } from '../auth/permissions';

export type OrganizationRole = 'OWNER' | 'ADMIN' | 'MEMBER' | null;
export type NavigationItem = { label: string; to: string };
export type NavigationGroup = { label: string; items: NavigationItem[] };

const hasAnyRole = (user: SessionUser | null, roles: string[]) =>
  !!user && (user.is_superuser || user.roles.some((role) => roles.includes(role.code)));

export const canSeeCampaignAdministration = (user: SessionUser | null) =>
  hasAnyRole(user, ['ADMIN']);

export function buildNavigation(
  user: SessionUser | null,
  organizationRole: OrganizationRole,
  campaignId?: string,
): NavigationGroup[] {
  const campaignPath = (path: string) =>
    campaignId ? `/app/campaigns/${campaignId}/${path}` : '/app/campaigns';
  const platformAdmin = hasAnyRole(user, ['ADMIN']);
  const analyst = hasAnyRole(user, ['ANALYST']);
  const operational = hasAnyRole(user, [
    'CANDIDATE',
    'CAMPAIGN_MANAGER',
    'TERRITORIAL_COORDINATOR',
    'ANALYST',
  ]);
  const detailedAnalysis = platformAdmin || analyst;

  const isFieldCoordinator = hasAnyRole(user, ['TERRITORIAL_COORDINATOR']);

  const groups: NavigationGroup[] = [
    {
      label: 'Inicio',
      items: [
        { label: 'Dashboard', to: campaignPath('dashboard') },
        ...(isFieldCoordinator ? [{ label: 'Operación de campo', to: campaignPath('field') }] : []),
        ...(isFieldCoordinator
          ? [{ label: 'Mi Jornada', to: campaignPath('election-day/my') }]
          : []),
      ],
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
        ...(hasAnyRole(user, [
          'ADMIN',
          'TERRITORIAL_COORDINATOR',
          'ANALYST',
          'CANDIDATE',
          'CAMPAIGN_MANAGER',
        ])
          ? [{ label: 'Centro de Informes', to: campaignPath('reports') }]
          : []),
        ...(hasAnyRole(user, [
          'ADMIN',
          'TERRITORIAL_COORDINATOR',
          'ANALYST',
          'CANDIDATE',
          'CAMPAIGN_MANAGER',
        ])
          ? [{ label: 'Centro de alertas', to: campaignPath('alerts') }]
          : []),
        ...(hasAnyRole(user, [
          'ADMIN',
          'TERRITORIAL_COORDINATOR',
          'ANALYST',
          'CANDIDATE',
          'CAMPAIGN_MANAGER',
        ])
          ? [{ label: 'Preparación para debate', to: campaignPath('debate') }]
          : []),
        ...(hasAnyRole(user, [
          'ADMIN',
          'TERRITORIAL_COORDINATOR',
          'ANALYST',
          'CANDIDATE',
          'CAMPAIGN_MANAGER',
        ])
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
          { label: 'Plantillas de informes', to: '/app/admin/report-templates' },
          { label: 'Auditoría', to: '/app/admin/security-audit' },
          { label: 'Configuración de IA', to: '/app/admin/ai-configuration' },
        ]
      : []),
  ];
  if (administration.length) groups.push({ label: 'Administración', items: administration });
  return groups.filter((group) => group.items.length > 0);
}
