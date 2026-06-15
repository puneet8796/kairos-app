"""
emailer.py
Optional. Sends the summary by email if SMTP env vars are set. Off by default.
The whole tool works without this. Email is just one delivery option.

Set these to enable:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""

import os
import smtplib
import ssl
from email.message import EmailMessage


def email_configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM")
    )


def send_summary(to_address: str, subject: str, body_text: str) -> tuple[bool, str]:
    if not email_configured():
        return False, "Email is not configured. Set the SMTP_* environment variables."
    if not to_address:
        return False, "No recipient address provided."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = to_address
    msg.set_content(body_text)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls(context=context)
                s.login(user, password)
                s.send_message(msg)
        return True, "Sent."
    except Exception as e:
        return False, f"Send failed: {e}"
