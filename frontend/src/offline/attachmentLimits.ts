// Mirrors the backend's first-phase evidence contract exactly (JPEG, PNG,
// PDF; see backend/app/services/evidence_security_service.py and
// EVIDENCE_MAX_FILE_MB). This client-side check is only a fast local
// rejection — the backend re-validates the real file bytes independently
// and is the actual authority.
export const ALLOWED_ATTACHMENT_MIME_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];
export const MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024;

export function validateAttachment(file: File): string | null {
  if (!ALLOWED_ATTACHMENT_MIME_TYPES.includes(file.type)) return 'Formato de archivo no permitido.';
  if (file.size > MAX_ATTACHMENT_SIZE_BYTES) return 'El archivo supera el tamaño máximo permitido (15 MB).';
  return null;
}
