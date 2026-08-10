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
export const canManageUsers = (u: SessionUser | null) => has(u, 'ADMIN');
export const canAdministerCampaigns = (u: SessionUser | null) => has(u, 'ADMIN');
export const canManageCampaign = (u: SessionUser | null) => has(u, 'ADMIN', 'CAMPAIGN_MANAGER');
export const canManageSurvey = canManageCampaign;
export const canCollectSurvey = (u: SessionUser | null) =>
  has(u, 'ADMIN', 'CAMPAIGN_MANAGER', 'TERRITORIAL_COORDINATOR');
export const canRunImports = (u: SessionUser | null) => has(u, 'ADMIN');
export const canImportGeometry = canRunImports;
export const canGenerateReport = (u: SessionUser | null) =>
  has(u, 'ADMIN', 'CAMPAIGN_MANAGER', 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canDeleteReport = canManageCampaign;
export const canEvaluateAlerts = (u: SessionUser | null) =>
  has(u, 'ADMIN', 'CAMPAIGN_MANAGER', 'ANALYST');
export const canAcknowledgeAlert = (u: SessionUser | null) =>
  has(u, 'ADMIN', 'CAMPAIGN_MANAGER', 'TERRITORIAL_COORDINATOR', 'ANALYST');
export const canResolveAlert = canAcknowledgeAlert;
export const canDismissAlert = (u: SessionUser | null) => has(u, 'ADMIN', 'CAMPAIGN_MANAGER');
export const canViewSecurityAudit = canManageUsers;
