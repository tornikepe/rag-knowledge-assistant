"""Minimal SMTP email sending for sign-up verification codes.

Kept dependency-free (stdlib ``smtplib``). When SMTP isn't configured, callers fall
back to returning the code to the client so the demo still works end-to-end.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings


def send_verification_email(settings: Settings, to_email: str, name: str, code: str) -> bool:
    """Send the 6-digit verification code. Returns True if it was actually sent."""
    if not settings.email_enabled:
        return False

    sender = settings.smtp_from or settings.smtp_user or "no-reply@peit.app"
    msg = EmailMessage()
    msg["Subject"] = f"Your Peit verification code: {code}"
    msg["From"] = sender
    msg["To"] = to_email
    greeting = name.strip() or "there"
    msg.set_content(
        f"Hi {greeting},\n\n"
        f"Your Peit verification code is: {code}\n\n"
        "Enter this code to finish creating your account. It expires in 10 minutes.\n\n"
        "If you didn't request this, you can ignore this email.\n\n"
        "— Peit"
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
        if settings.smtp_starttls:
            server.starttls(context=context)
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    return True
