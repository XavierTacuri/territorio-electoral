import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type {
  CachedAgenda,
  CachedAssignment,
  CachedCampaignInfo,
  CachedCatalog,
  CachedElectionDayAssignment,
  OfflineDraft,
  PendingAttachment,
  SessionSnapshot,
  SyncQueueItem,
} from './types';

const DB_NAME = 'territorio-field';
export const DB_VERSION = 2;

interface FieldDB extends DBSchema {
  drafts: {
    key: string;
    value: OfflineDraft;
    indexes: { owner: string; ownerStatus: [string, string] };
  };
  syncQueue: {
    key: string;
    value: SyncQueueItem;
    indexes: { owner: string; status: string };
  };
  cachedAssignments: { key: string; value: CachedAssignment };
  cachedAgenda: { key: string; value: CachedAgenda };
  cachedCampaignInfo: { key: string; value: CachedCampaignInfo };
  catalogs: { key: string; value: CachedCatalog };
  pendingAttachments: {
    key: string;
    value: PendingAttachment;
    indexes: { draft: string; owner: string };
  };
  sessionSnapshot: { key: string; value: SessionSnapshot };
  cachedElectionDayAssignment: { key: string; value: CachedElectionDayAssignment };
}

let dbPromise: Promise<IDBPDatabase<FieldDB>> | null = null;

// Schema upgrades must always add/adjust stores in place. Never call
// indexedDB.deleteDatabase() here: that would silently discard every
// unsynced draft a coordinator has on their device across a deploy.
export function getFieldDb(): Promise<IDBPDatabase<FieldDB>> {
  if (!dbPromise) {
    dbPromise = openDB<FieldDB>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          const drafts = db.createObjectStore('drafts', { keyPath: 'id' });
          drafts.createIndex('owner', 'owner_key');
          drafts.createIndex('ownerStatus', ['owner_key', 'sync_status']);
          const queue = db.createObjectStore('syncQueue', { keyPath: 'id' });
          queue.createIndex('owner', 'owner_key');
          queue.createIndex('status', 'status');
          db.createObjectStore('cachedAssignments', { keyPath: 'owner_key' });
          db.createObjectStore('cachedAgenda', { keyPath: 'owner_key' });
          db.createObjectStore('cachedCampaignInfo', { keyPath: 'campaign_id' });
          db.createObjectStore('catalogs', { keyPath: 'name' });
          const attachments = db.createObjectStore('pendingAttachments', { keyPath: 'id' });
          attachments.createIndex('draft', 'draft_id');
          attachments.createIndex('owner', 'owner_key');
          db.createObjectStore('sessionSnapshot', { keyPath: 'id' });
        }
        if (oldVersion < 2) {
          db.createObjectStore('cachedElectionDayAssignment', { keyPath: 'owner_key' });
        }
      },
    });
  }
  return dbPromise;
}

export type { FieldDB };
