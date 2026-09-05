import type { SessionUser } from '../../auth/permissions';
import { canApproveActivity, canEditActivity } from '../../auth/permissions';
import type { Activity } from './types';

export function activityDetailActions(user: SessionUser | null, activity: Activity) {
  return {
    approve: activity.approval_status === 'PENDING_APPROVAL' && canApproveActivity(user),
    reject: activity.approval_status === 'PENDING_APPROVAL' && canApproveActivity(user),
    correctAndResubmit: activity.approval_status === 'REJECTED' && canEditActivity(user),
    execution: activity.approval_status === 'APPROVED',
  };
}
