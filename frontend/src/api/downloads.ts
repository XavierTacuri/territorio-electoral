import { apiBlob } from './client';
export const safeFilename = (value: string): string =>
  value.replace(/[^\p{L}\p{N}._-]+/gu, '_').slice(0, 180) || 'informe';
export async function downloadReport(
  path: string,
  fallback: string,
  openPdf = false,
): Promise<void> {
  const { blob, disposition } = await apiBlob(path);
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
  const name = safeFilename(decodeURIComponent(match?.[1] ?? fallback));
  const url = URL.createObjectURL(blob);
  if (openPdf && blob.type === 'application/pdf') window.open(url, '_blank', 'noopener,noreferrer');
  else {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = name;
    anchor.click();
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
