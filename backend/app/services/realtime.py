from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMember, ChatMessage, ChatRoom, FriendRequest, FriendStatus, User
from app.services import chat as chat_service
from app.services import user as user_service
from app.websocket_manager import manager


async def _get_room_member_ids(session: AsyncSession, *, room_id: int) -> list[int]:
    result = await session.execute(
        select(ChatMember.user_id).where(ChatMember.room_id == room_id)
    )
    return list(result.scalars().all())


async def _get_friend_ids(session: AsyncSession, *, user_id: int) -> list[int]:
    result = await session.execute(
        select(FriendRequest).where(
            and_(
                FriendRequest.status == FriendStatus.ACCEPTED,
                or_(
                    FriendRequest.from_user_id == user_id,
                    FriendRequest.to_user_id == user_id,
                ),
            )
        )
    )
    friend_ids: list[int] = []
    for friendship in result.scalars().all():
        friend_ids.append(
            friendship.to_user_id if friendship.from_user_id == user_id else friendship.from_user_id
        )
    return friend_ids


def build_message_notification(*, room_name: str, message: ChatMessage) -> str:
    preview = message.content.strip()
    if not preview and message.attachments:
        preview = "Новое вложение"
    if len(preview) > 80:
        preview = f"{preview[:77]}..."
    if not preview:
        preview = "Новое сообщение"
    return f"{room_name}: {preview}"


async def broadcast_room_message(message: ChatMessage) -> None:
    dead_connections = []
    for websocket, room_user_id in manager.get_room_connections(message.room_id):
        serialized = chat_service.serialize_message(message, current_user_id=room_user_id)
        try:
            await websocket.send_json(
                {"type": "message", "message": serialized.model_dump(mode="json")}
            )
        except Exception:
            dead_connections.append(websocket)

    for websocket in dead_connections:
        manager.disconnect(websocket)


async def broadcast_reaction_update(message: ChatMessage) -> None:
    dead_connections = []
    for websocket, room_user_id in manager.get_room_connections(message.room_id):
        serialized = chat_service.serialize_message(message, current_user_id=room_user_id)
        try:
            await websocket.send_json(
                {
                    "type": "reaction_update",
                    "message_id": message.id,
                    "message": serialized.model_dump(mode="json"),
                    "reactions": [reaction.model_dump() for reaction in serialized.reactions],
                }
            )
        except Exception:
            dead_connections.append(websocket)

    for websocket in dead_connections:
        manager.disconnect(websocket)


async def broadcast_read_receipt(*, room_id: int, user_id: int, last_read_message_id: int | None) -> None:
    await manager.broadcast(
        room_id,
        {
            "type": "read_receipt",
            "room_id": room_id,
            "user_id": user_id,
            "last_read_message_id": last_read_message_id,
        },
    )


async def broadcast_room_snapshot(
    session: AsyncSession,
    *,
    room_id: int,
    actor_user_id: int | None = None,
    notification_text: str | None = None,
) -> None:
    room = await session.get(ChatRoom, room_id)
    if not room:
        return

    for member_id in await _get_room_member_ids(session, room_id=room_id):
        room_payload = await chat_service.serialize_room(session, room, user_id=member_id)
        payload: dict[str, object] = {
            "type": "room_snapshot",
            "room": room_payload.model_dump(mode="json"),
        }
        if notification_text and member_id != actor_user_id:
            payload["message"] = notification_text
        await manager.broadcast_to_user(member_id, payload)


async def broadcast_room_snapshot_to_user(
    session: AsyncSession,
    *,
    room_id: int,
    user_id: int,
) -> None:
    room = await session.get(ChatRoom, room_id)
    if not room:
        return

    room_payload = await chat_service.serialize_room(session, room, user_id=user_id)
    await manager.broadcast_to_user(
        user_id,
        {
            "type": "room_snapshot",
            "room": room_payload.model_dump(mode="json"),
        },
    )


async def broadcast_user_presence(session: AsyncSession, *, user_id: int) -> None:
    user = await session.get(User, user_id)
    if not user:
        return

    serialized_user = user_service.serialize_user(user).model_dump(mode="json", exclude_none=True)

    room_ids_result = await session.execute(
        select(ChatMember.room_id).where(ChatMember.user_id == user_id)
    )
    room_ids = set(room_ids_result.scalars().all())

    for room_id in room_ids:
        await manager.broadcast(
            room_id,
            {
                "type": "profile_update",
                "user": serialized_user,
            },
        )
        await broadcast_room_snapshot(session, room_id=room_id)

    for friend_id in await _get_friend_ids(session, user_id=user_id):
        await manager.broadcast_to_user(
            friend_id,
            {
                "type": "profile_update",
                "user": serialized_user,
            },
        )
