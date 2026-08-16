import { createContext, useContext, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export type ActiveOrganization = {
  id: string;
  name: string;
  slug: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'ARCHIVED';
  plan_code: 'STANDARD' | 'PRO' | null;
  subscription_status: string | null;
  campaign_count: number;
  user_count: number;
  current_role: 'OWNER' | 'ADMIN' | 'MEMBER' | null;
};

type Value = {
  activeOrganization: ActiveOrganization | null;
  setActiveOrganization: (organization: ActiveOrganization | null) => void;
};

const OrganizationContext = createContext<Value | null>(null);

export function OrganizationProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [activeOrganization, setValue] = useState<ActiveOrganization | null>(() => {
    try {
      const stored = sessionStorage.getItem('territorio.activeOrganization');
      return stored ? (JSON.parse(stored) as ActiveOrganization) : null;
    } catch {
      return null;
    }
  });
  const value = useMemo<Value>(
    () => ({
      activeOrganization,
      setActiveOrganization: (organization) => {
        setValue(organization);
        sessionStorage.removeItem('territorio.activeCampaign');
        if (organization)
          sessionStorage.setItem('territorio.activeOrganization', JSON.stringify(organization));
        else sessionStorage.removeItem('territorio.activeOrganization');
        queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'organizations' });
      },
    }),
    [activeOrganization, queryClient],
  );
  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>;
}

export function useActiveOrganization() {
  const value = useContext(OrganizationContext);
  if (!value) throw new Error('OrganizationProvider requerido');
  return value;
}

export function useOptionalOrganization() {
  return useContext(OrganizationContext);
}
