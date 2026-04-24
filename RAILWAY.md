# Railway Deploy Guide

This project is ready to be deployed to Railway as a small multi-service setup.

Recommended service layout:

- `frontend` - public service, built from [nginx/Dockerfile](/E:/D-Chat/nginx/Dockerfile)
- `backend` - private service, built from [backend/Dockerfile](/E:/D-Chat/backend/Dockerfile)
- `postgres` - Railway PostgreSQL service
- `redis` - Railway Redis service

## Why this layout

The frontend service serves the React app and proxies `/api`, `/uploads`, and `/ws` to the private backend service.
This keeps cookies and WebSocket traffic on the same public domain, which is the safest setup for the current auth flow.

## 1. Push the project to GitHub

If the repository is still empty:

```powershell
cd E:\D-Chat
git init
git add .
git commit -m "Stable D-Chat build"
git branch -M main
git remote add origin https://github.com/BaRRakuda102/D-Chat.git
git push -u origin main
```

## 2. Create the services in Railway

Create or attach these services inside the same Railway project/environment:

- `frontend`
- `backend`
- `postgres`
- `redis`

Use these source settings:

- `frontend`
  - Repo: this repository
  - Root Directory: `/`
  - Dockerfile Path: `nginx/Dockerfile`
- `backend`
  - Repo: this repository
  - Root Directory: `/backend`
  - Dockerfile Path: `Dockerfile`

## 3. Attach a persistent volume

Attach a Railway volume to the `backend` service with mount path:

```text
/app/uploads
```

That is required for avatars and chat attachments to survive redeploys.

## 4. Set frontend variables

Copy values from [railway/frontend.env.example](/E:/D-Chat/railway/frontend.env.example).

Main variable:

```text
BACKEND_UPSTREAM=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000
```

If your backend service has a different Railway service name, replace `backend` in the template with that exact service name.

## 5. Set backend variables

Copy values from [railway/backend.env.example](/E:/D-Chat/railway/backend.env.example).

Important ones:

```text
DATABASE_URL=${{postgres.DATABASE_URL}}
REDIS_URL=${{redis.REDIS_URL}}
ALLOWED_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
FRONTEND_URL=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
COOKIE_SECURE=true
UPLOAD_DIR=/app/uploads
```

Also set:

- a strong `SECRET_KEY`
- real `SMTP_*` values if you want email verification and password reset by email

If your service names differ from `frontend`, `postgres`, or `redis`, update the reference variables to match the real names.

### SMTP for real users

Email verification and password reset only work for real users when SMTP is configured.
Without SMTP, the backend falls back to logging the verification link into backend logs, which is fine for local development but not for online testing with friends.

Set these variables in the `backend` Railway service:

```text
SMTP_HOST=<your smtp host>
SMTP_PORT=587
SMTP_USER=<your smtp username>
SMTP_PASSWORD=<your smtp password>
SMTP_TLS=true
SMTP_SSL=false
SMTP_TIMEOUT_SECONDS=15
EMAIL_FROM=<verified sender email>
EMAIL_FROM_NAME=D-Chat
```

If your mail provider uses implicit SSL on port `465`, switch to:

```text
SMTP_PORT=465
SMTP_TLS=false
SMTP_SSL=true
```

`EMAIL_FROM` should match a sender address that your SMTP provider allows you to send from.

## 6. Public domain

Expose only the `frontend` service publicly.
The `backend` service should stay private unless you explicitly need a public debug endpoint.

## 7. First checks after deploy

Open:

- `https://<frontend-domain>/`
- `https://<frontend-domain>/api/v1/health`

Then verify:

- registration
- email verification flow
- login persistence
- WebSocket chat updates
- file uploads

## Notes

- The nginx upload limit is set to `50M` to match the backend upload limit.
- The frontend proxies requests to the backend over Railway private networking.
- The backend still runs Alembic migrations automatically on startup.
