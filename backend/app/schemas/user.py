from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    role: str
    is_online: bool = False
    is_superuser: bool = False
    is_verified: bool = False
    date_of_birth: date | None = None
    age: int | None = None
    created_at: datetime
    updated_at: datetime
    last_seen: datetime | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=500)
    date_of_birth: date | None = None

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value


class RoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"user", "moderator", "admin"}:
            raise ValueError("Unsupported role")
        return normalized
