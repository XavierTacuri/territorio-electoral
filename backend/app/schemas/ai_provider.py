from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AiProviderConfiguration(BaseModel):
    provider: str
    provider_label: str
    model: str | None
    status: Literal["CONNECTED", "NOT_CONFIGURED", "ERROR"]
    api_key_configured: bool


class AiProviderConnectionResult(BaseModel):
    status: Literal["CONNECTED"]
    provider: str
    model: str
    checked_at: datetime
