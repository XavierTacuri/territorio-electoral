from app.services.campaign_access_service import CampaignAccessService
from app.services.campaign_permissions import CAMPAIGN_EXECUTIVE_ROLES
class AlertAccessService:
    def __init__(self,db):self.access=CampaignAccessService(db)
    def require_read(self,campaign_id,user):return self.access.require_access(campaign_id,user)
    def require_evaluate(self,campaign_id,user):
        campaign=self.access.require_access(campaign_id,user);roles={r.code for r in user.roles}
        if not self.access.admin(user) and not roles.intersection(CAMPAIGN_EXECUTIVE_ROLES|{"ANALYST","TERRITORIAL_COORDINATOR"}):raise PermissionError("Sin permisos para evaluar alertas")
        return campaign
    def can_dismiss(self,user):return self.access.admin(user) or bool(CAMPAIGN_EXECUTIVE_ROLES & {r.code for r in user.roles})
    def can_modify(self,user):return self.access.admin(user) or bool({r.code for r in user.roles}&(CAMPAIGN_EXECUTIVE_ROLES|{"ANALYST","TERRITORIAL_COORDINATOR"}))
    def can_approve_activities(self,user):return self.access.admin(user) or bool(CAMPAIGN_EXECUTIVE_ROLES & {r.code for r in user.roles})
    # Candidate/Manager see only two alert families in their experience:
    # activities pending approval and newly published surveys/studies (§23 of
    # the executive-role refinement). This does not apply when the user also
    # holds a broader role (Admin/Analyst), which keeps the full alert catalog.
    AUTHORIZED_CONDITION_TYPES={"ACTIVITY_PENDING_APPROVAL","SURVEY_STUDY_PUBLISHED"}
    def restrict_to_candidate_manager_families(self,user):
        if self.access.admin(user):return False
        roles={r.code for r in user.roles}
        if roles&{"ANALYST"}:return False
        return bool(roles&CAMPAIGN_EXECUTIVE_ROLES)
