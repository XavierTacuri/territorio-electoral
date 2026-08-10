from app.models.alerts import AlertRule
from app.repositories.alert_rule_repository import AlertRuleRepository
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import ConflictError,NotFoundError

class AlertRuleService:
    def __init__(self,db):self.db=db;self.repo=AlertRuleRepository(db)
    def list(self):return self.repo.active()
    def update(self,code,configuration,is_active,user):
        if not CampaignAccessService.admin(user):raise PermissionError("Permisos insuficientes")
        rule=self.repo.by_code(code)
        if not rule:raise NotFoundError("Regla no encontrada")
        rule.configuration=configuration;rule.is_active=is_active;self.db.commit();return rule
