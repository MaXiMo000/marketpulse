"""Email delivery for band-flip alerts. Optional: does nothing unless SMTP is configured."""
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, Ticker

log = logging.getLogger(__name__)


def send_email(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def notify_flips(session: Session, cycle_time: datetime, send=send_email) -> int:
    """Emails the band flips recorded for one cycle. Returns how many were sent; a mail failure is logged, never raised."""
    if not (settings.smtp_host and settings.alert_email_to):
        return 0
    rows = session.execute(
        select(Alert, Ticker.symbol).join(Ticker).where(Alert.computed_at == cycle_time).order_by(Ticker.symbol)
    ).all()
    if not rows:
        return 0
    lines = [f"{sym}: {a.from_band} -> {a.to_band} ({a.from_score:.0f} -> {a.to_score:.0f})" for a, sym in rows]
    msg = EmailMessage()
    msg["From"] = settings.alert_email_from or settings.alert_email_to
    msg["To"] = settings.alert_email_to
    if len(rows) == 1:
        a, sym = rows[0]
        msg["Subject"] = f"MarketPulse: {sym} {a.from_band} -> {a.to_band}"
    else:
        msg["Subject"] = f"MarketPulse: {len(rows)} signal flips"
    msg.set_content("\n".join(lines) + "\n\nAlgorithmic signal, not personalized financial advice.\n")
    try:
        send(msg)
    except Exception:
        log.exception("alert email failed")
        return 0
    return len(rows)
