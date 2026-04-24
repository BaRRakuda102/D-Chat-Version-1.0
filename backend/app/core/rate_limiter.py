from slowapi import Limiter

from app.core.config import settings
from app.core.security import resolve_client_ip

limiter = Limiter(
    key_func=resolve_client_ip,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.REDIS_URL,
)
