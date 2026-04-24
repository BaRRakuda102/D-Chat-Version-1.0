from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("dchat.email")


def _send_email_sync(subject: str, recipient: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.EMAIL_FROM:
        logger.info("Email transport is not configured, message for %s: %s", recipient, body)
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    message["To"] = recipient
    message.set_content(body)

    smtp_client: smtplib.SMTP | smtplib.SMTP_SSL
    if settings.SMTP_SSL:
        smtp_client = smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )
    else:
        smtp_client = smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )

    with smtp_client as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)

    logger.info('Email "%s" sent to %s', subject, recipient)


async def send_verification_email(recipient: str, verification_url: str) -> None:
    body = (
        "Welcome to D-Chat.\n\n"
        "Use this link to verify your email address:\n"
        f"{verification_url}\n\n"
        "If you did not create an account, ignore this email."
    )
    await asyncio.to_thread(
        _send_email_sync,
        "Verify your D-Chat email",
        recipient,
        body,
    )


async def send_password_reset_email(recipient: str, reset_url: str) -> None:
    body = (
        "You requested a D-Chat password reset.\n\n"
        "Use this link to choose a new password:\n"
        f"{reset_url}\n\n"
        "If you did not request a reset, ignore this email."
    )
    await asyncio.to_thread(
        _send_email_sync,
        "Reset your D-Chat password",
        recipient,
        body,
    )
