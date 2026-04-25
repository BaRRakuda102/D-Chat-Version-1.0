from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatMember, MembershipRole, RoomType, User
from app.schemas import (
    AddRoomMemberRequest,
    MemberPermissionUpdate,
    MemberResponse,
    MessageCreate,
    MessageResponse,
    PrivateRoomRequest,
    RoomCreate,
    RoomResponse,
    RoomUpdate,
    SimpleMessageResponse,
)
from app.services import audit as audit_service
from app.services import chat as chat_service
from app.services import realtime as realtime_service
from app.websocket_manager import manager

router = APIRouter()


async def _ensure_room_admin(
    session: AsyncSession,
    *,
    room_id: int,
    user_id: int,
) -> ChatMember:
    result = await session.execute(
        select(ChatMember).where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
    )
    membership = result.scalar_one_or_none()
    if not membership or membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room admin access required")
    return membership


@router.get("/", response_model=list[RoomResponse])
async def list_rooms(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RoomResponse]:
    rooms = await chat_service.list_user_rooms(session, user_id=current_user.id)
    return [await chat_service.serialize_room(session, room, user_id=current_user.id) for room in rooms]


@router.post("/", response_model=RoomResponse, status_code=201)
async def create_room(
    request: Request,
    payload: RoomCreate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RoomResponse:
    room = await chat_service.create_room(session, owner=current_user, payload=payload)
    await audit_service.create_audit_log(
        session,
        action="create_room",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room.id,
        details=f"Created {payload.room_type} room {payload.name}",
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await realtime_service.broadcast_room_snapshot(session, room_id=room.id)

    invite_message = (
        f'Вас пригласили в канал "{room.name}"'
        if room.type == RoomType.CHANNEL
        else f'Вас добавили в группу "{room.name}"'
    )
    for member_id in {member_id for member_id in payload.member_ids if member_id != current_user.id}:
        invited_room = await chat_service.serialize_room(session, room, user_id=member_id)
        await manager.broadcast_to_user(
            member_id,
            {
                "type": "room_membership_added",
                "room": invited_room.model_dump(mode="json"),
                "message": invite_message,
            },
        )
    return await chat_service.serialize_room(session, room, user_id=current_user.id)


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RoomResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    return await chat_service.serialize_room(session, room, user_id=current_user.id)


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: int,
    request: Request,
    payload: RoomUpdate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RoomResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    if room.type == RoomType.CHANNEL and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can manage the channel")
    if room.owner_id != current_user.id and not current_user.is_superuser:
        await _ensure_room_admin(session, room_id=room_id, user_id=current_user.id)
    room = await chat_service.update_room(session, room=room, payload=payload)
    await audit_service.create_audit_log(
        session,
        action="update_room",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await realtime_service.broadcast_room_snapshot(session, room_id=room.id)
    return await chat_service.serialize_room(session, room, user_id=current_user.id)


@router.delete("/{room_id}", response_model=SimpleMessageResponse)
async def delete_room(
    room_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    member_ids = await chat_service.list_room_member_ids(session, room_id=room_id)
    if room.type != RoomType.PRIVATE and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only room owner can delete the room")
    await chat_service.delete_room(session, room=room)
    await audit_service.create_audit_log(
        session,
        action="delete_room",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    for member_id in member_ids:
        manager.disconnect_user_from_room(user_id=member_id, room_id=room_id)
        await manager.broadcast_to_user(
            member_id,
            {
                "type": "room_membership_removed",
                "room_id": room_id,
                "message": "Чат удален",
            },
        )
    return SimpleMessageResponse(message="Room deleted.")


@router.post("/{room_id}/clear", response_model=SimpleMessageResponse)
async def clear_room(
    room_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    if room.type != RoomType.PRIVATE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only private chats can be cleared")

    await chat_service.clear_room_messages(session, room_id=room_id)
    await audit_service.create_audit_log(
        session,
        action="clear_room",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await manager.broadcast(
        room_id,
        {
            "type": "room_cleared",
            "room_id": room_id,
        },
    )
    await realtime_service.broadcast_room_snapshot(session, room_id=room_id)
    return SimpleMessageResponse(message="Room cleared.")


@router.get("/{room_id}/members", response_model=list[MemberResponse])
async def list_members(
    room_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    members = await chat_service.list_room_members(session, room_id=room_id, user_id=current_user.id)
    return [chat_service.serialize_member(member) for member in members]


@router.post("/{room_id}/members", response_model=SimpleMessageResponse)
async def add_member(
    room_id: int,
    request: Request,
    payload: AddRoomMemberRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    if room.type == RoomType.CHANNEL and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can manage the channel")
    await _ensure_room_admin(session, room_id=room_id, user_id=current_user.id)
    await chat_service.add_room_member(session, room_id=room_id, user_id=payload.user_id)
    target_user = await session.get(User, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    actor_name = current_user.display_name or current_user.username
    target_name = target_user.display_name or target_user.username
    if room.type == RoomType.GROUP:
        message = await chat_service.create_room_activity_message(
            session,
            room_id=room_id,
            sender_id=current_user.id,
            content=f"{actor_name} добавил участника {target_name}",
        )
        await realtime_service.broadcast_room_message(message)

    invited_room = await chat_service.serialize_room(session, room, user_id=payload.user_id)
    invite_message = (
        f'Вас пригласили в канал "{room.name}"'
        if room.type == RoomType.CHANNEL
        else f'Вас добавили в группу "{room.name}"'
    )
    await manager.broadcast_to_user(
        payload.user_id,
        {
            "type": "room_membership_added",
            "room": invited_room.model_dump(mode="json"),
            "message": invite_message,
        },
    )
    await realtime_service.broadcast_room_snapshot(session, room_id=room_id)
    await audit_service.create_audit_log(
        session,
        action="add_member",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room_id,
        details=f"Added user {payload.user_id}",
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Member added.")


@router.delete("/{room_id}/members/{member_user_id}", response_model=SimpleMessageResponse)
async def remove_member(
    room_id: int,
    member_user_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    if room.type == RoomType.CHANNEL and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can manage the channel")
    target_user = await session.get(User, member_user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await _ensure_room_admin(session, room_id=room_id, user_id=current_user.id)
    await chat_service.remove_room_member(session, room_id=room_id, user_id=member_user_id)
    manager.disconnect_user_from_room(user_id=member_user_id, room_id=room_id)

    actor_name = current_user.display_name or current_user.username
    target_name = target_user.display_name or target_user.username
    if room.type == RoomType.GROUP:
        message = await chat_service.create_room_activity_message(
            session,
            room_id=room_id,
            sender_id=current_user.id,
            content=f"{actor_name} исключил участника {target_name}",
        )
        await realtime_service.broadcast_room_message(message)

    await manager.broadcast_to_user(
        member_user_id,
        {
            "type": "room_membership_removed",
            "room_id": room_id,
            "room_name": room.name,
            "message": f'Вы были исключены из чата "{room.name}"',
        },
    )
    await realtime_service.broadcast_room_snapshot(session, room_id=room_id)
    await audit_service.create_audit_log(
        session,
        action="remove_member",
        user_id=current_user.id,
        entity_type="room",
        entity_id=room_id,
        details=f"Removed user {member_user_id}",
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Member removed.")


@router.patch("/{room_id}/members/{member_user_id}", response_model=MemberResponse)
async def update_member_permissions(
    room_id: int,
    member_user_id: int,
    request: Request,
    payload: MemberPermissionUpdate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MemberResponse:
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    if room.type == RoomType.CHANNEL and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can manage the channel")
    if payload.role is not None and room.type != RoomType.GROUP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins can only be assigned inside groups")
    if payload.role is not None and room.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only group owner can manage admin roles")
    await _ensure_room_admin(session, room_id=room_id, user_id=current_user.id)
    member = await chat_service.update_member_permissions(
        session,
        room_id=room_id,
        user_id=member_user_id,
        can_send_messages=payload.can_send_messages,
        role=payload.role,
    )
    await audit_service.create_audit_log(
        session,
        action="update_member_permissions",
        user_id=current_user.id,
        entity_type="room_member",
        entity_id=member_user_id,
        details=f"can_send_messages={payload.can_send_messages}, role={payload.role}",
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return chat_service.serialize_member(member)


@router.get("/{room_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    room_id: int,
    limit: int = 100,
    offset: int = 0,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    messages = await chat_service.list_room_messages(
        session,
        room_id=room_id,
        user_id=current_user.id,
        limit=min(limit, 200),
        offset=offset,
    )
    await realtime_service.broadcast_room_snapshot_to_user(
        session,
        room_id=room_id,
        user_id=current_user.id,
    )
    return [chat_service.serialize_message(message) for message in messages]


@router.post("/{room_id}/messages", response_model=MessageResponse)
async def create_message(
    room_id: int,
    request: Request,
    payload: MessageCreate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    message = await chat_service.create_message(
        session,
        room_id=room_id,
        sender=current_user,
        payload=payload,
    )
    room = await chat_service.get_room_for_user(session, room_id=room_id, user_id=current_user.id)
    await realtime_service.broadcast_room_message(message)
    await realtime_service.broadcast_room_snapshot(
        session,
        room_id=room_id,
        actor_user_id=current_user.id,
        notification_text=realtime_service.build_message_notification(
            room_name=room.name,
            message=message,
        ),
    )
    await audit_service.create_audit_log(
        session,
        action="send_message",
        user_id=current_user.id,
        entity_type="message",
        entity_id=message.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return chat_service.serialize_message(message)


@router.post("/{room_id}/read", response_model=SimpleMessageResponse)
async def mark_room_read(
    room_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await chat_service.mark_room_read(session, room_id=room_id, user_id=current_user.id)
    await realtime_service.broadcast_room_snapshot_to_user(
        session,
        room_id=room_id,
        user_id=current_user.id,
    )
    return SimpleMessageResponse(message="Room marked as read.")


@router.post("/private", response_model=RoomResponse)
async def get_or_create_private_room(
    payload: PrivateRoomRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RoomResponse:
    room = await chat_service.get_or_create_private_room(
        session,
        user_id=current_user.id,
        target_user_id=payload.user_id,
    )
    return await chat_service.serialize_room(session, room, user_id=current_user.id)
