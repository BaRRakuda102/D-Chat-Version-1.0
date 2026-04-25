from __future__ import annotations

from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ChatMember,
    ChatMessage,
    ChatRoom,
    FriendRequest,
    FriendStatus,
    MembershipRole,
    MessageAttachment,
    MessageReaction,
    RoomType,
    User,
    utcnow,
)
from app.schemas.chat import (
    FriendRequestResponse,
    FriendResponse,
    MemberResponse,
    MessageAttachmentResponse,
    MessageCreate,
    MessageReactionSummary,
    MessageResponse,
    ReplyPreview,
    RoomResponse,
)
from app.services.user import serialize_user


async def _ensure_room_member(session: AsyncSession, *, room_id: int, user_id: int) -> ChatMember:
    result = await session.execute(
        select(ChatMember)
        .options(selectinload(ChatMember.user))
        .where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room access denied")
    return membership


async def _resolve_allowed_member_ids(
    session: AsyncSession,
    *,
    owner_id: int,
    member_ids: list[int],
) -> set[int]:
    requested_member_ids = {member_id for member_id in member_ids if member_id != owner_id}
    if not requested_member_ids:
        return set()

    friendships_result = await session.execute(
        select(FriendRequest)
        .where(
            and_(
                FriendRequest.status == FriendStatus.ACCEPTED,
                or_(
                    and_(
                        FriendRequest.from_user_id == owner_id,
                        FriendRequest.to_user_id.in_(requested_member_ids),
                    ),
                    and_(
                        FriendRequest.to_user_id == owner_id,
                        FriendRequest.from_user_id.in_(requested_member_ids),
                    ),
                ),
            )
        )
    )

    allowed_member_ids: set[int] = set()
    for friendship in friendships_result.scalars().all():
        counterpart_id = (
            friendship.to_user_id if friendship.from_user_id == owner_id else friendship.from_user_id
        )
        allowed_member_ids.add(counterpart_id)

    if allowed_member_ids != requested_member_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only accepted friends can be added to groups or channels",
        )

    return allowed_member_ids


def serialize_reactions(reactions: list[MessageReaction]) -> list[MessageReactionSummary]:
    counter = Counter(reaction.emoji for reaction in reactions)
    return [
        MessageReactionSummary(emoji=emoji, count=count)
        for emoji, count in sorted(counter.items(), key=lambda item: item[0])
    ]


def serialize_message(message: ChatMessage) -> MessageResponse:
    reply_preview = None
    if message.reply_to:
        reply_preview = ReplyPreview(
            id=message.reply_to.id,
            content=message.reply_to.content,
            sender=serialize_user(message.reply_to.sender) if message.reply_to.sender else None,
        )

    return MessageResponse(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        content=message.content,
        reply_to_id=message.reply_to_id,
        reply_to=reply_preview,
        sender=serialize_user(message.sender) if message.sender else None,
        reactions=serialize_reactions(list(message.reactions)),
        attachments=[
            MessageAttachmentResponse.model_validate(attachment)
            for attachment in message.attachments
        ],
        created_at=message.created_at,
        updated_at=message.updated_at,
        is_deleted=message.is_deleted,
    )


async def serialize_room(
    session: AsyncSession,
    room: ChatRoom,
    *,
    user_id: int | None = None,
) -> RoomResponse:
    member_count_result = await session.execute(select(func.count(ChatMember.id)).where(ChatMember.room_id == room.id))
    last_message_result = await session.execute(
        select(ChatMessage)
        .where(and_(ChatMessage.room_id == room.id, ChatMessage.is_deleted.is_(False)))
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    last_message = last_message_result.scalar_one_or_none()
    unread_count = 0
    room_name = room.name
    room_avatar_url = room.avatar_url

    if user_id is not None:
        membership_result = await session.execute(
            select(ChatMember).where(and_(ChatMember.room_id == room.id, ChatMember.user_id == user_id))
        )
        membership = membership_result.scalar_one_or_none()
        if membership:
            unread_query = select(func.count(ChatMessage.id)).where(
                and_(
                    ChatMessage.room_id == room.id,
                    ChatMessage.is_deleted.is_(False),
                    ChatMessage.sender_id != user_id,
                )
            )
            if membership.last_read_message_id:
                unread_query = unread_query.where(ChatMessage.id > membership.last_read_message_id)
            unread_result = await session.execute(unread_query)
            unread_count = unread_result.scalar_one()

        if room.type == RoomType.PRIVATE:
            counterpart_result = await session.execute(
                select(User)
                .join(ChatMember, ChatMember.user_id == User.id)
                .where(and_(ChatMember.room_id == room.id, ChatMember.user_id != user_id))
                .limit(1)
            )
            counterpart = counterpart_result.scalar_one_or_none()
            if counterpart:
                room_name = counterpart.display_name or counterpart.username
                room_avatar_url = counterpart.avatar_url

    return RoomResponse(
        id=room.id,
        name=room_name,
        type=room.type.value,
        description=room.description,
        avatar_url=room_avatar_url,
        owner_id=room.owner_id,
        member_count=member_count_result.scalar_one(),
        unread=unread_count,
        last_message=last_message.content if last_message else None,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


async def create_room(session: AsyncSession, *, owner: User, payload) -> ChatRoom:
    if payload.room_type == RoomType.GROUP.value and not payload.member_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A group must include at least one invited participant",
        )

    allowed_member_ids = await _resolve_allowed_member_ids(
        session,
        owner_id=owner.id,
        member_ids=payload.member_ids,
    )

    room_type = RoomType(payload.room_type)
    room = ChatRoom(
        name=payload.name,
        type=room_type,
        description=payload.description,
        avatar_url=payload.avatar_url,
        owner_id=owner.id,
    )
    session.add(room)
    await session.flush()

    session.add(
        ChatMember(
            room_id=room.id,
            user_id=owner.id,
            role=MembershipRole.OWNER,
            can_send_messages=True,
        )
    )

    for member_id in allowed_member_ids:
        session.add(
            ChatMember(
                room_id=room.id,
                user_id=member_id,
                role=MembershipRole.MEMBER,
                can_send_messages=room_type != RoomType.CHANNEL,
            )
        )

    await session.commit()
    await session.refresh(room)
    return room


async def list_user_rooms(session: AsyncSession, *, user_id: int) -> list[ChatRoom]:
    result = await session.execute(
        select(ChatRoom)
        .join(ChatMember, ChatMember.room_id == ChatRoom.id)
        .where(ChatMember.user_id == user_id)
        .order_by(ChatRoom.updated_at.desc())
    )
    return list(result.scalars().unique().all())


async def mark_room_read(session: AsyncSession, *, room_id: int, user_id: int) -> None:
    membership = await _ensure_room_member(session, room_id=room_id, user_id=user_id)

    last_message_result = await session.execute(
        select(ChatMessage.id)
        .where(and_(ChatMessage.room_id == room_id, ChatMessage.is_deleted.is_(False)))
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    last_message_id = last_message_result.scalar_one_or_none()
    membership.last_read_message_id = last_message_id
    await session.commit()


async def get_room_for_user(session: AsyncSession, *, room_id: int, user_id: int) -> ChatRoom:
    await _ensure_room_member(session, room_id=room_id, user_id=user_id)
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


async def update_room(session: AsyncSession, *, room: ChatRoom, payload) -> ChatRoom:
    if payload.name is not None:
        room.name = payload.name
    if payload.description is not None:
        room.description = payload.description
    if payload.avatar_url is not None:
        room.avatar_url = payload.avatar_url
    room.updated_at = utcnow()
    await session.commit()
    await session.refresh(room)
    return room


async def delete_room(session: AsyncSession, *, room: ChatRoom) -> None:
    await session.delete(room)
    await session.commit()


async def list_room_member_ids(session: AsyncSession, *, room_id: int) -> list[int]:
    result = await session.execute(
        select(ChatMember.user_id).where(ChatMember.room_id == room_id)
    )
    return list(result.scalars().all())


async def clear_room_messages(session: AsyncSession, *, room_id: int) -> None:
    memberships_result = await session.execute(
        select(ChatMember).where(ChatMember.room_id == room_id)
    )
    for membership in memberships_result.scalars().all():
        membership.last_read_message_id = None

    messages_result = await session.execute(
        select(ChatMessage).where(ChatMessage.room_id == room_id)
    )
    for message in messages_result.scalars().all():
        await session.delete(message)

    room = await session.get(ChatRoom, room_id)
    if room:
        room.updated_at = utcnow()

    await session.commit()


async def list_room_members(session: AsyncSession, *, room_id: int, user_id: int) -> list[ChatMember]:
    await _ensure_room_member(session, room_id=room_id, user_id=user_id)
    result = await session.execute(
        select(ChatMember)
        .options(selectinload(ChatMember.user))
        .where(ChatMember.room_id == room_id)
        .order_by(ChatMember.joined_at.asc())
    )
    return list(result.scalars().all())


async def add_room_member(session: AsyncSession, *, room_id: int, user_id: int) -> None:
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    existing_result = await session.execute(
        select(ChatMember).where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
    )
    if existing_result.scalar_one_or_none():
        return

    target_user = await session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    session.add(
        ChatMember(
            room_id=room_id,
            user_id=user_id,
            role=MembershipRole.MEMBER,
            can_send_messages=room.type != RoomType.CHANNEL,
        )
    )
    await session.commit()


async def create_room_activity_message(
    session: AsyncSession,
    *,
    room_id: int,
    sender_id: int,
    content: str,
) -> ChatMessage:
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    message = ChatMessage(
        room_id=room_id,
        sender_id=sender_id,
        content=content,
    )
    session.add(message)
    await session.flush()

    membership_result = await session.execute(
        select(ChatMember).where(and_(ChatMember.room_id == room_id, ChatMember.user_id == sender_id))
    )
    membership = membership_result.scalar_one_or_none()
    if membership:
        membership.last_read_message_id = message.id

    room.updated_at = utcnow()
    await session.commit()
    return await get_message_for_user(session, message_id=message.id, user_id=sender_id)


async def remove_room_member(session: AsyncSession, *, room_id: int, user_id: int) -> None:
    result = await session.execute(
        select(ChatMember).where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await session.delete(membership)
    await session.commit()


async def get_or_create_private_room(session: AsyncSession, *, user_id: int, target_user_id: int) -> ChatRoom:
    if user_id == target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create private room with yourself")

    candidate_room_ids = (
        select(ChatMember.room_id)
        .where(ChatMember.user_id.in_([user_id, target_user_id]))
        .group_by(ChatMember.room_id)
        .having(func.count(ChatMember.user_id.distinct()) == 2)
    )
    existing_result = await session.execute(
        select(ChatRoom)
        .where(ChatRoom.type == RoomType.PRIVATE)
        .where(ChatRoom.id.in_(candidate_room_ids))
    )
    existing_room = existing_result.scalar_one_or_none()
    if existing_room:
        return existing_room

    target_user = await session.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    room = ChatRoom(
        name=target_user.display_name or target_user.username,
        type=RoomType.PRIVATE,
        owner_id=user_id,
    )
    session.add(room)
    await session.flush()
    session.add(ChatMember(room_id=room.id, user_id=user_id, role=MembershipRole.OWNER))
    session.add(ChatMember(room_id=room.id, user_id=target_user_id, role=MembershipRole.MEMBER))
    await session.commit()
    await session.refresh(room)
    return room


async def list_room_messages(
    session: AsyncSession,
    *,
    room_id: int,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[ChatMessage]:
    await _ensure_room_member(session, room_id=room_id, user_id=user_id)
    result = await session.execute(
        select(ChatMessage)
        .options(
            selectinload(ChatMessage.sender),
            selectinload(ChatMessage.reply_to).selectinload(ChatMessage.sender),
            selectinload(ChatMessage.attachments),
            selectinload(ChatMessage.reactions),
        )
        .where(and_(ChatMessage.room_id == room_id, ChatMessage.is_deleted.is_(False)))
        .order_by(ChatMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    messages = list(result.scalars().unique().all())
    messages.reverse()
    await mark_room_read(session, room_id=room_id, user_id=user_id)
    return messages


async def get_message_for_user(session: AsyncSession, *, message_id: int, user_id: int) -> ChatMessage:
    result = await session.execute(
        select(ChatMessage)
        .options(
            selectinload(ChatMessage.sender),
            selectinload(ChatMessage.reply_to).selectinload(ChatMessage.sender),
            selectinload(ChatMessage.attachments),
            selectinload(ChatMessage.reactions),
            selectinload(ChatMessage.room).selectinload(ChatRoom.members),
        )
        .where(ChatMessage.id == message_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    member_ids = {member.user_id for member in message.room.members}
    if user_id not in member_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Message access denied")
    return message


async def create_message(
    session: AsyncSession,
    *,
    room_id: int,
    sender: User,
    payload: MessageCreate,
) -> ChatMessage:
    membership = await _ensure_room_member(session, room_id=room_id, user_id=sender.id)
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if room.type == RoomType.CHANNEL and room.owner_id != sender.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the channel owner can publish messages",
        )
    if not membership.can_send_messages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are muted in this chat",
        )

    reply_to = None
    if payload.reply_to_id:
        reply_result = await session.execute(
            select(ChatMessage).where(
                and_(ChatMessage.id == payload.reply_to_id, ChatMessage.room_id == room_id)
            )
        )
        reply_to = reply_result.scalar_one_or_none()
        if not reply_to:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reply target not found")

    message = ChatMessage(
        room_id=room_id,
        sender_id=sender.id,
        content=payload.content,
        reply_to_id=reply_to.id if reply_to else None,
    )
    session.add(message)
    await session.flush()

    for attachment in payload.attachments:
        session.add(
            MessageAttachment(
                message_id=message.id,
                file_url=attachment.file_url,
                file_name=attachment.file_name,
                file_type=attachment.file_type,
                file_size=attachment.file_size,
            )
        )

    room.updated_at = utcnow()
    membership.last_read_message_id = message.id
    await session.commit()
    return await get_message_for_user(session, message_id=message.id, user_id=sender.id)


async def delete_message(session: AsyncSession, *, message: ChatMessage) -> None:
    message.is_deleted = True
    message.updated_at = utcnow()
    await session.commit()


async def add_reaction(
    session: AsyncSession,
    *,
    message_id: int,
    user_id: int,
    emoji: str,
) -> ChatMessage:
    message = await get_message_for_user(session, message_id=message_id, user_id=user_id)
    existing_result = await session.execute(
        select(MessageReaction).where(
            and_(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
        )
    )
    if not existing_result.scalar_one_or_none():
        session.add(MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji))
        await session.commit()
    return await get_message_for_user(session, message_id=message_id, user_id=user_id)


async def send_friend_request(session: AsyncSession, *, from_user: User, target_username: str) -> FriendRequest:
    target_result = await session.execute(select(User).where(User.username == target_username))
    target_user = target_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target_user.id == from_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add yourself")

    existing_result = await session.execute(
        select(FriendRequest).where(
            or_(
                and_(FriendRequest.from_user_id == from_user.id, FriendRequest.to_user_id == target_user.id),
                and_(FriendRequest.from_user_id == target_user.id, FriendRequest.to_user_id == from_user.id),
            )
        )
    )
    existing_request = existing_result.scalar_one_or_none()
    if existing_request and existing_request.status == FriendStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Friend request already exists")

    friend_request = FriendRequest(from_user_id=from_user.id, to_user_id=target_user.id)
    session.add(friend_request)
    await session.commit()
    return await get_friend_request(session, request_id=friend_request.id)


async def get_friend_request(session: AsyncSession, *, request_id: int) -> FriendRequest:
    result = await session.execute(
        select(FriendRequest)
        .options(
            selectinload(FriendRequest.from_user),
            selectinload(FriendRequest.to_user),
        )
        .where(FriendRequest.id == request_id)
    )
    friend_request = result.scalar_one_or_none()
    if not friend_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found")
    return friend_request


async def list_pending_friend_requests(session: AsyncSession, *, user_id: int) -> list[FriendRequest]:
    result = await session.execute(
        select(FriendRequest)
        .options(selectinload(FriendRequest.from_user), selectinload(FriendRequest.to_user))
        .where(and_(FriendRequest.to_user_id == user_id, FriendRequest.status == FriendStatus.PENDING))
        .order_by(FriendRequest.created_at.desc())
    )
    return list(result.scalars().all())


async def accept_friend_request(session: AsyncSession, *, request_id: int, user_id: int) -> FriendRequest:
    friend_request = await get_friend_request(session, request_id=request_id)
    if friend_request.to_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Friend request access denied")
    friend_request.status = FriendStatus.ACCEPTED
    friend_request.updated_at = utcnow()
    await session.commit()
    return await get_friend_request(session, request_id=request_id)


async def reject_friend_request(session: AsyncSession, *, request_id: int, user_id: int) -> None:
    friend_request = await get_friend_request(session, request_id=request_id)
    if friend_request.to_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Friend request access denied")
    friend_request.status = FriendStatus.REJECTED
    friend_request.updated_at = utcnow()
    await session.commit()


async def list_friends(session: AsyncSession, *, user_id: int) -> list[FriendRequest]:
    result = await session.execute(
        select(FriendRequest)
        .options(selectinload(FriendRequest.from_user), selectinload(FriendRequest.to_user))
        .where(
            and_(
                or_(FriendRequest.from_user_id == user_id, FriendRequest.to_user_id == user_id),
                FriendRequest.status == FriendStatus.ACCEPTED,
            )
        )
        .order_by(FriendRequest.updated_at.desc())
    )
    return list(result.scalars().all())


async def delete_friendship(session: AsyncSession, *, request_id: int, user_id: int) -> None:
    friend_request = await get_friend_request(session, request_id=request_id)
    if user_id not in {friend_request.from_user_id, friend_request.to_user_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Friend request access denied")
    await session.delete(friend_request)
    await session.commit()


def serialize_member(member: ChatMember) -> MemberResponse:
    return MemberResponse(
        user_id=member.user_id,
        role=member.role.value,
        can_send_messages=member.can_send_messages,
        joined_at=member.joined_at,
        user=serialize_user(member.user) if member.user else None,
    )


async def update_member_permissions(
    session: AsyncSession,
    *,
    room_id: int,
    user_id: int,
    can_send_messages: bool | None = None,
    role: str | None = None,
) -> ChatMember:
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    result = await session.execute(
        select(ChatMember)
        .options(selectinload(ChatMember.user))
        .where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if membership.role == MembershipRole.OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner permissions cannot be changed")

    if role is not None:
        membership.role = MembershipRole(role)

    if can_send_messages is not None:
        if room.type == RoomType.CHANNEL and can_send_messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only the channel owner can publish messages",
            )
        membership.can_send_messages = can_send_messages

    if room.type == RoomType.CHANNEL:
        membership.can_send_messages = False

    await session.commit()
    await session.refresh(membership)
    return await _ensure_room_member(session, room_id=room_id, user_id=user_id)


def serialize_friend_request(friend_request: FriendRequest) -> FriendRequestResponse:
    return FriendRequestResponse(
        id=friend_request.id,
        from_user_id=friend_request.from_user_id,
        to_user_id=friend_request.to_user_id,
        status=friend_request.status.value,
        created_at=friend_request.created_at,
        updated_at=friend_request.updated_at,
        from_user=serialize_user(friend_request.from_user) if friend_request.from_user else None,
        to_user=serialize_user(friend_request.to_user) if friend_request.to_user else None,
    )


def serialize_friend(friend_request: FriendRequest, *, current_user_id: int) -> FriendResponse:
    counterpart = friend_request.to_user if friend_request.from_user_id == current_user_id else friend_request.from_user
    return FriendResponse(
        id=friend_request.id,
        friend_id=counterpart.id,
        status=friend_request.status.value,
        friend=serialize_user(counterpart),
    )
