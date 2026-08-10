from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator

class SurveyStatus(StrEnum):DRAFT='DRAFT';PUBLISHED='PUBLISHED';CLOSED='CLOSED';ARCHIVED='ARCHIVED'
class TargetScope(StrEnum):CANTON='CANTON';PARISH='PARISH';COMMUNITY='COMMUNITY';SECTOR='SECTOR';ACTIVITY='ACTIVITY'
class QuestionType(StrEnum):SINGLE_CHOICE='SINGLE_CHOICE';MULTIPLE_CHOICE='MULTIPLE_CHOICE';YES_NO='YES_NO';SHORT_TEXT='SHORT_TEXT';LONG_TEXT='LONG_TEXT';INTEGER='INTEGER';DECIMAL='DECIMAL';RATING='RATING'
class SourceChannel(StrEnum):FIELD='FIELD';WEB='WEB';QR='QR';ACTIVITY='ACTIVITY';MANUAL_IMPORT='MANUAL_IMPORT';OTHER='OTHER'
class AgeRange(StrEnum):UNDER_18='UNDER_18';AGE_18_24='AGE_18_24';AGE_25_34='AGE_25_34';AGE_35_44='AGE_35_44';AGE_45_54='AGE_45_54';AGE_55_64='AGE_55_64';AGE_65_PLUS='AGE_65_PLUS';NOT_PROVIDED='NOT_PROVIDED'
def clean(v:str)->str:
    v=' '.join(v.split())
    if not v:raise ValueError('El valor no puede estar vacío')
    return v
def code(v:str)->str:return '_'.join(clean(v).upper().replace('-','_').split())
class SurveyCreate(BaseModel):
    title:str;slug:str;description:str|None=None;instructions:str|None=None;start_date:date|None=None;end_date:date|None=None;target_scope:TargetScope;allow_multiple_submissions:bool=True;anonymous_only:bool=True;show_progress:bool=True;thank_you_message:str|None=None;model_config=ConfigDict(extra='forbid');_title=field_validator('title')(clean)
    @field_validator('slug')
    @classmethod
    def slug_clean(cls,v):return '-'.join(clean(v).lower().split())
    @model_validator(mode='after')
    def valid(self):
        if not self.anonymous_only:raise ValueError('La encuesta debe ser anónima')
        if self.start_date and self.end_date and self.start_date>self.end_date:raise ValueError('Rango de fechas inválido')
        return self
class SurveyUpdate(BaseModel):
    title:str|None=None;slug:str|None=None;description:str|None=None;instructions:str|None=None;start_date:date|None=None;end_date:date|None=None;target_scope:TargetScope|None=None;allow_multiple_submissions:bool|None=None;anonymous_only:bool|None=None;show_progress:bool|None=None;thank_you_message:str|None=None;model_config=ConfigDict(extra='forbid')
    @model_validator(mode='after')
    def valid(self):
        if self.anonymous_only is False:raise ValueError('La encuesta debe ser anónima')
        if self.start_date and self.end_date and self.start_date>self.end_date:raise ValueError('Rango inválido')
        return self
class SurveySummary(BaseModel):id:UUID;campaign_id:UUID;title:str;slug:str;status:SurveyStatus;start_date:date|None;end_date:date|None;target_scope:TargetScope;is_active:bool;model_config=ConfigDict(from_attributes=True)
class SurveyRead(SurveySummary):description:str|None;instructions:str|None;published_date:date|None;closed_date:date|None;allow_multiple_submissions:bool;anonymous_only:bool;show_progress:bool;thank_you_message:str|None
class SurveyDetail(SurveyRead):sections:list[dict]=[];total_valid_responses:int=0
class SurveyListResponse(BaseModel):items:list[SurveySummary];page:int;page_size:int;total:int;total_pages:int
class SurveyPublishResponse(BaseModel):id:UUID;status:SurveyStatus;published_date:date|None
class SurveyCloseResponse(BaseModel):id:UUID;status:SurveyStatus;closed_date:date|None
class SurveySectionCreate(BaseModel):title:str;description:str|None=None;display_order:int=Field(0,ge=0);model_config=ConfigDict(extra='forbid');_title=field_validator('title')(clean)
class SurveySectionUpdate(BaseModel):title:str|None=None;description:str|None=None;display_order:int|None=Field(None,ge=0);model_config=ConfigDict(extra='forbid')
class SurveySectionRead(SurveySectionCreate):id:UUID;survey_id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class SurveyQuestionCreate(BaseModel):
    code:str;question_text:str;help_text:str|None=None;question_type:QuestionType;is_required:bool=False;display_order:int=Field(0,ge=0);allow_other:bool=False;min_value:Decimal|None=None;max_value:Decimal|None=None;min_length:int|None=Field(None,ge=0);max_length:int|None=Field(None,ge=1);min_selections:int|None=Field(None,ge=0);max_selections:int|None=Field(None,ge=1);rating_min:int|None=None;rating_max:int|None=None;rating_min_label:str|None=None;rating_max_label:str|None=None;model_config=ConfigDict(extra='forbid');_text=field_validator('question_text')(clean);_code=field_validator('code')(code)
    @model_validator(mode='after')
    def valid(self):
        if self.min_value is not None and self.max_value is not None and self.min_value>self.max_value:raise ValueError('Rango numérico inválido')
        if self.min_length is not None and self.max_length is not None and self.min_length>self.max_length:raise ValueError('Longitud inválida')
        if self.question_type=='SHORT_TEXT' and (self.max_length or 250)>500:raise ValueError('Texto corto máximo 500')
        if self.question_type=='LONG_TEXT' and (self.max_length or 2000)>5000:raise ValueError('Texto largo máximo 5000')
        if self.question_type=='RATING' and (self.rating_min is None or self.rating_max is None or self.rating_min>=self.rating_max):raise ValueError('Rating inválido')
        if self.min_selections is not None and self.max_selections is not None and self.min_selections>self.max_selections:raise ValueError('Selecciones inválidas')
        return self
class SurveyQuestionUpdate(BaseModel):question_text:str|None=None;help_text:str|None=None;is_required:bool|None=None;display_order:int|None=Field(None,ge=0);allow_other:bool|None=None;min_value:Decimal|None=None;max_value:Decimal|None=None;min_length:int|None=None;max_length:int|None=None;min_selections:int|None=None;max_selections:int|None=None;rating_min:int|None=None;rating_max:int|None=None;rating_min_label:str|None=None;rating_max_label:str|None=None;model_config=ConfigDict(extra='forbid')
class SurveyOptionCreate(BaseModel):code:str;label:str;description:str|None=None;display_order:int=Field(0,ge=0);is_other:bool=False;model_config=ConfigDict(extra='forbid');_code=field_validator('code')(code);_label=field_validator('label')(clean)
class SurveyOptionUpdate(BaseModel):label:str|None=None;description:str|None=None;display_order:int|None=Field(None,ge=0);is_other:bool|None=None;model_config=ConfigDict(extra='forbid')
class SurveyOptionRead(SurveyOptionCreate):id:UUID;question_id:UUID;is_active:bool;model_config=ConfigDict(from_attributes=True)
class SurveyQuestionRead(BaseModel):id:UUID;survey_id:UUID;section_id:UUID;code:str;question_text:str;help_text:str|None;question_type:QuestionType;is_required:bool;display_order:int;allow_other:bool;min_value:Decimal|None;max_value:Decimal|None;min_length:int|None;max_length:int|None;min_selections:int|None;max_selections:int|None;rating_min:int|None;rating_max:int|None;rating_min_label:str|None;rating_max_label:str|None;is_active:bool;model_config=ConfigDict(from_attributes=True)
class SurveyQuestionWithOptions(SurveyQuestionRead):options:list[SurveyOptionRead]=[]
class SurveyAnswerInput(BaseModel):question_code:str;text_value:str|None=None;integer_value:int|None=None;decimal_value:Decimal|None=None;boolean_value:bool|None=None;rating_value:int|None=None;selected_option_codes:list[str]=[];other_text:str|None=None;model_config=ConfigDict(extra='forbid')
class SurveySubmissionCreate(BaseModel):response_date:date;parish_id:int;community_id:UUID|None=None;sector_id:UUID|None=None;activity_id:UUID|None=None;source_channel:SourceChannel;age_range:AgeRange|None=None;submission_key:str|None=Field(None,min_length=8,max_length=250);answers:list[SurveyAnswerInput];model_config=ConfigDict(extra='forbid')
class SurveyAnswerRead(BaseModel):question_code:str;text_value:str|None=None;integer_value:int|None=None;decimal_value:Decimal|None=None;boolean_value:bool|None=None;rating_value:int|None=None;selected_option_codes:list[str]=[];other_text:str|None=None
class SurveyResponseSummary(BaseModel):id:UUID;survey_id:UUID;response_date:date;parish_id:int;community_id:UUID|None;sector_id:UUID|None;activity_id:UUID|None;source_channel:SourceChannel;age_range:AgeRange|None;is_complete:bool;is_valid:bool;invalid_reason:str|None;model_config=ConfigDict(from_attributes=True)
class SurveyResponseRead(SurveyResponseSummary):answers:list[SurveyAnswerRead]=[]
class SurveyResponseListResponse(BaseModel):items:list[SurveyResponseSummary];page:int;page_size:int;total:int;total_pages:int
class SurveyResponseInvalidation(BaseModel):reason:str=Field(min_length=3,max_length=500);model_config=ConfigDict(extra='forbid');_reason=field_validator('reason')(clean)
class SurveyOptionResult(BaseModel):code:str;label:str;count:int;percentage:float|None
class SurveyNumericSummary(BaseModel):count:int;average:Decimal|None;minimum:Decimal|None;maximum:Decimal|None;median:Decimal|None;distribution:dict[str,int]|None=None
class SurveyTextSummary(BaseModel):count:int;non_empty_count:int
class SurveyQuestionResult(BaseModel):code:str;question_text:str;question_type:QuestionType;answered_count:int;options:list[SurveyOptionResult]=[];numeric:SurveyNumericSummary|None=None;text:SurveyTextSummary|None=None
class SurveyTerritorialResult(BaseModel):territory_id:str;territory_name:str;response_count:int;suppressed:bool;result:dict|None=None
class SurveyParticipationSummary(BaseModel):total_responses:int;valid_responses:int;invalid_responses:int;complete_responses:int;responses_by_parish:list[dict];responses_by_channel:list[dict];responses_by_age_range:list[dict];responses_by_date:list[dict];territories_without_responses:list[dict];territories_below_threshold:list[dict]
class SurveyResultsRead(BaseModel):survey_id:UUID;title:str;date_from:date|None;date_to:date|None;total_responses:int;valid_responses:int;invalid_responses:int;complete_responses:int;responses_by_parish:list[dict];responses_by_channel:list[dict];responses_by_age_range:list[dict];question_results:list[SurveyQuestionResult]
class SurveyComparisonRead(BaseModel):level:str;question_code:str;items:list[SurveyTerritorialResult]
