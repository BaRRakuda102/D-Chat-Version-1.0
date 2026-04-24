from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import clear_auth_cookies, resolve_client_ip, set_auth_cookies
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.schemas import (
    AuthSessionResponse,
    EmailVerificationConfirm,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    ResendVerificationRequest,
    SimpleMessageResponse,
)
from app.services import audit as audit_service
from app.services import auth as auth_service
from app.services.user import serialize_user

router = APIRouter()


@router.post("/register", response_model=SimpleMessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    user, raw_verification_token = await auth_service.register_user(session, payload, request)
    await auth_service.send_email_verification(user, raw_verification_token)
    await audit_service.create_audit_log(
        session,
        action="register",
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return SimpleMessageResponse(message="Registration successful. Check your email to verify the account.")


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    user = await auth_service.authenticate_user(
        session,
        username_or_email=payload.username.strip(),
        password=payload.password,
    )
    access_token, refresh_token = await auth_service.create_session_tokens(
        session,
        user=user,
        request=request,
    )
    set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    await audit_service.create_audit_log(
        session,
        action="login",
        user_id=user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AuthSessionResponse(user=serialize_user(user, include_email=True))


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh_session(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    raw_refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is required")
    user, access_token, refresh_token = await auth_service.refresh_session(
        session,
        raw_refresh_token=raw_refresh_token,
        request=request,
    )
    set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return AuthSessionResponse(user=serialize_user(user, include_email=True))


@router.post("/logout", response_model=SimpleMessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
) -> SimpleMessageResponse:
    raw_refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    await auth_service.revoke_refresh_token(session, raw_refresh_token)
    clear_auth_cookies(response)
    if current_user:
        await audit_service.create_audit_log(
            session,
            action="logout",
            user_id=current_user.id,
            ip_address=resolve_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    return SimpleMessageResponse(message="Logged out")


@router.get("/me", response_model=AuthSessionResponse)
async def me(current_user=Depends(get_current_user)) -> AuthSessionResponse:
    return AuthSessionResponse(user=serialize_user(current_user, include_email=True))


@router.get("/verify-email", response_model=SimpleMessageResponse)
async def verify_email(
    token: str = Query(..., min_length=20),
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await auth_service.verify_email(session, raw_token=token)
    return SimpleMessageResponse(message="Email verified successfully. You can sign in now.")


@router.post("/verify-email", response_model=SimpleMessageResponse)
async def verify_email_post(
    payload: EmailVerificationConfirm,
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await auth_service.verify_email(session, raw_token=payload.token)
    return SimpleMessageResponse(message="Email verified successfully. You can sign in now.")


@router.post("/resend-verification", response_model=SimpleMessageResponse)
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await auth_service.resend_verification_email(
        session,
        email=payload.email,
        request=request,
    )
    return SimpleMessageResponse(message="If the account exists, a verification email has been sent.")


@router.post("/password-reset/request", response_model=SimpleMessageResponse)
async def password_reset_request(
    request: Request,
    payload: PasswordResetRequest,
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await auth_service.request_password_reset(
        session,
        email=payload.email,
        request=request,
    )
    return SimpleMessageResponse(message="If the account exists, a password reset email has been sent.")


@router.post("/password-reset/confirm", response_model=SimpleMessageResponse)
async def password_reset_confirm(
    payload: PasswordResetConfirm,
    session: AsyncSession = Depends(get_db),
) -> SimpleMessageResponse:
    await auth_service.confirm_password_reset(session, payload)
    return SimpleMessageResponse(message="Password updated successfully.")
