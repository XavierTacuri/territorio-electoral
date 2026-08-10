from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.user import UserRead


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    type: Literal["access"]
    exp: int
    iat: int


class BrowserLogin(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    model_config = ConfigDict(extra="forbid")


class BrowserToken(Token):
    user: UserRead


class BrowserSession(BaseModel):
    authenticated: bool
    user: UserRead
