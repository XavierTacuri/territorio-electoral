import { useEffect, useState } from 'react';
import { Alert, Button, Snackbar } from '@mui/material';

const DISMISS_KEY = 'territorio.installPromptDismissed';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY)) return;
    const handler = (event: Event) => {
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  if (!deferred) return null;

  async function install() {
    if (!deferred) return;
    await deferred.prompt();
    const choice = await deferred.userChoice;
    if (choice.outcome !== 'accepted') localStorage.setItem(DISMISS_KEY, '1');
    setDeferred(null);
  }

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, '1');
    setDeferred(null);
  }

  return (
    <Snackbar open anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Alert
        severity="info"
        onClose={dismiss}
        action={
          <Button color="inherit" size="small" onClick={() => void install()}>
            INSTALAR
          </Button>
        }
      >
        Instalar Territorio Electoral
      </Alert>
    </Snackbar>
  );
}
