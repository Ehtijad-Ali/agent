"""Outgoing email over SMTP (welcome emails for new platform users).

Any SMTP provider works: Brevo, Mailgun, Amazon SES, or a Gmail account with an
app password. With SMTP_HOST unset nothing is sent and callers are told so, so
the admin knows to share the sign-in details themselves.

Passwords are never emailed. The admin who creates an account sets its password
and passes it on through a channel of their choosing; the email only says the
account exists and where to sign in.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("signal.email")


class EmailError(RuntimeError):
    """Sending failed; the message is safe to show to an admin."""


def enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


def send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not enabled():
        raise EmailError("Email is not set up on the server (SMTP_HOST / SMTP_FROM).")

    message = EmailMessage()
    message["From"] = s.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        if s.smtp_port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with server:
            if s.smtp_port != 465 and s.smtp_starttls:
                server.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("The email server rejected the SMTP username or password.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Sending email to %s failed: %s", to, exc)
        raise EmailError(f"Could not send the email: {type(exc).__name__}.") from exc


def welcome_text(name: str, email: str, role_label: str, invited_by: str) -> tuple[str, str]:
    s = get_settings()
    url = s.frontend_url.rstrip("/") or s.public_base_url.rstrip("/")
    subject = "Your Signal account is ready"
    body = f"""Hi {name},

{invited_by} has created a Signal account for you.

  Sign in at: {url}/login
  Email:      {email}
  Role:       {role_label}

Your password will be given to you by {invited_by} separately. For your
security it is never sent by email.

Signal - {s.product_label}
"""
    return subject, body
