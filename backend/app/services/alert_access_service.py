from app.services.campaign_access_service import CampaignAccessService
class AlertAccessService:
    def __init__(self,db):self.access=CampaignAccessService(db)
    def require_read(self,campaign_id,user):return self.access.require_access(campaign_id,user)
    def require_evaluate(self,campaign_id,user):
        campaign=self.access.require_access(campaign_id,user);roles={r.code for r in user.roles}
        if not self.access.admin(user) and not roles.intersection({"CAMPAIGN_MANAGER","ANALYST","TERRITORIAL_COORDINATOR"}):raise PermissionError("Sin permisos para evaluar alertas")
        return campaign
    def can_dismiss(self,user):return self.access.admin(user) or "CAMPAIGN_MANAGER" in {r.code for r in user.roles}
    def can_modify(self,user):return self.access.admin(user) or bool({r.code for r in user.roles}&{"CAMPAIGN_MANAGER","ANALYST","TERRITORIAL_COORDINATOR"})
