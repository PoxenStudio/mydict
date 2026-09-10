from pydantic import BaseModel, Field


class BootstrapStatusResponse(BaseModel):
    initialized: bool


class AdminSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AdminLoginRequest(BaseModel):
    username: str
    password: str
