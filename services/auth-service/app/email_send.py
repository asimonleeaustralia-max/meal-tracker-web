"""Optional SMTP email delivery for password reset."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import Settings

log = logging.getLogger(__name__)


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_password_reset_email(
    settings: Settings,
    *,
    to_email: str,
    reset_url: str,
) -> None:
    subject = "Reset your MacrosSimple password"
    body = (
        "You requested a password reset for your MacrosSimple account.\n\n"
        f"Open this link to choose a new password (expires in {settings.password_reset_token_hours} hour(s)):\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    if not smtp_configured(settings):
        log.warning(
            "SMTP not configured; password reset link for %s: %s",
            to_email,
            reset_url,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
