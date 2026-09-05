import { Alert, Button, Snackbar } from '@mui/material';
import { useRegisterSW } from 'virtual:pwa-register/react';

// registerType: 'prompt' (vite.config.ts) means a new build never activates
// itself — the coordinator must confirm, so an in-progress field form is
// never interrupted mid-edit. The draft is already safe in IndexedDB by the
// time this banner can even appear (autosave writes on every change), but we
// still wait for an explicit tap before reloading.
export function ServiceWorkerUpdateBanner() {
  const { needRefresh: [needRefresh, setNeedRefresh], updateServiceWorker } = useRegisterSW({
    onRegisterError: () => {
      // Installability/offline-shell is a progressive enhancement; a
      // registration failure must never block the app from working online.
    },
  });
  if (!needRefresh) return null;
  return (
    <Snackbar open anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Alert
        severity="info"
        action={
          <Button color="inherit" size="small" onClick={() => void updateServiceWorker(true)}>
            ACTUALIZAR
          </Button>
        }
        onClose={() => setNeedRefresh(false)}
      >
        Nueva versión disponible.
      </Alert>
    </Snackbar>
  );
}
