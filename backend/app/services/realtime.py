from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMember, ChatMessage, ChatRoom
from app.services import chat as chat_service
from app.websocket_manager import manager


async def _get_room_member_ids(session: AsyncSession, *, room_id: int) -> list[int]:
    result = await session.execute(
        select(ChatMember.user_id).where(ChatMember.room_id == room_id)
    )
    return list(result.scalars().all())


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
    serialized = chat_service.serialize_message(message)
    await manager.broadcast(
        message.room_id,
        {"type": "message", "message": serialized.model_dump(mode="json")},
    )


async def broadcast_reaction_update(message: ChatMessage) -> None:
    serialized = chat_service.serialize_message(message)
    await manager.broadcast(
        message.room_id,
        {
            "type": "reaction_update",
            "message_id": message.id,
            "reactions": [reaction.model_dump() for reaction in serialized.reactions],
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
