from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import require_roles
from app.models import ChatRoom, RoleEnum
from app.schemas import AuditLogResponse, RoleUpdateRequest, RoomResponse, SimpleMessageResponse, UserResponse
from app.services import audit as audit_service
from app.services import user as user_service

router = APIRouter()


@router.get("/users", response_model=list[UserResponse])
async def admin_list_users(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    users = await user_service.list_users(session, skip=skip, limit=min(limit, 200))
    return [user_service.serialize_user(user) for user in users]


@router.get("/rooms", response_model=list[RoomResponse])
async def admin_list_rooms(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> list[RoomResponse]:
    result = await session.execute(select(ChatRoom).order_by(ChatRoom.updated_at.desc()).offset(skip).limit(limit))
    rooms = result.scalars().all()
    from app.services import chat as chat_service

    return [await chat_service.serialize_room(session, room, user_id=current_user.id) for room in rooms]


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def admin_audit_logs(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    logs = await audit_service.list_audit_logs(session, skip=skip, limit=min(limit, 200))
    return [AuditLogResponse.model_validate(log) for log in logs]


@router.post("/users/{user_id}/ban", response_model=SimpleMessageResponse)
async def ban_user(
    user_id: int,
    request: Request,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    user = await user_service.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = True
    await session.commit()
    await audit_service.create_audit_log(
        session,
        action="ban_user",
        user_id=current_user.id,
        entity_type="user",
        entity_id=user_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="User banned.")


@router.post("/users/{user_id}/unban", response_model=SimpleMessageResponse)
async def unban_user(
    user_id: int,
    request: Request,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    user = await user_service.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = False
    await session.commit()
    await audit_service.create_audit_log(
        session,
        action="unban_user",
        user_id=current_user.id,
        entity_type="user",
        entity_id=user_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="User unbanned.")


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    request: Request,
    payload: RoleUpdateRequest,
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await user_service.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = RoleEnum(payload.role)
    await session.commit()
    await session.refresh(user)
    await audit_service.create_audit_log(
        session,
        action="update_user_role",
        user_id=current_user.id,
        entity_type="user",
        entity_id=user_id,
        details=payload.role,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return user_service.serialize_user(user)
