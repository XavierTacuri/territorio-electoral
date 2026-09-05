import { getFieldDb } from './db';
import type { CachedCampaignInfo } from './types';

// Bridges the online→offline gap for organization_id: it belongs to the
// campaign, not the user, so it must be cached the first time a campaign is
// opened online in order to compute the full {user, organization, campaign}
// owner key later while offline (see useFieldContext).
export async function cacheCampaignInfo(
  campaignId: string,
  organizationId: string,
  name: string,
): Promise<CachedCampaignInfo> {
  const db = await getFieldDb();
  const entry: CachedCampaignInfo = {
    campaign_id: campaignId,
    organization_id: organizationId,
    name,
    fetched_at: new Date().toISOString(),
  };
  await db.put('cachedCampaignInfo', entry);
  return entry;
}

export async function getCachedCampaignInfo(campaignId: string): Promise<CachedCampaignInfo | undefined> {
  const db = await getFieldDb();
  return db.get('cachedCampaignInfo', campaignId);
}
