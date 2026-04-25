from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import and_, select, text

from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.core.rate_limiter import limiter
from app.core.redis import close_redis, get_redis, init_redis
from app.core.security import decode_token
from app.database import async_session, engine
from app.models import ChatMember, User, utcnow
from app.routers import admin, auth, chat_rooms, friends, messages, upload, users
from app.schemas import HealthDependencyStatus, HealthResponse, MessageCreate
from app.services import chat as chat_service
from app.services import realtime as realtime_service
from app.services import user as user_service
from app.websocket_manager import manager

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    await init_redis()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

frontend_dist_dir = Path(os.getenv("FRONTEND_DIST_DIR", "/app/frontend-dist"))

app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["users"])
app.include_router(friends.router, prefix=f"{settings.API_V1_PREFIX}/friends", tags=["friends"])
app.include_router(chat_rooms.router, prefix=f"{settings.API_V1_PREFIX}/chat/rooms", tags=["chat"])
app.include_router(messages.router, prefix=f"{settings.API_V1_PREFIX}/chat/messages", tags=["messages"])
app.include_router(upload.router, prefix=f"{settings.API_V1_PREFIX}/upload", tags=["upload"])
app.include_router(admin.router, prefix=f"{settings.API_V1_PREFIX}/admin", tags=["admin"])


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.exception("Unhandled error during %s %s in %sms", request.method, request.url.path, duration_ms)
        raise

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get(f"{settings.API_V1_PREFIX}/health", response_model=HealthResponse)
async def healthcheck(response: Response) -> HealthResponse:
    database_status = HealthDependencyStatus(status="down")
    redis_status = HealthDependencyStatus(status="down")

    async with async_session() as session:
        db_started_at = perf_counter()
        try:
            await session.execute(text("SELECT 1"))
            database_status = HealthDependencyStatus(
                status="up",
                latency_ms=round((perf_counter() - db_started_at) * 1000, 2),
            )
        except Exception:
            logger.exception("Database healthcheck failed")

    redis_started_at = perf_counter()
    try:
        redis = get_redis()
        await redis.ping()
        redis_status = HealthDependencyStatus(
            status="up",
            latency_ms=round((perf_counter() - redis_started_at) * 1000, 2),
        )
    except Exception:
        logger.exception("Redis healthcheck failed")

    overall_status = "ok" if database_status.status == "up" and redis_status.status == "up" else "degraded"
    if overall_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=overall_status,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=utcnow(),
        database=database_status,
        redis=redis_status,
    )


@app.websocket("/ws/chat/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: int) -> None:
    access_token = websocket.cookies.get(settings.AUTH_COOKIE_NAME)
    if not access_token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(access_token, expected_type="access")
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=1008)
        return

    if not user_id:
        await websocket.close(code=1008)
        return

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await websocket.close(code=1008)
            return

        member_check = await session.execute(
            select(ChatMember).where(and_(ChatMember.room_id == room_id, ChatMember.user_id == user_id))
        )
        membership = member_check.scalar_one_or_none()
        if membership is None:
            await websocket.close(code=1008)
            return
        await user_service.set_user_presence(session, user, is_online=True)
        await realtime_service.broadcast_user_presence(session, user_id=user_id)

    await manager.connect(websocket, room_id=room_id, user_id=user_id)
    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type", "message")

            if event_type == "typing":
                await manager.broadcast(
                    room_id,
                    {"type": "typing", "user_id": user_id},
                    exclude=websocket,
                )
                continue

            async with async_session() as session:
                sender = await session.get(User, user_id)
                if not sender:
                    await websocket.close(code=1008)
                    return

                if event_type == "message":
                    message_payload = MessageCreate.model_validate(
                        {
                            "content": payload.get("content", ""),
                            "reply_to_id": payload.get("reply_to_id"),
                            "attachments": payload.get("attachments", []),
                        }
                    )
                    message = await chat_service.create_message(
                        session,
                        room_id=room_id,
                        sender=sender,
                        payload=message_payload,
                    )
                    room = await chat_service.get_room_for_user(
                        session,
                        room_id=room_id,
                        user_id=user_id,
                    )
                    await realtime_service.broadcast_room_message(message)
                    await realtime_service.broadcast_room_snapshot(
                        session,
                        room_id=room_id,
                        actor_user_id=user_id,
                        notification_text=realtime_service.build_message_notification(
                            room_name=room.name,
                            message=message,
                        ),
                    )
                elif event_type == "reaction":
                    message_id = int(payload.get("message_id", 0))
                    emoji = str(payload.get("emoji", "")).strip()
                    if not message_id or not emoji:
                        continue
                    message = await chat_service.add_reaction(
                        session,
                        message_id=message_id,
                        user_id=user_id,
                        emoji=emoji,
                    )
                    await realtime_service.broadcast_reaction_update(message)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("WebSocket error for room %s", room_id)
        manager.disconnect(websocket)
    finally:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user and not manager.has_user_connections(user_id):
                await user_service.set_user_presence(session, user, is_online=False)
                await realtime_service.broadcast_user_presence(session, user_id=user_id)


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket) -> None:
    access_token = websocket.cookies.get(settings.AUTH_COOKIE_NAME)
    if not access_token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(access_token, expected_type="access")
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=1008)
        return

    if not user_id:
        await websocket.close(code=1008)
        return

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await websocket.close(code=1008)
            return
        await user_service.set_user_presence(session, user, is_online=True)
        await realtime_service.broadcast_user_presence(session, user_id=user_id)

    await manager.connect_user(websocket, user_id=user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("Notification websocket error for user %s", user_id)
        manager.disconnect(websocket)
    finally:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user and not manager.has_user_connections(user_id):
                await user_service.set_user_presence(session, user, is_online=False)
                await realtime_service.broadcast_user_presence(session, user_id=user_id)


def _frontend_file_response(relative_path: str | None = None) -> FileResponse:
    if not frontend_dist_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend assets not found")

    if relative_path:
        candidate = (frontend_dist_dir / relative_path).resolve()
        try:
            candidate.relative_to(frontend_dist_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
        if candidate.is_file():
            return FileResponse(candidate)

    index_path = frontend_dist_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend index not found")
    return FileResponse(index_path)


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    return _frontend_file_response()


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str) -> FileResponse:
    reserved_prefixes = ("api/", "uploads/", "ws/")
    reserved_exact_paths = {"api", "uploads", "ws"}
    if full_path in reserved_exact_paths or full_path.startswith(reserved_prefixes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _frontend_file_response(full_path or None)
