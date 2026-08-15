import { createContext, useContext, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
export type ActiveCampaign = {
  id: string;
  name: string;
  slug?: string;
  canton_id: number;
  canton_name?: string | null;
  province_id?: number | null;
  province_name?: string | null;
  office_type: string;
  election_name: string;
  election_date: string;
  status: string;
};
type Value = {
  active: ActiveCampaign | null;
  setActive: (campaign: ActiveCampaign | null) => void;
};
const CampaignContext = createContext<Value | null>(null);
export function CampaignProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [active, setValue] = useState<ActiveCampaign | null>(() => {
    try {
      const stored = sessionStorage.getItem('territorio.activeCampaign');
      return stored ? (JSON.parse(stored) as ActiveCampaign) : null;
    } catch {
      return null;
    }
  });
  const value = useMemo(
    () => ({
      active,
      setActive: (campaign: ActiveCampaign | null) => {
        setValue(campaign);
        if (campaign) sessionStorage.setItem('territorio.activeCampaign', JSON.stringify(campaign));
        else sessionStorage.removeItem('territorio.activeCampaign');
        queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'campaigns' });
      },
    }),
    [active, queryClient],
  );
  return <CampaignContext.Provider value={value}>{children}</CampaignContext.Provider>;
}
export function useCampaign() {
  const value = useContext(CampaignContext);
  if (!value) throw new Error('CampaignProvider requerido');
  return value;
}
