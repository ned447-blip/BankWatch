"""Email notification — sends the daily report when something needs attention.

Triggered when there are material changes, new/withdrawn products, or
unverified checks. Clean runs (all verified, nothing changed) are silent.

Uses standard SMTP (defaults to Gmail). Configure via environment variables
(set as GitHub secrets — see the workflow file):

  BANKWATCH_EMAIL_FROM      sender address  e.g. you@gmail.com
  BANKWATCH_EMAIL_TO        recipient       e.g. you@gmail.com (can be same)
  BANKWATCH_EMAIL_PASSWORD  Gmail App Password (NOT your normal Gmail password)
  BANKWATCH_SMTP_HOST       optional, default smtp.gmail.com
  BANKWATCH_SMTP_PORT       optional, default 587

Gmail App Password setup (one-time, ~2 minutes):
  1. myaccount.google.com → Security → 2-Step Verification (must be on)
  2. Security → App passwords → select app "Mail" → generate
  3. Copy the 16-char password → add as GitHub secret BANKWATCH_EMAIL_PASSWORD
"""
from __future__ import annotations

import os
import smtplib
import textwrap
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def should_send(material: int, new_products: int, withdrawn: int, unverified: int) -> bool:
    return bool(material or new_products or withdrawn or unverified)


def _subject(material: int, new_products: int, unverified: int, date_str: str) -> str:
    parts = []
    if material:
        parts.append(f"🔴 {material} material change{'s' if material > 1 else ''}")
    if new_products:
        parts.append(f"🆕 {new_products} new product{'s' if new_products > 1 else ''}")
    if unverified:
        parts.append(f"⚠️ {unverified} unverified")
    summary = " · ".join(parts) if parts else "changes detected"
    return f"BankWatch {date_str} — {summary}"


def send(*, date_str: str, report_markdown: str,
         material: int, new_products: int, withdrawn: int, unverified: int) -> None:
    """Send the report email. No-op if env vars not set (safe to call always)."""
    sender = os.environ.get("BANKWATCH_EMAIL_FROM", "").strip()
    recipient = os.environ.get("BANKWATCH_EMAIL_TO", "").strip()
    password = os.environ.get("BANKWATCH_EMAIL_PASSWORD", "").strip()
    if not (sender and recipient and password):
        print("  Email: BANKWATCH_EMAIL_* not set — skipping notification.")
        return

    host = os.environ.get("BANKWATCH_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("BANKWATCH_SMTP_PORT", "587"))
    subject = _subject(material, new_products, unverified, date_str)

    # Plain-text body: the full Markdown report (very readable as-is).
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"BankWatch <{sender}>"
    msg["To"] = recipient
    msg.attach(MIMEText(report_markdown, "plain", "utf-8"))

    try:
        with smtplib.SMTP(host, port) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, [recipient], msg.as_string())
        print(f"  Email sent → {recipient}  subject: {subject}")
    except Exception as e:
        # Email failure is never fatal — the report file is already written.
        print(f"  ⚠️  Email failed ({type(e).__name__}: {e}) — report saved to file.")
