"""IMAP-Service — liest die neuesten E-Mails direkt aus dem HTW-Berlin-Postfach.

Nutzt imaplib (Standardbibliothek) statt der Gmail API, da das HTW-Postfach
nicht mit Gmail verbunden ist.
"""

from __future__ import annotations

import email
import imaplib
import logging
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.core.config import settings
from app.services.email_models import FetchedEmail

logger = logging.getLogger(__name__)


def _decode_mime_words(value: str | None) -> str:
    if not value:
        return ""

    parts = []

    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            safe_charset = charset

            if not safe_charset or safe_charset.lower() in {"unknown-8bit", "x-unknown", "unknown"}:
                safe_charset = "utf-8"

            try:
                parts.append(text.decode(safe_charset, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                parts.append(text.decode("latin-1", errors="replace"))
        else:
            parts.append(text)

    return "".join(parts)


def _extract_plain_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/plain" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                try:
                    return payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    continue
        return ""

    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return ""


def _log_effective_config() -> None:
    """Logs exactly what config values this process is using, without ever
    logging the password itself - only its length. Settings() is a module-level
    singleton created once at process startup (app/core/config.py), so if .env
    was edited after the backend started, these values are stale until restart."""
    env_path = Path(".env").resolve()
    logger.info(
        "IMAP debug: cwd=%s .env resolved to %s (exists=%s)",
        Path.cwd(), env_path, env_path.exists(),
    )
    logger.info(
        "IMAP debug: host=%r port=%r (type=%s) username=%r password_len=%d",
        settings.htw_imap_host,
        settings.htw_imap_port,
        type(settings.htw_imap_port).__name__,
        settings.htw_email_address,
        len(settings.htw_email_password or ""),
    )


def _connect_and_login() -> imaplib.IMAP4_SSL:
    """Opens the SSL connection and logs in. Shared by fetch_latest_emails() and
    test_imap_connection() so both exercise the identical code path.

    Raises:
        RuntimeError: on missing config, connection failure, or login failure.
    """
    _log_effective_config()

    host = settings.htw_imap_host
    port = settings.htw_imap_port
    # Strip whitespace defensively - a trailing newline/space pasted into .env
    # is a common, invisible cause of AUTHENTICATIONFAILED.
    username = (settings.htw_email_address or "").strip()
    password = (settings.htw_email_password or "").strip()

    if not (username and password and host):
        raise RuntimeError(
            "HTW-IMAP-Zugangsdaten sind nicht konfiguriert. "
            "HTW_EMAIL_ADDRESS, HTW_EMAIL_PASSWORD und HTW_IMAP_HOST in backend/.env setzen."
        )

    try:
        conn = imaplib.IMAP4_SSL(host, port)
        logger.info("IMAP debug: SSL connection to %s:%s succeeded.", host, port)
    except Exception as exc:
        logger.error("IMAP debug: SSL connection failed: %s", exc)
        raise RuntimeError(f"Verbindung zum IMAP-Server fehlgeschlagen: {exc}") from exc

    try:
        cap_status, cap_data = conn.capability()
        logger.info("IMAP debug: CAPABILITY status=%s data=%s", cap_status, cap_data)
        # If the server advertises LOGINDISABLED, the plain LOGIN command used
        # below is rejected at the protocol level regardless of credentials -
        # that's a real (different) cause worth distinguishing from bad creds.
        capabilities = b" ".join(cap_data or []).upper() if cap_data else b""
        if b"LOGINDISABLED" in capabilities:
            logger.warning(
                "IMAP debug: server advertises LOGINDISABLED - plain LOGIN will "
                "be rejected no matter what credentials are used."
            )
    except Exception as exc:
        logger.warning("IMAP debug: CAPABILITY request failed (continuing): %s", exc)

    logger.info(
        "IMAP debug: attempting login as %r (password length=%d, after stripping whitespace)",
        username, len(password),
    )

    try:
        login_status, login_data = conn.login(username, password)
        logger.info("IMAP debug: LOGIN response: status=%s data=%s", login_status, login_data)
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP debug: LOGIN failed: %s", exc)
        raise RuntimeError(f"IMAP-Login fehlgeschlagen: {exc}") from exc

    return conn


def fetch_latest_emails(limit: int = 20) -> list[FetchedEmail]:
    """Verbindet sich per IMAP über SSL mit dem HTW-Postfach und liest die
    `limit` neuesten E-Mails aus dem INBOX-Ordner (neueste zuerst).

    Diese Funktion ist blockierend (imaplib) und sollte über
    `asyncio.to_thread` aufgerufen werden.

    Raises:
        RuntimeError: bei fehlender Konfiguration oder IMAP-Fehlern.
    """
    conn = _connect_and_login()

    try:
        select_status, select_data = conn.select("INBOX")
        logger.info("IMAP debug: SELECT INBOX status=%s data=%s", select_status, select_data)

        status, data = conn.search(None, "ALL")
        logger.info("IMAP debug: SEARCH ALL status=%s", status)
        if status != "OK":
            raise RuntimeError("IMAP-Suche im INBOX-Ordner fehlgeschlagen.")

        all_ids = data[0].split()
        latest_ids = all_ids[-limit:] if len(all_ids) > limit else all_ids

        emails: list[FetchedEmail] = []
        for msg_id in reversed(latest_ids):
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            date_header = msg.get("Date") or ""
            try:
                date_str = parsedate_to_datetime(date_header).isoformat()
            except (TypeError, ValueError):
                date_str = date_header

            body = _extract_plain_text(msg).strip()

            emails.append(
                FetchedEmail(
                    subject=_decode_mime_words(msg.get("Subject")),
                    sender=_decode_mime_words(msg.get("From")),
                    date=date_str,
                    body=body,
                    snippet=body[:200].strip(),
                )
            )

        return emails
    except imaplib.IMAP4.error as exc:
        raise RuntimeError(f"IMAP-Abfrage fehlgeschlagen: {exc}") from exc
    finally:
        try:
            conn.logout()
        except Exception:
            logger.warning("IMAP-Logout fehlgeschlagen (Verbindung wird trotzdem verworfen).")


def test_imap_connection() -> None:
    """Standalone debug helper - connect, login, list mailboxes, logout.

    Deliberately bypasses FastAPI, asyncio.to_thread and Gemini entirely so
    IMAP connectivity/auth can be isolated from the rest of the stack. Prints
    every IMAP server response (never the password - see _connect_and_login).

    Run directly from backend/:  python -m app.services.imap_email_service
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print("=== IMAP connection test ===")

    conn = _connect_and_login()
    try:
        list_status, list_data = conn.list()
        print(f"LIST response: status={list_status}")
        for line in list_data or []:
            print(" ", line)
    finally:
        logout_status, logout_data = conn.logout()
        print(f"LOGOUT response: status={logout_status} data={logout_data}")

    print("=== IMAP connection test: SUCCESS ===")


if __name__ == "__main__":
    test_imap_connection()
