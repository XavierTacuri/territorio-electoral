"""SQLAlchemy models exported for application and Alembic discovery."""
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.models.territory import Province, Canton, Parish, Community, Sector
from app.models.campaign import Campaign
from app.models.candidate import Candidate
from app.models.assignments import CampaignUser, TerritorialAssignment
__all__ = ["Role", "User", "UserRole", "Province", "Canton", "Parish", "Community", "Sector", "Campaign", "Candidate", "CampaignUser", "TerritorialAssignment"]
from app.models.operational import ActivityType, NeedCategory, TerritorialActivity, ActivityParticipantSummary, CitizenNeed, Commitment, ActivityEvidence

from app.models.survey import Survey, SurveySection, SurveyQuestion, SurveyOption, SurveyResponse, SurveyAnswer, SurveyAnswerOption

from app.models.historical import DataSource, DataImportJob, DataImportError, ElectoralProcess, ElectoralContest, PoliticalOrganization, ElectoralGeography, ElectoralCandidate, ElectoralTurnout, ElectoralCandidateResult, DemographicIndicator, DemographicObservation

from app.models.reports import ReportTemplate, ReportRun, ReportArtifact
from app.models.alerts import AlertRule, OperationalAlert, AlertAcknowledgement
from app.models.security import AuthSession, SecurityAuditEvent
from app.models.survey_study import SurveyStudy, SurveyStudyTerritory, SurveyStudyOption, SurveyStudyResult
from app.models.public_intelligence import PublicSource, PublicIntelligenceItem, PublicItemRevision, PublicSourceFetchRun, PublicTopic, PublicItemTopic, PublicItemTerritory, PublicItemNeedLink
from app.models.entitlement import CampaignFeatureEntitlement, AiUsageEvent
from app.models.territory_ai import TerritoryAIConversation, TerritoryAIMessage
from app.models.organization import Organization, OrganizationMembership, OrganizationSubscription  # noqa: F401
