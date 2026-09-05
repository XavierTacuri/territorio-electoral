import { useState } from 'react';
import { Button, Snackbar, Alert } from '@mui/material';
import type { ReactNode } from 'react';
import { syncQueue } from '../../offline/syncEngine';
import type { OwnerScope } from '../../offline/types';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

export function SyncNowButton({
  scope,
  onDone,
  icon,
  pendingCount,
}: {
  scope: OwnerScope | null;
  onDone: () => void;
  icon?: ReactNode;
  pendingCount: number;
}) {
  const online = useOnlineStatus();
  const [progress, setProgress] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    if (!scope || running) return;
    setRunning(true);
    setProgress(null);
    try {
      const summary = await syncQueue(scope, ({ index, total }) => setProgress(`Sincronizando ${index} de ${total}...`));
      const parts: string[] = [];
      if (summary.synced > 0) parts.push(`${summary.synced} registro${summary.synced === 1 ? '' : 's'} sincronizado${summary.synced === 1 ? '' : 's'}.`);
      if (summary.conflicts > 0) parts.push(`${summary.conflicts} en conflicto, requieren revisión.`);
      if (summary.failed > 0) parts.push(`${summary.failed} no se pudieron sincronizar.`);
      if (summary.attachmentsSynced > 0)
        parts.push(`${summary.attachmentsSynced} evidencia${summary.attachmentsSynced === 1 ? '' : 's'} sincronizada${summary.attachmentsSynced === 1 ? '' : 's'}.`);
      if (summary.attachmentsFailed > 0)
        parts.push(`${summary.attachmentsFailed} evidencia${summary.attachmentsFailed === 1 ? '' : 's'} requieren revisión.`);
      if (summary.attachmentsPending > 0)
        parts.push(
          `${summary.attachmentsPending} evidencia${summary.attachmentsPending === 1 ? '' : 's'} pendiente${summary.attachmentsPending === 1 ? '' : 's'} de sincronizar.`,
        );
      setResult(parts.length ? parts.join(' ') : 'No había registros pendientes.');
      onDone();
    } finally {
      setProgress(null);
      setRunning(false);
    }
  }

  return (
    <>
      <Button
        size="large"
        variant="outlined"
        startIcon={icon}
        onClick={() => void run()}
        disabled={!online || !scope || running || pendingCount === 0}
      >
        {progress ?? 'Sincronizar ahora'}
      </Button>
      <Snackbar open={Boolean(result)} autoHideDuration={5000} onClose={() => setResult(null)}>
        <Alert severity="info" onClose={() => setResult(null)} sx={{ width: '100%' }}>
          {result}
        </Alert>
      </Snackbar>
    </>
  );
}
