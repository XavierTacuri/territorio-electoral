import { describe, expect, it } from 'vitest';
import * as p from './permissions';
import type { SessionUser } from './permissions';
const user = (code: string, superuser = false): SessionUser => ({
  id: '1',
  username: 'u',
  email: 'u@example.com',
  first_name: 'U',
  last_name: 'T',
  is_active: true,
  is_superuser: superuser,
  roles: [{ code, name: code }],
});
describe('matriz de permisos', () => {
  it.each(['CANDIDATE', 'CAMPAIGN_MANAGER'])('comparte capacidades ejecutivas de campaña para %s', (role) => {
    const executive = user(role);
    expect(p.canApproveActivity(executive)).toBe(true);
    expect(p.canManageSurvey(executive)).toBe(true);
    expect(p.canCollectSurvey(executive)).toBe(true);
    expect(p.canGenerateReport(executive)).toBe(true);
    expect(p.canDeleteReport(executive)).toBe(true);
    expect(p.canEvaluateAlerts(executive)).toBe(true);
    expect(p.canAcknowledgeAlert(executive)).toBe(true);
    expect(p.canDismissAlert(executive)).toBe(true);
  });
  it('analista no aprueba actividades', () => expect(p.canApproveActivity(user('ANALYST'))).toBe(false));
  it('ADMIN gestiona usuarios', () => expect(p.canManageUsers(user('ADMIN'))).toBe(true));
  it('CANDIDATE no gestiona usuarios', () =>
    expect(p.canManageUsers(user('CANDIDATE'))).toBe(false));
  it('superusuario prevalece sobre roles', () =>
    expect(p.canManageUsers(user('CANDIDATE', true))).toBe(true));
  it('manager gestiona campaña', () =>
    expect(p.canManageCampaign(user('CAMPAIGN_MANAGER'))).toBe(true));
  it('analista no gestiona campaña', () =>
    expect(p.canManageCampaign(user('ANALYST'))).toBe(false));
  it('manager diseña encuestas', () =>
    expect(p.canManageSurvey(user('CAMPAIGN_MANAGER'))).toBe(true));
  it('coordinador captura encuestas', () =>
    expect(p.canCollectSurvey(user('TERRITORIAL_COORDINATOR'))).toBe(true));
  it('analista no captura encuestas', () =>
    expect(p.canCollectSurvey(user('ANALYST'))).toBe(false));
  it('solo admin ejecuta importaciones', () => {
    expect(p.canRunImports(user('ADMIN'))).toBe(true);
    expect(p.canRunImports(user('ANALYST'))).toBe(false);
  });
  it('solo admin importa geometría', () => expect(p.canImportGeometry(user('ADMIN'))).toBe(true));
  it('analista genera informes', () => expect(p.canGenerateReport(user('ANALYST'))).toBe(true));
  it('candidato genera informes', () =>
    expect(p.canGenerateReport(user('CANDIDATE'))).toBe(true));
  it('manager elimina informes', () =>
    expect(p.canDeleteReport(user('CAMPAIGN_MANAGER'))).toBe(true));
  it('analista evalúa alertas', () => expect(p.canEvaluateAlerts(user('ANALYST'))).toBe(true));
  it('coordinador reconoce pero no descarta alertas', () => {
    expect(p.canAcknowledgeAlert(user('TERRITORIAL_COORDINATOR'))).toBe(true);
    expect(p.canDismissAlert(user('TERRITORIAL_COORDINATOR'))).toBe(false);
  });
  it('el ejecutivo de campaÃ±a puede gestionar alertas', () => {
    expect(p.canAcknowledgeAlert(user('CANDIDATE'))).toBe(true);
    expect(p.canResolveAlert(user('CANDIDATE'))).toBe(true);
    expect(p.canDismissAlert(user('CANDIDATE'))).toBe(true);
  });
  it('auditoría queda reservada a admin', () => {
    expect(p.canViewSecurityAudit(user('ADMIN'))).toBe(true);
    expect(p.canViewSecurityAudit(user('ANALYST'))).toBe(false);
  });
  it('usuario nulo no recibe permisos', () => expect(p.canGenerateReport(null)).toBe(false));
});
