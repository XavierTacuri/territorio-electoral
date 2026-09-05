import { getFieldDb } from './db';
import type { SessionSnapshot } from './types';

// Non-sensitive identity only (id, username, roles, names) — never a token,
// password, or refresh secret. This exists solely so the app shell can
// render for an already-logged-in coordinator on an offline reload; any
// real request still requires a live token obtained online.
export async function saveSessionSnapshot(user: SessionSnapshot['user']): Promise<void> {
  const db = await getFieldDb();
  await db.put('sessionSnapshot', { id: 'current', user, updated_at: new Date().toISOString() });
}

export async function getSessionSnapshot(): Promise<SessionSnapshot | undefined> {
  const db = await getFieldDb();
  return db.get('sessionSnapshot', 'current');
}

export async function clearSessionSnapshot(): Promise<void> {
  const db = await getFieldDb();
  await db.delete('sessionSnapshot', 'current');
}
