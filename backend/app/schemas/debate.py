from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class ClaimCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_text: str = Field(min_length=3, max_length=1000)
    parish_id: int | None = None


class ClaimEvidenceItem(BaseModel):
    id: str
    title: str
    source_name: str
    evidence_class: str
    source_label: str
    record_date: date | None = None
    external_url: str | None = None


class ClaimCheckResponse(BaseModel):
    claim_text: str
    verdict: str
    verdict_label: str
    evidence: list[ClaimEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
