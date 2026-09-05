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
export const hasCampaignExecutiveRole = (u: SessionUser | null) => has(u, ...CAMPAIGN_EXECUTIVE_ROLES);
export const canApproveActivity = hasCampaignExecutiveRole;
export const canEditActivity = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR');
export const canResubmitActivity = canEditActivity;
export const canManageUsers = (u: SessionUser | null) => has(u, 'ADMIN');
export const canAdministerCampaigns = (u: SessionUser | null) => has(u, 'ADMIN');
export const canManageCampaign = (u: SessionUser | null) => has(u, 'ADMIN', 'CAMPAIGN_MANAGER');
export const canManageSurvey = (u: SessionUser | null) => has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canManageGeneralSurvey = (u: SessionUser | null) => has(u, 'ADMIN', 'ANALYST');
export const canManageCneExitPoll = (u: SessionUser | null) => has(u, 'ADMIN');
export const canCollectSurvey = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR');
export const canRunImports = (u: SessionUser | null) => has(u, 'ADMIN');
export const canImportGeometry = canRunImports;
export const canViewDataHub = (u: SessionUser | null) => has(u, 'ADMIN', 'ANALYST');
export const canGenerateReport = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canDeleteReport = (u: SessionUser | null) => has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canEvaluateAlerts = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'ANALYST');
export const canAcknowledgeAlert = (u: SessionUser | null) =>
  has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES, 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canResolveAlert = canAcknowledgeAlert;
export const canDismissAlert = (u: SessionUser | null) => has(u, 'ADMIN', ...CAMPAIGN_EXECUTIVE_ROLES);
export const canViewSecurityAudit = canManageUsers;
