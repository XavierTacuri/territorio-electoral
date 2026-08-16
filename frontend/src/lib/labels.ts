export const organizationRoleLabels = {
  OWNER: 'Propietario',
  ADMIN: 'Administrador',
  MEMBER: 'Miembro',
} as const;

export const organizationStatusLabels = {
  ACTIVE: 'Activa',
  SUSPENDED: 'Suspendida',
  ARCHIVED: 'Archivada',
} as const;

export const memberStatusLabels = {
  ACTIVE: 'Activo',
  INACTIVE: 'Inactivo',
  INVITED: 'Invitado',
} as const;

export const subscriptionStatusLabels = {
  TRIAL: 'Prueba',
  ACTIVE: 'Activa',
  PAST_DUE: 'Pago pendiente',
  SUSPENDED: 'Suspendida',
  EXPIRED: 'Expirada',
  CANCELLED: 'Cancelada',
} as const;

export const entitlementTypeLabels = {
  LICENSE: 'Licencia',
  TRIAL: 'Prueba',
  ADMIN_OVERRIDE: 'Habilitación administrativa',
} as const;

export const entitlementStatusLabels = {
  ENABLED: 'Activa',
  TRIAL: 'Prueba activa',
  EXPIRED: 'Expirada',
  DISABLED: 'No habilitada',
  SCHEDULED: 'Programada',
} as const;

export const featureLabels = {
  TERRITORY_AI: 'Territorio IA',
} as const;

export const territoryAiSourceLabels: Record<string, string> = {
  CNE: 'Consejo Nacional Electoral',
  TURNOUT_MODEL: 'Modelo de participación',
  INEC: 'Instituto Nacional de Estadística y Censos',
  SURVEY_STUDY: 'Estudio de encuesta',
  TERRITORIAL_ACTIVITY: 'Actividad territorial',
  CITIZEN_NEED: 'Necesidad ciudadana',
  COMMITMENT: 'Compromiso',
  PUBLIC_INTELLIGENCE: 'Información pública',
  SYSTEM_METADATA: 'Información metodológica',
};

export const auditEventLabels: Record<string, string> = {
  ORGANIZATION_CREATED: 'Organización creada',
  ORGANIZATION_SUSPENDED: 'Organización suspendida',
  ORGANIZATION_REACTIVATED: 'Organización reactivada',
  ORG_MEMBER_ADDED: 'Miembro agregado',
  ORG_MEMBER_REMOVED: 'Miembro eliminado',
  SUBSCRIPTION_CHANGED: 'Suscripción modificada',
  PLAN_LIMIT_CHANGED: 'Límites del plan modificados',
  ENTITLEMENT_CHANGED: 'Licencia modificada',
};

export const commercialErrorMessages: Record<string, string> = {
  ORGANIZATION_ACCESS_DENIED: 'No tienes acceso a esta organización.',
  ORGANIZATION_SUSPENDED: 'Esta organización está suspendida.',
  PLAN_CAMPAIGN_LIMIT_REACHED: 'Has alcanzado el límite de campañas de tu plan.',
  PLAN_USER_LIMIT_REACHED: 'Has alcanzado el límite de usuarios de tu plan.',
  SUBSCRIPTION_INACTIVE: 'La suscripción de esta organización no está activa.',
  FEATURE_NOT_ENTITLED: 'Esta funcionalidad no está disponible para esta campaña.',
};

export function labelFor<T extends string>(labels: Partial<Record<T, string>>, value: T) {
  return labels[value] ?? 'No disponible';
}
