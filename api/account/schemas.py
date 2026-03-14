from datetime import datetime
from pydantic import BaseModel, Field


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ApiKeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=50)
    key_value: str = Field(min_length=1)


class ApiKeyResponse(BaseModel):
    id: str
    label: str
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}
