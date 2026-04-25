from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import CacheService, get_redis
from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatMember
from app.schemas import SimpleMessageResponse, UserResponse, UserUpdate
from app.services import audit as audit_service
from app.services import realtime as realtime_service
from app.services import user as user_service
from app.websocket_manager import manager

router = APIRouter()


@router.get("/", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    users = await user_service.list_users(session, skip=skip, limit=min(limit, 200))
    return [user_service.serialize_user(user) for user in users]


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user=Depends(get_current_user)) -> UserResponse:
    return user_service.serialize_user(current_user, include_email=True)


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    request: Request,
    payload: UserUpdate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    updated_user = await user_service.update_user_profile(session, current_user, payload)
    public_profile = user_service.serialize_user(updated_user)
    try:
        cache = CacheService(get_redis())
        await user_service.invalidate_cached_user(cache, user_id=updated_user.id)
    except RuntimeError:
        pass
    await audit_service.create_audit_log(
        session,
        action="update_profile",
        user_id=current_user.id,
        entity_type="user",
        entity_id=current_user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    room_ids_result = await session.execute(
        select(ChatMember.room_id).where(ChatMember.user_id == updated_user.id)
    )
    for room_id in set(room_ids_result.scalars().all()):
        await manager.broadcast(
            room_id,
            {
                "type": "profile_update",
                "user": public_profile.model_dump(mode="json", exclude_none=True),
            },
        )
        await realtime_service.broadcast_room_snapshot(session, room_id=room_id)
    return user_service.serialize_user(updated_user, include_email=True)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(
    user_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        cache = CacheService(get_redis())
        cached_user = await user_service.get_cached_user_response(session, cache, user_id=user_id)
    except RuntimeError:
        cached_user = None

    if cached_user:
        return cached_user

    target_user = await user_service.get_user_by_id(session, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_service.serialize_user(target_user)
