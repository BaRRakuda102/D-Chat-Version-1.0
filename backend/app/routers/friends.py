from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import FriendRequestCreate, FriendRequestResponse, FriendResponse, SimpleMessageResponse
from app.services import audit as audit_service
from app.services import chat as chat_service

router = APIRouter()


@router.get("/", response_model=list[FriendResponse])
async def get_friends(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FriendResponse]:
    friendships = await chat_service.list_friends(session, user_id=current_user.id)
    return [chat_service.serialize_friend(friendship, current_user_id=current_user.id) for friendship in friendships]


@router.get("/requests/", response_model=list[FriendRequestResponse])
async def get_friend_requests(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FriendRequestResponse]:
    requests = await chat_service.list_pending_friend_requests(session, user_id=current_user.id)
    return [chat_service.serialize_friend_request(friend_request) for friend_request in requests]


@router.post("/requests", response_model=FriendRequestResponse, status_code=201)
async def send_friend_request(
    request: Request,
    payload: FriendRequestCreate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FriendRequestResponse:
    friend_request = await chat_service.send_friend_request(
        session,
        from_user=current_user,
        target_username=payload.username.strip(),
    )
    await audit_service.create_audit_log(
        session,
        action="send_friend_request",
        user_id=current_user.id,
        entity_type="friend_request",
        entity_id=friend_request.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return chat_service.serialize_friend_request(friend_request)


@router.post("/requests/{request_id}/accept", response_model=FriendRequestResponse)
async def accept_friend_request(
    request_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FriendRequestResponse:
    friend_request = await chat_service.accept_friend_request(session, request_id=request_id, user_id=current_user.id)
    await audit_service.create_audit_log(
        session,
        action="accept_friend_request",
        user_id=current_user.id,
        entity_type="friend_request",
        entity_id=request_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return chat_service.serialize_friend_request(friend_request)


@router.post("/requests/{request_id}/reject", response_model=SimpleMessageResponse)
async def reject_friend_request(
    request_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await chat_service.reject_friend_request(session, request_id=request_id, user_id=current_user.id)
    await audit_service.create_audit_log(
        session,
        action="reject_friend_request",
        user_id=current_user.id,
        entity_type="friend_request",
        entity_id=request_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Friend request rejected.")


@router.delete("/{request_id}", response_model=SimpleMessageResponse)
async def delete_friend(
    request_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await chat_service.delete_friendship(session, request_id=request_id, user_id=current_user.id)
    await audit_service.create_audit_log(
        session,
        action="delete_friend",
        user_id=current_user.id,
        entity_type="friend_request",
        entity_id=request_id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Friend removed.")
