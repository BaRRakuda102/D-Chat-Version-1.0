from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import CacheService
from app.models import User, utcnow
from app.schemas.user import UserResponse, UserUpdate


def calculate_age(date_of_birth: date | None) -> int | None:
    if not date_of_birth:
        return None

    today = date.today()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return max(age, 0)


def serialize_user(user: User, *, include_email: bool = False) -> UserResponse:
    return UserResponse.model_validate(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email if include_email else None,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "role": user.role.value,
            "is_online": user.is_online,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified,
            "date_of_birth": user.date_of_birth,
            "age": calculate_age(user.date_of_birth),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_seen": user.last_seen,
        }
    )


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_username_or_email(session: AsyncSession, value: str) -> User | None:
    result = await session.execute(
        select(User).where(or_(User.username == value, User.email == value))
    )
    return result.scalar_one_or_none()


async def list_users(
    session: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[User]:
    result = await session.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_user_profile(session: AsyncSession, user: User, payload: UserUpdate) -> User:
    if "display_name" in payload.model_fields_set:
        user.display_name = payload.display_name
    if "email" in payload.model_fields_set:
        user.email = payload.email
    if "avatar_url" in payload.model_fields_set:
        user.avatar_url = payload.avatar_url
    if "date_of_birth" in payload.model_fields_set:
        user.date_of_birth = payload.date_of_birth
    user.updated_at = utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def set_user_presence(session: AsyncSession, user: User, *, is_online: bool) -> None:
    user.is_online = is_online
    user.last_seen = utcnow()
    await session.commit()


async def get_cached_user_response(
    session: AsyncSession,
    cache: CacheService,
    *,
    user_id: int,
) -> UserResponse | None:
    cache_key = f"user:profile:{user_id}"
    cached = await cache.get_json(cache_key)
    if cached:
        return UserResponse.model_validate(cached)

    user = await get_user_by_id(session, user_id)
    if not user:
        return None

    serialized = serialize_user(user)
    await cache.set_json(
        cache_key,
        serialized.model_dump(mode="json"),
        settings.PROFILE_CACHE_TTL_SECONDS,
    )
    return serialized


async def invalidate_cached_user(cache: CacheService, *, user_id: int) -> None:
    await cache.delete(f"user:profile:{user_id}")
