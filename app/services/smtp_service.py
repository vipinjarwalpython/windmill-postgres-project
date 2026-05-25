"""SMTP diagnostics — connection + test-send.

The actual outgoing email is sent inside Windmill (the worker runs the loan
flow). FastAPI only forwards the credentials. This service lets administrators
verify those credentials *from FastAPI* before relying on Windmill, so config
issues surface here rather than buried in a worker job log.

Stdlib ``smtplib`` is blocking, so each call is offloaded via
``asyncio.to_thread`` to keep the event loop free.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import socket
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip()
        except Exception:
            return repr(value)
    return str(value).strip()


class SmtpService:
    """Read-only SMTP diagnostic helpers."""

    def __init__(self, settings: Settings):
        self.settings = settings

    # ---------------- config ----------------
    def config_status(self) -> dict:
        """Per-field status used by the SMTP page."""
        cfg = self.settings.smtp_config
        return {
            "host": {"value": cfg["host"], "set": bool(cfg["host"])},
            "port": {"value": cfg["port"], "set": bool(cfg["port"])},
            "username": {"value": cfg["username"], "set": bool(cfg["username"])},
            "password": {
                "value": "•" * 10 if cfg["password"] else "",
                "set": bool(cfg["password"]),
            },
            "from_addr": {"value": cfg["from_addr"], "set": bool(cfg["from_addr"])},
        }

    def is_configured(self) -> bool:
        cfg = self.settings.smtp_config
        return all([cfg["host"], cfg["port"], cfg["username"], cfg["password"], cfg["from_addr"]])

    # ---------------- internal sync helpers ----------------
    def _open_connection(self) -> smtplib.SMTP:
        cfg = self.settings.smtp_config
        host = cfg["host"]
        port = int(cfg["port"])
        context = ssl.create_default_context()

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            # STARTTLS for standard submission ports (587); harmless if server doesn't advertise it.
            try:
                server.starttls(context=context)
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                # Server doesn't support STARTTLS — continue plain. (Some local relays.)
                logger.warning("smtp_starttls_not_supported", extra={"host": host, "port": port})

        server.login(cfg["username"], cfg["password"])
        return server

    def _test_connection_sync(self) -> None:
        server = self._open_connection()
        try:
            server.noop()
        finally:
            try:
                server.quit()
            except Exception:
                pass

    def _send_test_sync(self, recipient: str) -> str:
        cfg = self.settings.smtp_config
        msg = EmailMessage()
        msg["Subject"] = "Loan Pipeline Console — SMTP test"
        msg["From"] = cfg["from_addr"] or cfg["username"]
        msg["To"] = recipient
        msg.set_content(
            "This is a test email from the Loan Pipeline Console.\n"
            f"If you received this, SMTP is configured correctly.\n\n"
            f"Sent at {datetime.now(timezone.utc).isoformat()}\n"
            f"From host: {cfg['host']}:{cfg['port']}\n"
            f"As user: {cfg['username']}\n"
        )

        server = self._open_connection()
        try:
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return msg["From"]

    # ---------------- public async API ----------------
    async def test_connection(self) -> dict:
        if not self.is_configured():
            return {
                "ok": False,
                "stage": "config",
                "title": "SMTP is not fully configured",
                "detail": "Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM in .env, then recreate the api container.",
            }

        try:
            await asyncio.to_thread(self._test_connection_sync)
            cfg = self.settings.smtp_config
            return {
                "ok": True,
                "stage": "auth",
                "title": "Connection succeeded",
                "detail": f"Logged in as {cfg['username']} on {cfg['host']}:{cfg['port']}.",
            }
        except smtplib.SMTPAuthenticationError as exc:
            logger.exception("smtp_auth_failed")
            return {
                "ok": False,
                "stage": "auth",
                "title": "Authentication failed",
                "detail": _decode(exc.smtp_error) or str(exc),
                "hint": "Gmail/Outlook need an *App Password*, not your account password. Two-factor auth must be enabled first.",
            }
        except smtplib.SMTPConnectError as exc:
            logger.exception("smtp_connect_failed")
            return {
                "ok": False,
                "stage": "connect",
                "title": "Could not connect to SMTP server",
                "detail": _decode(exc.smtp_error) or str(exc),
                "hint": "Check SMTP_HOST and SMTP_PORT, and that this host can reach the SMTP server.",
            }
        except smtplib.SMTPHeloError as exc:
            logger.exception("smtp_helo_failed")
            return {
                "ok": False,
                "stage": "helo",
                "title": "Server rejected the HELO/EHLO greeting",
                "detail": _decode(exc.smtp_error) or str(exc),
            }
        except smtplib.SMTPNotSupportedError as exc:
            return {
                "ok": False,
                "stage": "starttls",
                "title": "Server does not support a required feature",
                "detail": str(exc),
            }
        except ssl.SSLError as exc:
            logger.exception("smtp_ssl_error")
            return {
                "ok": False,
                "stage": "tls",
                "title": "TLS error",
                "detail": str(exc),
                "hint": "Use port 587 with STARTTLS or 465 for implicit SSL. Some providers reject other combos.",
            }
        except (socket.gaierror, socket.timeout, ConnectionError, OSError) as exc:
            logger.exception("smtp_network_error")
            return {
                "ok": False,
                "stage": "network",
                "title": "Network error reaching SMTP host",
                "detail": str(exc),
                "hint": "Is the host name correct? Can this container reach the public internet?",
            }
        except smtplib.SMTPException as exc:
            logger.exception("smtp_protocol_error")
            return {
                "ok": False,
                "stage": "smtp",
                "title": "SMTP protocol error",
                "detail": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("smtp_unexpected_error")
            return {
                "ok": False,
                "stage": "unexpected",
                "title": "Unexpected error",
                "detail": str(exc),
            }

    async def send_test_email(self, recipient: str) -> dict:
        recipient = (recipient or "").strip()
        if not recipient or "@" not in recipient:
            return {
                "ok": False,
                "stage": "input",
                "title": "Invalid recipient",
                "detail": "Enter a valid email address (e.g. you@example.com).",
            }
        if not self.is_configured():
            return {
                "ok": False,
                "stage": "config",
                "title": "SMTP is not fully configured",
                "detail": "Set SMTP_* env vars before sending a test email.",
            }

        try:
            sender = await asyncio.to_thread(self._send_test_sync, recipient)
            return {
                "ok": True,
                "stage": "send",
                "title": "Test email sent",
                "detail": f"Sent to {recipient} from {sender}. Check the inbox (and spam folder).",
            }
        except smtplib.SMTPRecipientsRefused as exc:
            return {
                "ok": False,
                "stage": "recipient",
                "title": "Recipient refused",
                "detail": str(exc.recipients) if hasattr(exc, "recipients") else str(exc),
            }
        except smtplib.SMTPSenderRefused as exc:
            return {
                "ok": False,
                "stage": "sender",
                "title": "Sender refused",
                "detail": _decode(exc.smtp_error) or str(exc),
                "hint": "Check SMTP_FROM matches an address the SMTP account is allowed to send as.",
            }
        except smtplib.SMTPDataError as exc:
            return {
                "ok": False,
                "stage": "data",
                "title": "Server rejected the message body",
                "detail": _decode(exc.smtp_error) or str(exc),
            }
        except smtplib.SMTPAuthenticationError as exc:
            return {
                "ok": False,
                "stage": "auth",
                "title": "Authentication failed",
                "detail": _decode(exc.smtp_error) or str(exc),
                "hint": "Use an App Password — Gmail/Outlook reject account passwords for SMTP.",
            }
        except (socket.gaierror, socket.timeout, ConnectionError, OSError) as exc:
            return {
                "ok": False,
                "stage": "network",
                "title": "Network error reaching SMTP host",
                "detail": str(exc),
            }
        except ssl.SSLError as exc:
            return {
                "ok": False,
                "stage": "tls",
                "title": "TLS error",
                "detail": str(exc),
            }
        except smtplib.SMTPException as exc:
            return {
                "ok": False,
                "stage": "smtp",
                "title": "SMTP error",
                "detail": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("smtp_send_unexpected_error")
            return {
                "ok": False,
                "stage": "unexpected",
                "title": "Unexpected error",
                "detail": str(exc),
            }
