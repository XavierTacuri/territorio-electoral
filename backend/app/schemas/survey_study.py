from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

class StudyType(StrEnum): GENERAL_SURVEY="GENERAL_SURVEY"; CNE_EXIT_POLL="CNE_EXIT_POLL"; POLL="POLL"; TRACKING_POLL="TRACKING_POLL"; EXIT_POLL="EXIT_POLL"; OTHER="OTHER"
class StudyStatus(StrEnum): DRAFT="DRAFT"; VALIDATED="VALIDATED"; PUBLISHED="PUBLISHED"; ARCHIVED="ARCHIVED"
class GeographyLevel(StrEnum): CANTON="CANTON"; PARISH="PARISH"
class OptionType(StrEnum): CANDIDATE="CANDIDATE"; UNDECIDED="UNDECIDED"; BLANK="BLANK"; NULL_VOTE="NULL_VOTE"; OTHER="OTHER"; NO_RESPONSE="NO_RESPONSE"
class QuestionType(StrEnum): SINGLE_CHOICE="SINGLE_CHOICE"; MULTIPLE_CHOICE="MULTIPLE_CHOICE"; SCALE="SCALE"; RATING="RATING"; VOTE_INTENTION="VOTE_INTENTION"

def tidy(value: str) -> str:
    value = " ".join(value.split())
    if not value: raise ValueError("El valor no puede estar vacío")
    return value

class StudyBase(BaseModel):
    code: str = Field(min_length=1,max_length=80); name: str = Field(min_length=1,max_length=180); description: str|None=None
    study_type: StudyType; fieldwork_start_date: date; fieldwork_end_date: date; publication_date: date|None=None
    geography_level: GeographyLevel; sample_size_total: int=Field(gt=0); universe_description: str
    sampling_method: str; collection_method: str; confidence_level: Decimal|None=Field(None,ge=0,le=1)
    margin_of_error: Decimal|None=Field(None,ge=0,le=1); pollster_name: str|None=None; sponsor_name: str|None=None
    source_type: str="ESTUDIO"; source_url: HttpUrl|None=None; source_name:str|None=None; source_document:str|None=None; notes: str|None=None; is_official: bool=False
    study_series_code: str|None=None; question_code: str="VOTE_INTENTION"; election_process_id: UUID|None=None
    result_count_notes: str|None=None
    model_config=ConfigDict(extra="forbid")
    @field_validator("code","question_code")
    @classmethod
    def normalize_code(cls,v): return "_".join(tidy(v).upper().replace("-","_").split())
    @field_validator("name","universe_description","sampling_method","collection_method","source_type")
    @classmethod
    def normalize_text(cls,v): return tidy(v)
    @model_validator(mode="after")
    def valid(self):
        if self.fieldwork_start_date>self.fieldwork_end_date: raise ValueError("Las fechas de campo son inválidas")
        if self.study_type==StudyType.TRACKING_POLL and not self.study_series_code: raise ValueError("Tracking requiere código de serie")
        if self.study_type==StudyType.EXIT_POLL and not self.election_process_id: raise ValueError("Exit poll legacy requiere proceso electoral")
        if self.study_type==StudyType.CNE_EXIT_POLL:
            if not self.election_process_id: raise ValueError("Exit poll CNE requiere proceso electoral")
            if not self.source_name or not self.publication_date or not (self.source_url or self.source_document): raise ValueError("Exit poll CNE requiere fuente, fecha de publicación y URL o documento verificable")
        return self

class StudyCreate(StudyBase): pass
class StudyUpdate(BaseModel):
    name:str|None=None; description:str|None=None; publication_date:date|None=None; fieldwork_start_date:date|None=None; fieldwork_end_date:date|None=None
    sample_size_total:int|None=Field(None,gt=0); universe_description:str|None=None; sampling_method:str|None=None; collection_method:str|None=None
    confidence_level:Decimal|None=Field(None,ge=0,le=1); margin_of_error:Decimal|None=Field(None,ge=0,le=1)
    pollster_name:str|None=None; sponsor_name:str|None=None; source_type:str|None=None; source_url:HttpUrl|None=None; source_name:str|None=None; source_document:str|None=None; notes:str|None=None
    is_official:bool|None=None; result_count_notes:str|None=None
    model_config=ConfigDict(extra="forbid")

class TerritoryInput(BaseModel): parish_id:int|None=None; sample_size:int=Field(gt=0); margin_of_error:Decimal|None=Field(None,ge=0,le=1); coverage_notes:str|None=None
class OptionInput(BaseModel):
    question_code:str="Q1"; question_text:str="Pregunta agregada"; question_type:QuestionType=QuestionType.SINGLE_CHOICE
    code:str; label:str; option_type:OptionType=OptionType.OTHER; display_order:int=Field(0,ge=0)
class ResultInput(BaseModel): study_territory_id:UUID; option_id:UUID; response_count:int|None=Field(None,ge=0); percentage:Decimal=Field(ge=0,le=1)
class StudyRead(StudyBase):
    id:UUID; campaign_id:UUID; status:StudyStatus; created_by_user_id:UUID; imported_by_user_id:UUID|None=None; created_at:datetime; updated_at:datetime
    methodology_completeness:str; model_config=ConfigDict(from_attributes=True)
class TerritoryRead(TerritoryInput): id:UUID; study_id:UUID; parish_name:str|None=None; parish_dpa:str|None=None; model_config=ConfigDict(from_attributes=True)
class OptionRead(OptionInput): id:UUID; study_id:UUID; model_config=ConfigDict(from_attributes=True)
class ResultRead(ResultInput): id:UUID; study_id:UUID; option_code:str; option_label:str; option_type:OptionType; created_at:datetime; model_config=ConfigDict(from_attributes=True)
class StudyDetail(StudyRead): territories:list[TerritoryRead]=[]; options:list[OptionRead]=[]; results:list[ResultRead]=[]; exit_poll_warning:str|None=None
class StudyList(BaseModel): items:list[StudyRead]; page:int; page_size:int; total:int; total_pages:int
class ValidationIssue(BaseModel): code:str; message:str; territory_id:UUID|None=None
class ValidationResponse(BaseModel): valid:bool; status:StudyStatus; issues:list[ValidationIssue]; methodology_completeness:str
class ComparisonResponse(BaseModel): comparable:bool; message:str|None=None; studies:list[StudyDetail]
class SurveyImportIssue(BaseModel): row_number:int|None=None; code:str; message:str
class SurveyImportSummary(BaseModel):
    dataset_type:str="SURVEY_AGGREGATE_RESULTS"; mapping_profile:str="CANONICAL_SURVEY_AGGREGATE_RESULT"
    status:str; rows_read:int; rows_valid:int; rows_rejected:int; studies:list[str]; territories:int; options:int; questions:int=0; parishes:list[str]=[]
    errors:list[SurveyImportIssue]=[]
