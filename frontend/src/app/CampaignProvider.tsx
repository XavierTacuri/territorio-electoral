import { createContext, useContext, useMemo, useState } from 'react';
import { queryClient } from './queryClient';
type Campaign = { id: string; name: string; slug?: string };
type Value = { active: Campaign | null; setActive: (campaign: Campaign | null) => void };
const CampaignContext = createContext<Value | null>(null);
export function CampaignProvider({ children }: { children: React.ReactNode }) {
  const [active, setValue] = useState<Campaign | null>(() => {
    try {
      const stored = sessionStorage.getItem('territorio.activeCampaign');
      return stored ? (JSON.parse(stored) as Campaign) : null;
    } catch {
      return null;
    }
  });
  const value = useMemo(
    () => ({
      active,
      setActive: (campaign: Campaign | null) => {
        setValue(campaign);
        if (campaign) sessionStorage.setItem('territorio.activeCampaign', JSON.stringify(campaign));
        else sessionStorage.removeItem('territorio.activeCampaign');
        queryClient.removeQueries({ queryKey: ['campaign'] });
      },
    }),
    [active],
  );
  return <CampaignContext.Provider value={value}>{children}</CampaignContext.Provider>;
}
export function useCampaign() {
  const value = useContext(CampaignContext);
  if (!value) throw new Error('CampaignProvider requerido');
  return value;
}
