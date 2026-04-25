# Railway One-Service Deploy

This variant is the simplest Railway setup for this project:

- one public Railway web service built from the repository root
- one Railway PostgreSQL resource
- one Railway Redis resource

The web service builds both the frontend and backend into a single container.
FastAPI serves the React build directly, so there is no separate frontend service and no nginx proxy service in Railway.

## Service layout

- `dchat-app` - one public web service from the repository root
- `postgres` - Railway PostgreSQL
- `redis` - Railway Redis

## Source settings for the web service

- Root Directory: `/`
- Builder: `Dockerfile`
- Dockerfile Path: `/Dockerfile`

## Required variables for `dchat-app`

Set these in the Railway web service:

```text
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<long-random-secret>
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE=52428800
FRONTEND_URL=https://<your-railway-public-domain>
ALLOWED_ORIGINS=https://<your-railway-public-domain>
ALLOWED_HOSTS=localhost,127.0.0.1,<your-railway-public-domain>
REDIS_URL=<redis connection string>
```

For the database use one of these options:

### Preferred

```text
APP_DATABASE_URL=<postgres connection string>
```

### Optional

```text
DATABASE_URL=<postgres connection string>
```

The app now accepts both `APP_DATABASE_URL` and `DATABASE_URL`.

## Upload persistence

Attach a Railway volume to the web service with mount path:

```text
/app/uploads
```

## Health check

After deploy, open:

```text
https://<your-railway-public-domain>/api/v1/health
```

Then open:

```text
https://<your-railway-public-domain>/
```

## Notes

- Email verification can stay in log mode if SMTP is not configured.
- WebSockets use the same public domain because the frontend and backend are in one service.
- This setup avoids the Railway issue we hit with separate frontend/backend services.
