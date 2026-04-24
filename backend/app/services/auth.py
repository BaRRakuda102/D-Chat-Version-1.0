from __future__ import annotations

from datetime import timedelta
import logging

from fastapi import HTTPException, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    build_frontend_url,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    get_access_token_from_request,
    hash_password,
    hash_token,
    resolve_client_ip,
    utcnow,
    verify_password,
)
from app.models import AuthToken, RoleEnum, TokenType, User
from app.schemas.auth import PasswordResetConfirm, RegisterRequest
from app.services import email as email_service
from app.services.user import get_user_by_email, get_user_by_username_or_email

logger = logging.getLogger("dchat.auth")


def _build_token_record(
    *,
    user_id: int,
    token_type: TokenType,
    token_hash_value: str,
    expires_at,
    request: Request | None,
    jti: str | None = None,
) -> AuthToken:
    return AuthToken(
        user_id=user_id,
        token_type=token_type,
        token_hash=token_hash_value,
        jti=jti,
        expires_at=expires_at,
        ip_address=resolve_client_ip(request) if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )


async def register_user(
    session: AsyncSession,
    payload: RegisterRequest,
    request: Request | None = None,
) -> tuple[User, str]:
    existing_result = await session.execute(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this username or email already exists",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name or payload.username,
        hashed_password=hash_password(payload.password),
        role=RoleEnum.USER,
    )
    session.add(user)
    await session.flush()

    raw_token = generate_secure_token()
    session.add(
        _build_token_record(
            user_id=user.id,
            token_type=TokenType.EMAIL_VERIFICATION,
            token_hash_value=hash_token(raw_token),
            expires_at=utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
            request=request,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user, raw_token


async def send_email_verification(user: User, raw_token: str) -> None:
    verification_url = build_frontend_url("/verify-email", raw_token)
    try:
        await email_service.send_verification_email(user.email, verification_url)
    except Exception:
        logger.exception("Failed to send verification email to %s", user.email)


async def authenticate_user(
    session: AsyncSession,
    *,
    username_or_email: str,
    password: str,
) -> User:
    user = await get_user_by_username_or_email(session, username_or_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    is_valid, updated_hash = verify_password(password, user.hashed_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if updated_hash:
        user.hashed_password = updated_hash

    if not user.is_active or user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not available",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
        )

    user.last_seen = utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def create_session_tokens(
    session: AsyncSession,
    *,
    user: User,
    request: Request | None = None,
) -> tuple[str, str]:
    access_token = create_access_token(user_id=user.id, role=user.role.value)
    refresh_token, refresh_jti = create_refresh_token(user_id=user.id, role=user.role.value)
    session.add(
        _build_token_record(
            user_id=user.id,
            token_type=TokenType.REFRESH,
            token_hash_value=hash_token(refresh_token),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            request=request,
            jti=refresh_jti,
        )
    )
    await session.commit()
    return access_token, refresh_token


async def revoke_refresh_token(session: AsyncSession, raw_refresh_token: str | None) -> None:
    if not raw_refresh_token:
        return
    try:
        payload = decode_token(raw_refresh_token, expected_type="refresh")
    except HTTPException:
        return

    jti = payload.get("jti")
    if not jti:
        return

    result = await session.execute(
        select(AuthToken).where(
            and_(
                AuthToken.jti == jti,
                AuthToken.token_type == TokenType.REFRESH,
                AuthToken.revoked_at.is_(None),
            )
        )
    )
    token_record = result.scalar_one_or_none()
    if not token_record:
        return
    token_record.revoked_at = utcnow()
    token_record.used_at = utcnow()
    await session.commit()


async def refresh_session(
    session: AsyncSession,
    *,
    raw_refresh_token: str,
    request: Request | None = None,
) -> tuple[User, str, str]:
    payload = decode_token(raw_refresh_token, expected_type="refresh")
    user_id = int(payload.get("sub", 0))
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    result = await session.execute(
        select(AuthToken).where(
            and_(
                AuthToken.jti == jti,
                AuthToken.token_type == TokenType.REFRESH,
                AuthToken.revoked_at.is_(None),
            )
        )
    )
    token_record = result.scalar_one_or_none()
    if not token_record or token_record.expires_at <= utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or revoked",
        )

    if token_record.token_hash != hash_token(raw_refresh_token):
        token_record.revoked_at = utcnow()
        token_record.used_at = utcnow()
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or revoked",
        )

    user = await session.get(User, user_id)
    if not user or not user.is_active or user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session is not available",
        )

    token_record.revoked_at = utcnow()
    token_record.used_at = utcnow()
    access_token = create_access_token(user_id=user.id, role=user.role.value)
    refresh_token, refresh_jti = create_refresh_token(user_id=user.id, role=user.role.value)
    session.add(
        _build_token_record(
            user_id=user.id,
            token_type=TokenType.REFRESH,
            token_hash_value=hash_token(refresh_token),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            request=request,
            jti=refresh_jti,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user, access_token, refresh_token


async def verify_email(
    session: AsyncSession,
    *,
    raw_token: str,
) -> User:
    token_hash_value = hash_token(raw_token)
    result = await session.execute(
        select(AuthToken)
        .where(
            and_(
                AuthToken.token_hash == token_hash_value,
                AuthToken.token_type == TokenType.EMAIL_VERIFICATION,
                AuthToken.revoked_at.is_(None),
                AuthToken.used_at.is_(None),
            )
        )
    )
    token_record = result.scalar_one_or_none()
    if not token_record or token_record.expires_at <= utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is invalid or expired",
        )

    user = await session.get(User, token_record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_verified = True
    token_record.used_at = utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def resend_verification_email(
    session: AsyncSession,
    *,
    email: str,
    request: Request | None = None,
) -> None:
    user = await get_user_by_email(session, email)
    if not user or user.is_verified:
        return

    raw_token = generate_secure_token()
    session.add(
        _build_token_record(
            user_id=user.id,
            token_type=TokenType.EMAIL_VERIFICATION,
            token_hash_value=hash_token(raw_token),
            expires_at=utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
            request=request,
        )
    )
    await session.commit()
    await send_email_verification(user, raw_token)


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    request: Request | None = None,
) -> None:
    user = await get_user_by_email(session, email)
    if not user or not user.is_active:
        return

    raw_token = generate_secure_token()
    session.add(
        _build_token_record(
            user_id=user.id,
            token_type=TokenType.PASSWORD_RESET,
            token_hash_value=hash_token(raw_token),
            expires_at=utcnow() + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
            request=request,
        )
    )
    await session.commit()
    reset_url = build_frontend_url("/reset-password", raw_token)
    try:
        await email_service.send_password_reset_email(user.email, reset_url)
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)


async def confirm_password_reset(
    session: AsyncSession,
    payload: PasswordResetConfirm,
) -> User:
    token_hash_value = hash_token(payload.token)
    result = await session.execute(
        select(AuthToken)
        .where(
            and_(
                AuthToken.token_hash == token_hash_value,
                AuthToken.token_type == TokenType.PASSWORD_RESET,
                AuthToken.revoked_at.is_(None),
                AuthToken.used_at.is_(None),
            )
        )
    )
    token_record = result.scalar_one_or_none()
    if not token_record or token_record.expires_at <= utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token is invalid or expired",
        )

    user = await session.get(User, token_record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(payload.new_password)
    token_record.used_at = utcnow()

    active_refresh_tokens = await session.execute(
        select(AuthToken).where(
            and_(
                AuthToken.user_id == user.id,
                AuthToken.token_type == TokenType.REFRESH,
                AuthToken.revoked_at.is_(None),
            )
        )
    )
    for refresh_token_record in active_refresh_tokens.scalars().all():
        refresh_token_record.revoked_at = utcnow()

    await session.commit()
    await session.refresh(user)
    return user


async def get_user_from_request(session: AsyncSession, request: Request) -> User | None:
    access_token = get_access_token_from_request(request)
    if not access_token:
        return None

    try:
        payload = decode_token(access_token, expected_type="access")
    except HTTPException:
        return None

    user_id = int(payload.get("sub", 0))
    if not user_id:
        return None

    user = await session.get(User, user_id)
    if not user or not user.is_active or user.is_banned:
        return None
    return user
