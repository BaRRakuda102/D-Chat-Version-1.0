from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user import UserResponse


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    room_type: str = Field(default="group")
    description: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500)
    member_ids: list[int] = Field(default_factory=list)

    @field_validator("room_type")
    @classmethod
    def validate_room_type(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"private", "group", "channel"}:
            raise ValueError("Unsupported room type")
        return normalized


class RoomUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500)


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    description: str | None = None
    avatar_url: str | None = None
    owner_id: int | None = None
    member_count: int = 0
    unread: int = 0
    last_message: str | None = None
    created_at: datetime
    updated_at: datetime


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    role: str
    can_send_messages: bool = True
    joined_at: datetime
    user: UserResponse | None = None


class UploadedAttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_url: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=100)
    file_size: int = Field(ge=1)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=4000)
    reply_to_id: int | None = None
    attachments: list[UploadedAttachmentInput] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.strip()

    @field_validator("attachments")
    @classmethod
    def validate_payload(cls, value: list[UploadedAttachmentInput], info) -> list[UploadedAttachmentInput]:
        content = info.data.get("content", "")
        if not content and not value:
            raise ValueError("Message content or attachment is required")
        return value


class AddRoomMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int


class MemberPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_send_messages: bool | None = None
    role: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower().strip()
        if normalized not in {"admin", "member"}:
            raise ValueError("Unsupported membership role")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> "MemberPermissionUpdate":
        if self.can_send_messages is None and self.role is None:
            raise ValueError("At least one permission field must be provided")
        return self


class PrivateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int


class MessageAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_url: str
    file_name: str
    file_type: str
    file_size: int


class MessageReactionSummary(BaseModel):
    emoji: str
    count: int


class ReplyPreview(BaseModel):
    id: int
    content: str
    sender: UserResponse | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    sender_id: int | None
    content: str
    reply_to_id: int | None = None
    reply_to: ReplyPreview | None = None
    sender: UserResponse | None = None
    reactions: list[MessageReactionSummary] = Field(default_factory=list)
    attachments: list[MessageAttachmentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class ReactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emoji: str = Field(min_length=1, max_length=50)


class FriendRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50)


class FriendRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_user_id: int
    to_user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    from_user: UserResponse | None = None
    to_user: UserResponse | None = None


class FriendResponse(BaseModel):
    id: int
    friend_id: int
    status: str
    friend: UserResponse
