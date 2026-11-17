from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.database import SessionLocal
from app.models.device import Device
from app.models.notification_log import NotificationLog
from app.services.crypto import decrypt
from app.services.notification_gate import block_reason
from app.services.settings_store import get_setting

logger = logging.getLogger("networkwatcher.smtp")


def _load_config(db) -> dict | None:
    if not get_setting(db, "smtp", "enabled", False):
        return None
    host = get_setting(db, "smtp", "host", None)
    if not host:
        return None
    password_enc = get_setting(db, "smtp", "password", None)
    return {
        "host": host,
        "port": get_setting(db, "smtp", "port", 587),
        "username": get_setting(db, "smtp", "username", None),
        "password": decrypt(password_enc) if password_enc else None,
        "security": get_setting(db, "smtp", "security", "STARTTLS"),  # NONE | STARTTLS | SSL_TLS
        "from_address": get_setting(db, "smtp", "from_address", None),
        "recipients": get_setting(db, "smtp", "recipients", []),
        "subject_prefix": get_setting(db, "smtp", "subject_prefix", "[Network Watcher]"),
    }


def _send(config: dict, subject: str, body: str, recipients: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"{config['subject_prefix']} {subject}".strip()
    msg["From"] = config["from_address"] or config["username"] or "networkwatcher@localhost"
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    context = ssl.create_default_context()
    if config["security"] == "SSL_TLS":
        with smtplib.SMTP_SSL(config["host"], config["port"], context=context, timeout=10) as server:
            if config["username"]:
                server.login(config["username"], config["password"])
            server.send_message(msg)
    else:
        with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
            if config["security"] == "STARTTLS":
                server.starttls(context=context)
            if config["username"]:
                server.login(config["username"], config["password"])
            server.send_message(msg)


def send_new_device_email(db, device: Device) -> None:
    """§18. Never raises -- SMTP failures must not block detection (§36)."""
    config = _load_config(db)
    if config is None or not config["recipients"]:
        return
    reason = block_reason(db, device.mac_address, "NEW_DEVICE")
    if reason:
        logger.info("Skipping new-device email (%s, mac=%s)", reason, device.mac_address)
        for recipient in config["recipients"]:
            db.add(
                NotificationLog(
                    device_id=device.id,
                    notification_type="SMTP",
                    event_type="NEW_DEVICE",
                    destination=recipient,
                    status="SKIPPED",
                    error=reason,
                )
            )
        db.commit()
        return

    body = (
        "Novi uređaj detektovan na mreži.\n\n"
        f"IP: {device.ip_address or '-'}\n"
        f"MAC: {device.mac_address}\n"
        f"Vendor: {device.vendor or 'nepoznat'}\n"
        f"Connection: {device.connection_type or '-'}\n"
        f"First seen: {device.first_seen.strftime('%d.%m.%Y %H:%M:%S')}\n"
    )

    for recipient in config["recipients"]:
        status, error = "SUCCESS", None
        try:
            _send(config, "New device detected", body, [recipient])
        except Exception as e:
            status, error = "FAILED", str(e)
            logger.exception("Failed to send new-device email (mac=%s)", device.mac_address)
        db.add(
            NotificationLog(
                device_id=device.id,
                notification_type="SMTP",
                event_type="NEW_DEVICE",
                destination=recipient,
                status=status,
                error=error,
            )
        )
    db.commit()


def test_connection() -> tuple[bool, str]:
    db = SessionLocal()
    try:
        config = _load_config(db)
        if config is None:
            return False, "SMTP server nije podešen"
        if not config["recipients"]:
            return False, "Nema podešenih primalaca"

        status, error, message = "SUCCESS", None, "SMTP connection successful"
        try:
            _send(
                config,
                "Test email",
                "Ovo je test poruka iz Network Device Watcher aplikacije.",
                config["recipients"],
            )
        except Exception as e:
            status, error = "FAILED", str(e)
            message = f"SMTP connection failed: {e}"

        for recipient in config["recipients"]:
            db.add(
                NotificationLog(
                    device_id=None,
                    notification_type="SMTP",
                    event_type="TEST",
                    destination=recipient,
                    status=status,
                    error=error,
                )
            )
        db.commit()
        return status == "SUCCESS", message
    finally:
        db.close()
