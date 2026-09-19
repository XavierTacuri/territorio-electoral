export type SessionUser = {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_superuser: boolean;
  roles: { code: string; name: string }[];
};
const has = (u: SessionUser | null, ...roles: string[]) =>
  !!u && (u.is_superuser || u.roles.some((r) => roles.includes(r.code)));
export const CAMPAIGN_EXECUTIVE_ROLES = ['CANDIDATE', 'CAMPAIGN_MANAGER'] as const;
export const hasCampaignExecutiveRole = (u: SessionUser | null) =>
  has(u, ...CAMPAIGN_EXECUTIVE_ROLES);
export const canApproveActivity = hasCampaignExecutiveRole;
export const canEditActivity = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR');
export const canResubmitActivity = canEditActivity;
export const canManageUsers = (u: SessionUser | null) => has(u, 'ADMIN');
export const canAdministerCampaigns = (u: SessionUser | null) => has(u, 'ADMIN');
export const canManageCampaign = (u: SessionUser | null) => has(u, 'ADMIN', 'CAMPAIGN_MANAGER');
export const canManageSurvey = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canManageGeneralSurvey = (u: SessionUser | null) => has(u, 'ADMIN', 'ANALYST');
export const canManageCneExitPoll = (u: SessionUser | null) => has(u, 'ADMIN');
export const canCollectSurvey = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR');
export const canRunImports = (u: SessionUser | null) => has(u, 'ADMIN');
export const canImportGeometry = canRunImports;
export const canViewDataHub = (u: SessionUser | null) => has(u, 'ADMIN', 'ANALYST');
export const canGenerateReport = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canDeleteReport = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canEvaluateAlerts = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'ANALYST');
export const canAcknowledgeAlert = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canResolveAlert = canAcknowledgeAlert;
export const canDismissAlert = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canViewSecurityAudit = canManageUsers;

// Centro de Control de Jornada Electoral (§7/§12): solo el equipo ejecutivo
// de campaña, o ADMIN — cuya entrada real depende de tener una sesión de
// soporte activa para esa campaña, verificada por el backend en cada
// llamada, nunca solo aquí. Coordinator y Analyst nunca pasan este guard.
export const canAccessElectionDayControlCenter = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);

// TERRITORIAL_COORDINATOR is an operational territorial role: it does not get
// the executive/analyst/admin-facing global modules below, per product
// decision. Other campaign roles keep exactly the access they had before.
const NON_COORDINATOR_ANALYSIS_ROLES = ['ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'ANALYST'] as const;
export const canAccessReportsCenter = (u: SessionUser | null) =>
  has(u, ...NON_COORDINATOR_ANALYSIS_ROLES);
export const canAccessAlertsCenter = (u: SessionUser | null) =>
  has(u, ...NON_COORDINATOR_ANALYSIS_ROLES);
export const canAccessDebateAssistant = (u: SessionUser | null) =>
  has(u, ...NON_COORDINATOR_ANALYSIS_ROLES);
export const canAccessSurveysModule = (u: SessionUser | null) =>
  has(u, ...NON_COORDINATOR_ANALYSIS_ROLES);
// Territorio IA · PRO has no direct sidebar entry for TERRITORIAL_COORDINATOR
// (see navigation.ts), but its route is intentionally left unguarded: the
// Field PWA links coordinators into it as an internal assistant.

// Identifies a genuinely coordinator-only profile for UI-simplification
// decisions (e.g. which Dashboard cards/CTAs to show). Deliberately does NOT
// use `has()`'s superuser-bypass semantics: a superuser, or a user who also
// literally holds ADMIN/CANDIDATE/CAMPAIGN_MANAGER/ANALYST, must keep the
// fuller experience those broader roles/privileges grant, not the reduced
// coordinator one.
export const isCoordinatorOnly = (u: SessionUser | null) =>
  !!u &&
  !u.is_superuser &&
  u.roles.some((r) => r.code === 'TERRITORIAL_COORDINATOR') &&
  !u.roles.some((r) => ['ADMIN', 'CANDIDATE', 'CAMPAIGN_MANAGER', 'ANALYST'].includes(r.code));

// Mirrors AlertAccessService.restrict_to_candidate_manager_families on the
// backend: only a literal Candidate/Manager (no ADMIN/ANALYST role, not a
// superuser) is restricted to the two-family alert view. Admin/Analyst keep
// the full Centro de Alertas even if they also happen to hold this role.
export const isCandidateOrManagerOnly = (u: SessionUser | null) =>
  !!u &&
  !u.is_superuser &&
  !u.roles.some((r) => ['ADMIN', 'ANALYST'].includes(r.code)) &&
  u.roles.some((r) => (CAMPAIGN_EXECUTIVE_ROLES as readonly string[]).includes(r.code));

// Personal de Jornada Electoral invitado (Delegado de recinto / Validador de
// actas, Fase 1B §2): se crea sin ningún UserRole general — su acceso vive
// exclusivamente en ElectionDayAssignment. Un usuario así no debe ver el
// resto de la aplicación (§22): solo la superficie de Jornada Electoral.
export const isElectionDayStaffOnly = (u: SessionUser | null) =>
  !!u && !u.is_superuser && u.roles.length === 0;
