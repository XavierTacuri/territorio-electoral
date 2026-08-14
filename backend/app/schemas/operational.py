from datetime import date,datetime,time
from enum import StrEnum
from uuid import UUID
from pydantic import AnyHttpUrl,BaseModel,ConfigDict,Field,field_validator,model_validator
class ActivityStatus(StrEnum):PLANNED="PLANNED";IN_PROGRESS="IN_PROGRESS";COMPLETED="COMPLETED";CANCELLED="CANCELLED"
class ApprovalStatus(StrEnum):DRAFT="DRAFT";PENDING_APPROVAL="PENDING_APPROVAL";APPROVED="APPROVED";REJECTED="REJECTED"
class Priority(StrEnum):LOW="LOW";MEDIUM="MEDIUM";HIGH="HIGH";CRITICAL="CRITICAL"
class NeedStatus(StrEnum):
    REPORTED="REPORTED";UNDER_REVIEW="UNDER_REVIEW";VALIDATED="VALIDATED";IN_PLAN="IN_PLAN";CLOSED="CLOSED";ARCHIVED="ARCHIVED"
    IDENTIFIED="IDENTIFIED";INCLUDED_IN_PLAN="INCLUDED_IN_PLAN";DISCARDED="DISCARDED"
class NeedSourceType(StrEnum):ASSEMBLY="ASSEMBLY";COMMUNITY_MEETING="COMMUNITY_MEETING";FIELD_VISIT="FIELD_VISIT";CAMPAIGN_ACTIVITY="CAMPAIGN_ACTIVITY";CITIZEN_REPORT="CITIZEN_REPORT";TEAM_REPORT="TEAM_REPORT";OTHER="OTHER"
class NeedScope(StrEnum):LOCAL="LOCAL";PARISH="PARISH";CANTON="CANTON"
class CommitmentStatus(StrEnum):PENDING="PENDING";IN_PROGRESS="IN_PROGRESS";COMPLETED="COMPLETED";CANCELLED="CANCELLED"
class EvidenceType(StrEnum):PHOTO="PHOTO";VIDEO="VIDEO";DOCUMENT="DOCUMENT";NEWS_LINK="NEWS_LINK";SOCIAL_LINK="SOCIAL_LINK";OTHER="OTHER"
def clean(v:str)->str:
    v=" ".join(v.split())
    if not v:raise ValueError("El valor no puede estar vacío")
    return v
class CatalogBase(BaseModel):
    code:str;name:str;description:str|None=None;is_active:bool=True;display_order:int=0
    model_config=ConfigDict(extra="forbid")
    @field_validator("code")
    @classmethod
    def code_upper(cls,v):return clean(v).upper()
    _name=field_validator("name")(clean)
class ActivityTypeCreate(CatalogBase):pass
class ActivityTypeUpdate(BaseModel):name:str|None=None;description:str|None=None;is_active:bool|None=None;display_order:int|None=None;model_config=ConfigDict(extra="forbid")
class ActivityTypeRead(CatalogBase):id:int;model_config=ConfigDict(from_attributes=True)
class NeedCategoryCreate(CatalogBase):pass
class NeedCategoryUpdate(ActivityTypeUpdate):pass
class NeedCategoryRead(CatalogBase):id:int;model_config=ConfigDict(from_attributes=True)
class TerritorialActivityCreate(BaseModel):
    activity_type_code:str;title:str;description:str|None=None;activity_date:date;status:ActivityStatus=ActivityStatus.PLANNED;parish_id:int;community_id:UUID|None=None;sector_id:UUID|None=None;location_name:str|None=None;latitude:float|None=Field(None,ge=-90,le=90);longitude:float|None=Field(None,ge=-180,le=180);responsible_user_id:UUID|None=None;start_time:time|None=None;end_time:time|None=None
    model_config=ConfigDict(extra="forbid");_title=field_validator("title")(clean)
    @model_validator(mode="after")
    def valid(self):
        if self.sector_id and not self.community_id:raise ValueError("Un sector requiere comunidad")
        if (self.latitude is None)!=(self.longitude is None):raise ValueError("Latitud y longitud deben enviarse juntas")
        if self.activity_date>date.today() and self.status==ActivityStatus.COMPLETED:raise ValueError("Una actividad futura no puede estar completada")
        return self
class TerritorialActivityUpdate(BaseModel):
    activity_type_code:str|None=None;title:str|None=None;description:str|None=None;activity_date:date|None=None;status:ActivityStatus|None=None;parish_id:int|None=None;community_id:UUID|None=None;sector_id:UUID|None=None;location_name:str|None=None;latitude:float|None=Field(None,ge=-90,le=90);longitude:float|None=Field(None,ge=-180,le=180);responsible_user_id:UUID|None=None;start_time:time|None=None;end_time:time|None=None
    model_config=ConfigDict(extra="forbid")
class TerritorialActivitySummary(BaseModel):
    id:UUID;campaign_id:UUID;activity_type_id:int;title:str;activity_date:date;status:ActivityStatus;approval_status:ApprovalStatus;parish_id:int;community_id:UUID|None;sector_id:UUID|None;is_active:bool;created_by_user_id:UUID;start_time:time|None=None;end_time:time|None=None
    model_config=ConfigDict(from_attributes=True)
class TerritorialActivityRead(TerritorialActivitySummary):description:str|None;location_name:str|None;latitude:float|None;longitude:float|None;responsible_user_id:UUID|None;submitted_for_approval_at:datetime|None;submitted_by_user_id:UUID|None;approved_at:datetime|None;approved_by_user_id:UUID|None;rejected_at:datetime|None;rejected_by_user_id:UUID|None;rejection_reason:str|None
class ActivityRejectRequest(BaseModel):
    rejection_reason:str=Field(min_length=1,max_length=1000)
    _reason=field_validator("rejection_reason")(clean)
class TerritorialActivityListResponse(BaseModel):items:list[TerritorialActivitySummary];page:int;page_size:int;total:int;total_pages:int
class ParticipantSummaryUpsert(BaseModel):estimated_attendees:int=Field(0,ge=0);organizations_count:int=Field(0,ge=0);community_leaders_count:int=Field(0,ge=0);campaign_team_count:int=Field(0,ge=0);notes:str|None=None;model_config=ConfigDict(extra="forbid")
class ParticipantSummaryRead(ParticipantSummaryUpsert):id:UUID;activity_id:UUID;model_config=ConfigDict(from_attributes=True)
class CitizenNeedCreate(BaseModel):
    need_category_code:str;title:str;description:str|None=None;mentions_count:int=Field(1,ge=1);priority:Priority=Priority.MEDIUM;urgency:Priority|None=None;status:NeedStatus=NeedStatus.REPORTED;parish_id:int|None=None;source_type:NeedSourceType=NeedSourceType.OTHER;reported_date:date=Field(default_factory=date.today);scope:NeedScope=NeedScope.PARISH;local_sector_description:str|None=None;assigned_to_user_id:UUID|None=None;evidence_notes:str|None=None;source_reference:str|None=None
    model_config=ConfigDict(extra="forbid");_title=field_validator("title")(clean)
    @model_validator(mode="after")
    def local_scope(self):
        if self.scope==NeedScope.LOCAL and not (self.local_sector_description or "").strip():raise ValueError("El alcance local requiere descripción del sector")
        return self
class CitizenNeedUpdate(BaseModel):title:str|None=None;description:str|None=None;mentions_count:int|None=Field(None,ge=1);priority:Priority|None=None;urgency:Priority|None=None;need_category_code:str|None=None;assigned_to_user_id:UUID|None=None;evidence_notes:str|None=None;resolution_notes:str|None=None;source_reference:str|None=None;model_config=ConfigDict(extra="forbid")
class NeedValidationRequest(BaseModel):validation_notes:str|None=None
class CitizenNeedSummary(BaseModel):id:UUID;activity_id:UUID|None;need_category_id:int;title:str;mentions_count:int;priority:Priority;urgency:Priority;status:NeedStatus;parish_id:int;source_type:NeedSourceType;reported_date:date;assigned_to_user_id:UUID|None;is_active:bool;model_config=ConfigDict(from_attributes=True)
class CitizenNeedRead(CitizenNeedSummary):campaign_id:UUID;description:str|None;community_id:UUID|None;sector_id:UUID|None;scope:NeedScope;local_sector_description:str|None;reported_by_user_id:UUID|None;validation_notes:str|None;validated_by_user_id:UUID|None;validated_at:datetime|None;resolution_notes:str|None;evidence_notes:str|None;source_reference:str|None
class CitizenNeedListResponse(BaseModel):items:list[CitizenNeedSummary];page:int;page_size:int;total:int;total_pages:int
class CommitmentCreate(BaseModel):
    activity_id:UUID|None=None;need_id:UUID|None=None;title:str;description:str|None=None;priority:Priority;status:CommitmentStatus=CommitmentStatus.PENDING;due_date:date|None=None;completed_date:date|None=None;responsible_user_id:UUID|None=None;parish_id:int;community_id:UUID|None=None;sector_id:UUID|None=None
    model_config=ConfigDict(extra="forbid");_title=field_validator("title")(clean)
    @model_validator(mode="after")
    def completed(self):
        if self.completed_date and self.status!=CommitmentStatus.COMPLETED:raise ValueError("completed_date requiere estado COMPLETED")
        if self.completed_date and self.completed_date>date.today():raise ValueError("Fecha de cumplimiento futura")
        if self.sector_id and not self.community_id:raise ValueError("Un sector requiere comunidad")
        return self
class CommitmentUpdate(BaseModel):
    title:str|None=None;description:str|None=None;priority:Priority|None=None;status:CommitmentStatus|None=None;due_date:date|None=None;completed_date:date|None=None;responsible_user_id:UUID|None=None;parish_id:int|None=None;community_id:UUID|None=None;sector_id:UUID|None=None
    model_config=ConfigDict(extra="forbid")
class CommitmentSummary(BaseModel):id:UUID;campaign_id:UUID;activity_id:UUID|None;need_id:UUID|None;title:str;priority:Priority;status:CommitmentStatus;due_date:date|None;completed_date:date|None;parish_id:int;is_active:bool;model_config=ConfigDict(from_attributes=True)
class CommitmentRead(CommitmentSummary):description:str|None;responsible_user_id:UUID|None;community_id:UUID|None;sector_id:UUID|None
class CommitmentListResponse(BaseModel):items:list[CommitmentSummary];page:int;page_size:int;total:int;total_pages:int
class ActivityEvidenceCreate(BaseModel):evidence_type:EvidenceType;title:str;description:str|None=None;url:AnyHttpUrl;evidence_date:date|None=None;model_config=ConfigDict(extra="forbid");_title=field_validator("title")(clean)
class ActivityEvidenceUpdate(BaseModel):evidence_type:EvidenceType|None=None;title:str|None=None;description:str|None=None;url:AnyHttpUrl|None=None;evidence_date:date|None=None;model_config=ConfigDict(extra="forbid")
class ActivityEvidenceRead(BaseModel):id:UUID;activity_id:UUID;evidence_type:EvidenceType;title:str;description:str|None;url:str;evidence_date:date|None;is_active:bool;model_config=ConfigDict(from_attributes=True)
class ActivityCountByType(BaseModel):code:str;name:str;count:int
class ActivityCountByParish(BaseModel):parish_id:int;name:str;completed:int;planned:int;estimated_attendees:int
class NeedCountByCategory(BaseModel):code:str;name:str;mentions:int;activities:int;max_priority:str
class NeedCountByParish(BaseModel):parish_id:int;name:str;mentions:int
class CommitmentStatusSummary(BaseModel):pending:int=0;in_progress:int=0;completed:int=0;cancelled:int=0;overdue:int=0
class UncoveredParishRead(BaseModel):id:int;name:str
class OperationalSummaryRead(BaseModel):date_from:date;date_to:date;completed_activities:int;planned_activities:int;cancelled_activities:int;total_activities:int;open_needs:int;parishes_with_commitments:int;estimated_attendees:int;activities_by_type:list[ActivityCountByType];activities_by_parish:list[ActivityCountByParish];top_needs:list[NeedCountByCategory];needs_by_parish:list[NeedCountByParish];commitments:CommitmentStatusSummary;uncovered_parishes:list[UncoveredParishRead];summary_text:str
