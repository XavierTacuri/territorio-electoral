import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

// The service worker (see vite.config.ts) can still be installing on a
// coordinator's very first visit; a route lazy-loaded in that narrow window
// can fail with "Failed to fetch dynamically imported module" even though
// the chunk genuinely exists. This is a one-time, self-healing reload — not
// a change to the service worker's caching strategy — guarded by
// sessionStorage so a real missing-module error (a genuine bug) still
// surfaces instead of reload-looping forever.
const RELOAD_KEY = 'territorio.chunkReloadAttempted';
const STALE_CHUNK_PATTERN = /Failed to fetch dynamically imported module|Importing a module script failed/;

export function lazyWithReload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      return await factory();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      let alreadyAttempted = true;
      try {
        alreadyAttempted = Boolean(sessionStorage.getItem(RELOAD_KEY));
      } catch {
        // sessionStorage unavailable (private mode, etc.) — fall through to rethrow.
      }
      if (STALE_CHUNK_PATTERN.test(message) && !alreadyAttempted) {
        try {
          sessionStorage.setItem(RELOAD_KEY, '1');
        } catch {
          // best-effort only
        }
        window.location.reload();
        return new Promise<never>(() => {});
      }
      throw error;
    }
  });
}
