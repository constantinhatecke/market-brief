"""SMTP delivery (Gmail app password by default)."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import Settings


def send_email(settings: Settings, subject: str, html: str, text: str) -> None:
    if not (settings.smtp_user and settings.smtp_password and settings.email_to):
        raise RuntimeError("SMTP_USER, SMTP_PASSWORD and EMAIL_TO must be set to send email")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = settings.email_to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as s:
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
