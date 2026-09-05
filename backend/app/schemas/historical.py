from datetime import date,datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from pydantic import AnyHttpUrl,BaseModel,ConfigDict,Field,field_validator,model_validator
class DatasetType(StrEnum):CNE_ELECTORAL_RESULTS='CNE_ELECTORAL_RESULTS';CNE_CANDIDATES='CNE_CANDIDATES';CNE_POLITICAL_ORGANIZATIONS='CNE_POLITICAL_ORGANIZATIONS';CNE_TURNOUT='CNE_TURNOUT';CNE_ELECTORAL_ROLL_SNAPSHOT='CNE_ELECTORAL_ROLL_SNAPSHOT';INEC_DEMOGRAPHIC_INDICATORS='INEC_DEMOGRAPHIC_INDICATORS';INEC_POPULATION_PROJECTIONS='INEC_POPULATION_PROJECTIONS';INEC_GEOGRAPHIC_CLASSIFIER='INEC_GEOGRAPHIC_CLASSIFIER';OTHER_AGGREGATED_OFFICIAL='OTHER_AGGREGATED_OFFICIAL';CNE_POLLING_PLACES='CNE_POLLING_PLACES';CNE_ELECTORAL_BOARDS='CNE_ELECTORAL_BOARDS'
def clean(v:str):
 v=' '.join(v.split())
 if not v:raise ValueError('Valor vacío')
 return v
def code(v:str):return '_'.join(clean(v).upper().replace('-','_').split())
class DataSourceCreate(BaseModel):
 code:str;institution:str;dataset_name:str;dataset_type:DatasetType;official_url:AnyHttpUrl|None=None;publication_date:date|None=None;reference_date:date|None=None;reference_year:int|None=Field(None,ge=1900,le=2200);license_or_terms:str|None=None;description:str|None=None;is_official:bool=True;model_config=ConfigDict(extra='forbid');_code=field_validator('code')(code);_names=field_validator('institution','dataset_name')(clean)
class DataSourceUpdate(BaseModel):institution:str|None=None;dataset_name:str|None=None;official_url:AnyHttpUrl|None=None;publication_date:date|None=None;reference_date:date|None=None;reference_year:int|None=None;license_or_terms:str|None=None;description:str|None=None;is_official:bool|None=None;is_active:bool|None=None;model_config=ConfigDict(extra='forbid')
class DataSourceRead(BaseModel):id:UUID;code:str;institution:str;dataset_name:str;dataset_type:DatasetType;official_url:str|None;publication_date:date|None;reference_date:date|None;reference_year:int|None;license_or_terms:str|None;description:str|None;is_official:bool;is_active:bool;model_config=ConfigDict(from_attributes=True)
class DataImportErrorRead(BaseModel):id:UUID;row_number:int|None;column_name:str|None;error_code:str;message:str;rejected_value_preview:str|None;model_config=ConfigDict(from_attributes=True)
class DataImportJobRead(BaseModel):id:UUID;source_id:UUID;dataset_type:str;original_filename:str;file_sha256:str;file_size_bytes:int;status:str;validation_only:bool;rows_read:int;rows_valid:int;rows_inserted:int;rows_updated:int;rows_skipped:int;rows_failed:int;encoding_used:str|None;delimiter_used:str|None;mapping_profile:str|None;error_summary:str|None;model_config=ConfigDict(from_attributes=True)
class DataImportValidationResponse(DataImportJobRead):errors:list[DataImportErrorRead]=[]
class DataImportExecutionResponse(DataImportValidationResponse):pass
class ElectoralProcessCreate(BaseModel):
 code:str;name:str;process_type:str;election_date:date;year:int;status:str='DRAFT';is_final:bool=True;source_id:UUID;description:str|None=None;model_config=ConfigDict(extra='forbid');_code=field_validator('code')(code);_name=field_validator('name')(clean)
 @model_validator(mode='after')
 def year_ok(self):
  if self.year!=self.election_date.year:raise ValueError('El año no coincide con la fecha')
  return self
class ElectoralProcessUpdate(BaseModel):name:str|None=None;status:str|None=None;is_final:bool|None=None;description:str|None=None;is_active:bool|None=None;model_config=ConfigDict(extra='forbid')
class ElectoralProcessRead(BaseModel):id:UUID;code:str;name:str;process_type:str;election_date:date;year:int;status:str;is_final:bool;source_id:UUID;description:str|None;is_active:bool;model_config=ConfigDict(from_attributes=True)
class ElectoralContestCreate(BaseModel):
 office_type:str;name:str;vote_method:str;province_id:int|None=None;canton_id:int|None=None;parish_id:int|None=None;seats:int=Field(1,ge=1);model_config=ConfigDict(extra='forbid')
 @model_validator(mode='after')
 def scope(self):
  if self.office_type=='MAYOR' and not self.canton_id:raise ValueError('Alcaldía requiere cantón')
  if self.office_type=='PARISH_BOARD' and not self.parish_id:raise ValueError('Junta parroquial requiere parroquia')
  return self
class ElectoralContestRead(ElectoralContestCreate):id:UUID;electoral_process_id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class PoliticalOrganizationRead(BaseModel):id:UUID;external_code:str|None;name:str;short_name:str|None;organization_type:str|None;list_number:str|None;scope:str|None;source_id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class ElectoralGeographyRead(BaseModel):id:UUID;electoral_process_id:UUID;level:str;external_code:str;name:str;parent_id:UUID|None;province_id:int|None;canton_id:int|None;parish_id:int|None;zone_code:str|None;precinct_code:str|None;jrv_code:str|None;is_mapped:bool;is_active:bool;model_config=ConfigDict(from_attributes=True)
class ElectoralCandidateRead(BaseModel):id:UUID;electoral_contest_id:UUID;political_organization_id:UUID|None;external_code:str;full_name:str;display_name:str|None;list_number:str|None;ballot_order:int|None;is_winner:bool;source_id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class ElectoralTurnoutRead(BaseModel):id:UUID;electoral_contest_id:UUID;electoral_geography_id:UUID;aggregation_level:str;registered_voters:int;ballots_cast:int;absentee_count:int;valid_votes:int;blank_votes:int;null_votes:int;participation_rate:Decimal|None;absentee_rate:Decimal|None;valid_vote_rate:Decimal|None;blank_vote_rate:Decimal|None;null_vote_rate:Decimal|None;source_id:UUID;is_final:bool
class CandidateResultRead(BaseModel):candidate:ElectoralCandidateRead;organization:PoliticalOrganizationRead|None;votes:int;vote_share:Decimal|None;position:int;is_winner:bool;source_id:UUID;geography_id:UUID|None=None;geography_code:str|None=None;geography_name:str|None=None;geography_level:str|None=None
class TerritorialElectoralSummary(BaseModel):items:list[dict];warnings:list[str]=[]
class ElectoralComparisonRead(BaseModel):process_ids:list[UUID];office_type:str;canton_id:int;aggregation_level:str;items:list[dict];not_comparable:bool=False;warnings:list[str]=[]
class DemographicIndicatorCreate(BaseModel):code:str;name:str;description:str|None=None;category:str;unit:str;value_type:str;source_id:UUID;model_config=ConfigDict(extra='forbid');_code=field_validator('code')(code);_name=field_validator('name')(clean)
class DemographicIndicatorRead(DemographicIndicatorCreate):id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class DemographicObservationRead(BaseModel):id:UUID;demographic_indicator_id:UUID;geography_level:str;province_id:int|None;canton_id:int|None;parish_id:int|None;reference_year:int;value:Decimal;numerator:Decimal|None;denominator:Decimal|None;source_id:UUID;is_official:bool;is_active:bool;model_config=ConfigDict(from_attributes=True)
class DemographicProfileRead(BaseModel):canton_id:int;parish_id:int|None;reference_year:int|None;observations:list[dict]
class ElectoralRollSnapshotRead(BaseModel):id:UUID;source_id:UUID;electoral_process_id:UUID|None;snapshot_date:date;name:str;status:str;is_final:bool;notes:str|None;created_by_user_id:UUID;model_config=ConfigDict(from_attributes=True)
class ElectoralRollSnapshotEntryRead(BaseModel):id:UUID;snapshot_id:UUID;geography_level:str;province_id:int|None;canton_id:int|None;parish_id:int|None;province_dpa:str|None;canton_dpa:str|None;parish_dpa:str|None;registered_voters:int;male_voters:int|None;female_voters:int|None;electoral_zones:int|None;juntas:int|None;model_config=ConfigDict(from_attributes=True)
class ParticipationProjectionResultRead(BaseModel):id:UUID;run_id:UUID;parish_id:int;registered_voters:int;turnout_rate_low:Decimal;turnout_rate_central:Decimal;turnout_rate_high:Decimal;expected_voters_low:int;expected_voters_central:int;expected_voters_high:int;data_quality_status:str;explanation:str;model_config=ConfigDict(from_attributes=True)
class ParticipationProjectionRunRead(BaseModel):id:UUID;campaign_id:UUID|None;electoral_process_id:UUID;snapshot_id:UUID;model_code:str;model_version:str;historical_process_ids:list;parameters:dict;run_date:date;created_by_user_id:UUID;model_config=ConfigDict(from_attributes=True)
class HistoricalElectoralContextRead(BaseModel):campaign_id:UUID;canton:dict;office_type:str;processes:list[dict];turnout_comparison:list[dict];parish_comparison:list[dict];candidate_results:list[dict];data_quality:dict
class DatasetVersionRead(BaseModel):id:UUID;data_source_id:UUID;dataset_type:str;reference_date:date|None;version_label:str;checksum:str;import_job_id:UUID;status:str;activated_at:datetime|None=None;activated_by_user_id:UUID|None=None;superseded_by_id:UUID|None=None;model_config=ConfigDict(from_attributes=True)
class DataHubCatalogEntry(BaseModel):dataset_type:str;dataset_label:str;version_kind:str;version_kind_label:str;sources:list[DataSourceRead];active_version:DatasetVersionRead|None;last_job:DataImportJobRead|None;versions_count:int
class DataHubSummary(BaseModel):active_sources:int;datasets:int;recent_imports:int;imports_with_errors:int;datasets_without_active_version:int
class DataHubCatalogResponse(BaseModel):summary:DataHubSummary;entries:list[DataHubCatalogEntry]
class DatasetDetailResponse(BaseModel):dataset_type:str;dataset_label:str;version_kind:str;version_kind_label:str;sources:list[DataSourceRead];active_version:DatasetVersionRead|None;versions:list[DatasetVersionRead];jobs:list[DataImportJobRead]
class DatasetVersionDiffItem(BaseModel):parish_id:int;previous:int;new:int;delta:int
class DatasetVersionDiff(BaseModel):version_id:UUID;compared_to_id:UUID|None;comparable:bool;metric:str|None=None;previous_value:int|None=None;new_value:int|None=None;delta:int|None=None;items:list[DatasetVersionDiffItem]=[];warnings:list[dict|str]=[]
class ElectoralMilestoneCreate(BaseModel):
 electoral_process_id:UUID;title:str;description:str|None=None;milestone_type:str;starts_at:datetime;ends_at:datetime|None=None;source_id:UUID;source_url:AnyHttpUrl|None=None;model_config=ConfigDict(extra='forbid');_title=field_validator('title')(clean)
 @model_validator(mode='after')
 def range_ok(self):
  if self.ends_at and self.ends_at<self.starts_at:raise ValueError('La fecha de fin debe ser posterior a la fecha de inicio')
  return self
class ElectoralMilestoneUpdate(BaseModel):title:str|None=None;description:str|None=None;starts_at:datetime|None=None;ends_at:datetime|None=None;source_url:AnyHttpUrl|None=None;status:str|None=None;model_config=ConfigDict(extra='forbid')
class ElectoralMilestoneRead(BaseModel):id:UUID;electoral_process_id:UUID;title:str;description:str|None;milestone_type:str;starts_at:datetime;ends_at:datetime|None;source_id:UUID;source_url:str|None;import_job_id:UUID|None;dataset_version_id:UUID|None;is_official:bool;status:str;model_config=ConfigDict(from_attributes=True)
class CalendarEvent(BaseModel):id:str;event_type:str;title:str;description:str|None=None;starts_at:datetime;ends_at:datetime|None=None;start_time:str|None=None;parish_id:int|None=None;parish_name:str|None=None;is_official:bool=False;status:str|None=None;source_name:str|None=None;source_url:str|None=None;deep_link:str|None=None
class CalendarResponse(BaseModel):events:list[CalendarEvent]
