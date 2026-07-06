"""
emailer.py — Sends the digest as an HTML email over SMTP.

Works with any SMTP provider. For Gmail:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=youraddress@gmail.com
  SMTP_PASS=<16-character App Password>  (NOT your normal Gmail password —
            you must enable 2-Step Verification, then create an "App
            Password" at https://myaccount.google.com/apppasswords)
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(subject, html_body, plain_body=None):
    host = os.environ.get("SMTP_HOST", "").strip()
    port_str = os.environ.get("SMTP_PORT", "").strip()
    port = int(port_str) if port_str else 587
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()

    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not user:
        missing.append("SMTP_USER")
    if not password:
        missing.append("SMTP_PASS")
    if missing:
        raise ValueError(
            f"Missing required SMTP configuration: {', '.join(missing)}. "
            "Please configure these variables in your environment or GitHub Secrets."
        )

    from_addr = os.environ.get("EMAIL_FROM", "").strip() or user
    email_to = os.environ.get("EMAIL_TO", "").strip()
    if not email_to:
        email_to = "abhinaykumar5432@gmail.com"
    to_addrs = [a.strip() for a in email_to.split(",") if a.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    if plain_body:
        msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(user, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())

    logger.info("Email sent to %s", to_addrs)

