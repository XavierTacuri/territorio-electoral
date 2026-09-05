import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { cacheAssignments, getCachedAssignments } from '../../offline/assignmentsRepository';
import { cacheCampaignInfo, getCachedCampaignInfo } from '../../offline/campaignInfoRepository';
import type { OwnerScope } from '../../offline/types';
import { useOnlineStatus } from '../../offline/useOnlineStatus';

type CampaignRef = { id: string; name: string; organization_id: string };
type AssignmentRead = { parish_id: number };
type ParishRef = { id: number; name: string };

export type FieldContext = {
  loading: boolean;
  online: boolean;
  scope: OwnerScope | null;
  campaignName: string | null;
  parishes: { parish_id: number; parish_name: string }[];
  fromCache: boolean;
  cachedAt: string | null;
  error: string | null;
};

const EMPTY: FieldContext = {
  loading: true,
  online: true,
  scope: null,
  campaignName: null,
  parishes: [],
  fromCache: false,
  cachedAt: null,
  error: null,
};

export function useFieldContext(): FieldContext {
  const { campaignId = '' } = useParams();
  const { user } = useAuth();
  const online = useOnlineStatus();
  const [state, setState] = useState<FieldContext>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!user || !campaignId) return;
      setState((prev) => ({ ...prev, loading: true, error: null }));
      if (online) {
        try {
          const campaign = await apiRequest<CampaignRef>(`/campaigns/${campaignId}`);
          const assignments = await apiRequest<AssignmentRead[]>(
            `/campaigns/${campaignId}/territorial-assignments`,
          );
          const uniqueParishIds = [...new Set(assignments.map((a) => a.parish_id))];
          const parishes = await Promise.all(
            uniqueParishIds.map((id) => apiRequest<ParishRef>(`/parishes/${id}`)),
          );
          const scope: OwnerScope = {
            user_id: user.id,
            organization_id: campaign.organization_id,
            campaign_id: campaignId,
          };
          const resolved = parishes.map((p) => ({ parish_id: p.id, parish_name: p.name }));
          await cacheCampaignInfo(campaignId, campaign.organization_id, campaign.name);
          await cacheAssignments(scope, resolved);
          if (!cancelled)
            setState({
              loading: false,
              online,
              scope,
              campaignName: campaign.name,
              parishes: resolved,
              fromCache: false,
              cachedAt: null,
              error: null,
            });
          return;
        } catch {
          // fall through to the offline cache below
        }
      }
      // Offline, or the online fetch failed: only ever show territories this
      // device already fetched and cached while authorized — never invent
      // organization_id or scope from thin air.
      const campaignInfo = await getCachedCampaignInfo(campaignId);
      if (!campaignInfo) {
        if (!cancelled)
          setState({
            ...EMPTY,
            loading: false,
            online,
            error: 'Sin datos guardados en este dispositivo para este territorio todavía.',
          });
        return;
      }
      const scope: OwnerScope = {
        user_id: user.id,
        organization_id: campaignInfo.organization_id,
        campaign_id: campaignId,
      };
      const cached = await getCachedAssignments(scope);
      if (!cancelled)
        setState({
          loading: false,
          online,
          scope,
          campaignName: campaignInfo.name,
          parishes: cached?.parishes ?? [],
          fromCache: true,
          cachedAt: cached?.fetched_at ?? null,
          error: cached
            ? null
            : 'Sin datos guardados en este dispositivo para este territorio todavía.',
        });
    }
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId, user?.id, online]);

  return state;
}
