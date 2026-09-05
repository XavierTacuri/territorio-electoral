// Minimal cross-component signal for "the local sync queue changed
// somewhere". IndexedDB itself has no change subscription API, and pulling
// in a state-management library just for a pending-count badge would be
// overkill — a plain EventTarget is enough for the handful of listeners
// (AppShell's logout guard, the Field home tile) that need to notice a
// queue mutation made on a different page/component.
const bus = new EventTarget();
const QUEUE_CHANGED = 'queue-changed';

export function notifyQueueChanged(): void {
  bus.dispatchEvent(new Event(QUEUE_CHANGED));
}

export function onQueueChanged(listener: () => void): () => void {
  bus.addEventListener(QUEUE_CHANGED, listener);
  return () => bus.removeEventListener(QUEUE_CHANGED, listener);
}
