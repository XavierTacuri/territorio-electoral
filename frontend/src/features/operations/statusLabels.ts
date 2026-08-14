export const EXECUTION_STATUS_LABELS = {
  PLANNED: 'Planificada',
  IN_PROGRESS: 'En ejecución',
  COMPLETED: 'Completada',
  CANCELLED: 'Cancelada',
} as const;

export const APPROVAL_STATUS_LABELS = {
  DRAFT: 'Borrador',
  PENDING_APPROVAL: 'Pendiente de aprobación',
  APPROVED: 'Aprobada',
  REJECTED: 'Rechazada',
} as const;

export const OPERATION_STATUS_LABELS: Record<string, string> = {
  ...EXECUTION_STATUS_LABELS,
  ...APPROVAL_STATUS_LABELS,
  PENDING: 'Pendiente',
};

export function operationStatusLabel(status: string) {
  return OPERATION_STATUS_LABELS[status] ?? status.replaceAll('_', ' ');
}
