from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RoleEnum, User
from app.services.auth import get_user_from_request


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await get_user_from_request(session, request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User | None:
    return await get_user_from_request(session, request)


def require_roles(*roles: RoleEnum) -> Callable[[User], User]:
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return dependency
