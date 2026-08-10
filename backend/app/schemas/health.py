from typing import Literal

from pydantic import BaseModel


class RootResponse(BaseModel):
    name: str
    status: Literal["running"]


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    application: str
    database: Literal["connected", "unavailable"]

