import { campaignRoleLabels } from '../../lib/labels';
import type { ActivityActor } from './types';

const rolePriority = ['CANDIDATE', 'CAMPAIGN_MANAGER', 'TERRITORIAL_COORDINATOR', 'ANALYST', 'ADMIN'];

export function formatActivityActor(actor?: ActivityActor | null) {
  if (!actor) return 'Usuario no disponible';
  const name = actor.display_name.trim() || actor.username.trim() || 'Usuario no disponible';
  const roleCode = rolePriority.find((code) => actor.role_codes.includes(code));
  const role = roleCode ? campaignRoleLabels[roleCode] : undefined;
  return role ? `${name} · ${role}` : name;
}
