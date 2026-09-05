import { useEffect, useState } from 'react';
import { getCachedCampaignInfo } from './campaignInfoRepository';

// AppShell needs an organization_id to compute the pending-sync count for
// the logout warning, but CampaignProvider's `active` is only populated once
// the user has gone through the campaign selector — a direct/deep link
// (exactly how an installed PWA is opened) leaves it null. Fall back to
// whatever this device has already cached for that campaign.
export function useResolvedOrganizationId(
  campaignId: string | undefined,
  activeOrganizationId: string | undefined,
): string | undefined {
  const [fallback, setFallback] = useState<string | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    if (!campaignId || activeOrganizationId) {
      setFallback(undefined);
      return;
    }
    void getCachedCampaignInfo(campaignId).then((info) => {
      if (!cancelled) setFallback(info?.organization_id);
    });
    return () => {
      cancelled = true;
    };
  }, [campaignId, activeOrganizationId]);
  return activeOrganizationId ?? fallback;
}
