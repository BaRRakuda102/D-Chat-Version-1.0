from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import MessageResponse, ReactionCreate, SimpleMessageResponse
from app.services import audit as audit_service
from app.services import chat as chat_service
from app.services import realtime as realtime_service

router = APIRouter()


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    message = await chat_service.get_message_for_user(session, message_id=message_id, user_id=current_user.id)
    return chat_service.serialize_message(message)


@router.delete("/{message_id}", response_model=SimpleMessageResponse)
async def delete_message(
    message_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    message = await chat_service.get_message_for_user(session, message_id=message_id, user_id=current_user.id)
    if message.sender_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only author can delete the message")
    await chat_service.delete_message(session, message=message)
    await audit_service.create_audit_log(
        session,
        action="delete_message",
        user_id=current_user.id,
        entity_type="message",
        entity_id=message_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Message deleted.")


@router.post("/{message_id}/reactions", response_model=MessageResponse)
async def add_reaction(
    message_id: int,
    request: Request,
    payload: ReactionCreate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    message = await chat_service.add_reaction(
        session,
        message_id=message_id,
        user_id=current_user.id,
        emoji=payload.emoji,
    )
    await realtime_service.broadcast_reaction_update(message)
    await audit_service.create_audit_log(
        session,
        action="add_reaction",
        user_id=current_user.id,
        entity_type="message",
        entity_id=message_id,
        details=payload.emoji,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return chat_service.serialize_message(message)
