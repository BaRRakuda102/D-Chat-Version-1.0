# Render Deploy Guide

This repository is prepared for Render with a multi-service setup that matches the current auth flow:

- `dchat-frontend` - public web service that serves the React app and proxies `/api`, `/uploads`, and `/ws`
- `dchat-api` - public web service that runs FastAPI and WebSockets
- `dchat-postgres` - Render Postgres
- `dchat-cache` - Render Key Value

## Why the backend is public on Render free

Render free web services cannot receive private network traffic.
Because of that limitation, the frontend proxies to the API over the API's public Render URL instead of a private hostname.

Official docs:

- [Free web service limitations](https://render.com/docs/free)
- [Web services](https://render.com/docs/web-services)
- [Blueprint YAML reference](https://render.com/docs/blueprint-spec)

## Important free-plan limitations

- Free web services spin down after 15 minutes without traffic.
- Free web services lose local filesystem changes on restart, redeploy, or spin-down.
- Free Postgres expires after 30 days.
- Free Key Value is memory-only and loses data on restart.
- Free web services cannot send SMTP traffic on ports `25`, `465`, or `587`.

That means:

- avatar and attachment files are temporary on free Render
- email verification should stay in log mode unless you move email sending to another provider or a paid plan

## Deploy with Blueprint

1. Push the latest code to GitHub.
2. In Render, click `New +` -> `Blueprint`.
3. Select this repository.
4. Render will detect [render.yaml](/E:/D-Chat/render.yaml).
5. Review the four resources and create them.

## First checks after deploy

Open:

- `https://<frontend-domain>/`
- `https://<frontend-domain>/api/v1/health`

Then verify:

- registration
- email verification via backend logs
- login
- WebSocket updates
- basic messaging

## Notes

- The frontend reads the API URL from the API service's `RENDER_EXTERNAL_URL`.
- The backend accepts both `DATABASE_URL` and `APP_DATABASE_URL` so it remains tolerant of provider quirks.
- The nginx config forwards the correct upstream host header for public-to-public service proxying on Render.
