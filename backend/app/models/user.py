from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RoleEnum, enum_value_type


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(
        enum_value_type(RoleEnum, name="user_role_enum"),
        default=RoleEnum.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date(), nullable=True)

    owned_rooms = relationship("ChatRoom", back_populates="owner")
    memberships = relationship("ChatMember", back_populates="user", cascade="all, delete-orphan")
    sent_messages = relationship("ChatMessage", back_populates="sender")
    audit_logs = relationship("AuditLog", back_populates="user")
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")
    sent_friend_requests = relationship(
        "FriendRequest",
        foreign_keys="FriendRequest.from_user_id",
        back_populates="from_user",
        cascade="all, delete-orphan",
    )
    received_friend_requests = relationship(
        "FriendRequest",
        foreign_keys="FriendRequest.to_user_id",
        back_populates="to_user",
        cascade="all, delete-orphan",
    )

    @property
    def is_superuser(self) -> bool:
        return self.role == RoleEnum.ADMIN
