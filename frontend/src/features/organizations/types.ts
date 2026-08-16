export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'ARCHIVED';
  legal_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  country: string;
  timezone: string;
  created_at: string;
  updated_at: string;
  campaign_count: number;
  user_count: number;
  plan_code: 'STANDARD' | 'PRO' | null;
  subscription_status: SubscriptionStatus | null;
  current_role: 'OWNER' | 'ADMIN' | 'MEMBER' | null;
};
export type SubscriptionStatus =
  | 'TRIAL'
  | 'ACTIVE'
  | 'PAST_DUE'
  | 'SUSPENDED'
  | 'EXPIRED'
  | 'CANCELLED';
export type Subscription = {
  id: string;
  organization_id: string;
  plan_code: 'STANDARD' | 'PRO';
  status: SubscriptionStatus;
  starts_at: string | null;
  expires_at: string | null;
  trial_ends_at: string | null;
  max_campaigns: number | null;
  max_users: number | null;
  effective: boolean;
};
export type Member = {
  id: string;
  user_id: string;
  username: string | null;
  email: string | null;
  display_name: string | null;
  organization_role: 'OWNER' | 'ADMIN' | 'MEMBER';
  status: 'ACTIVE' | 'INACTIVE' | 'INVITED';
  created_at: string;
};
export type Usage = {
  campaigns_used: number;
  campaigns_limit: number | null;
  users_used: number;
  users_limit: number | null;
  ai_requests_used: number;
};
export type License = {
  campaign_id: string;
  campaign_name: string;
  commercial_plan: string;
  features: {
    enabled: boolean;
    entitlement_type: string;
    starts_at: string | null;
    expires_at: string | null;
    status: string;
  }[];
};
export type AuditEvent = {
  id: string;
  event_type: string;
  outcome: string;
  created_at: string;
  actor: string | null;
  description: string;
};
