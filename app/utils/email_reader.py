"""
email_reader.py

Polls Gmail IMAP for a verification code email after form submission.

Setup (one-time):
1. Enable IMAP in Gmail: Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP
2. Generate an App Password: myaccount.google.com/apppasswords
   (requires 2FA to be enabled on the account)
3. Add to .env:
     GMAIL_ADDRESS=devoninternships@gmail.com
     GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

The reader searches UNSEEN emails, extracts any 8-digit code it finds,
marks the email read so the code can't be reused, and returns the code.
"""
import imaplib
import email
import email.message
import re
import time
from app.config import settings
from app.utils.logger import logger


def fetch_verification_code(
    sender_hint: str = "",
    max_wait_seconds: int = 90,
    poll_interval: int = 4,
) -> str | None:
    """
    Poll Gmail inbox until an 8-digit verification code arrives.

    Args:
        sender_hint: Optional partial sender address to narrow the search
                     (e.g. "greenhouse.io"). Leave blank to check all unread.
        max_wait_seconds: How long to keep polling before giving up.
        poll_interval:    Seconds between each inbox check.

    Returns:
        The 8-digit code string, or None if timed out.
    """
    if not settings.gmail_app_password:
        logger.error("GMAIL_APP_PASSWORD not set — cannot fetch verification code")
        return None

    deadline = time.time() + max_wait_seconds
    logger.info(f"Polling Gmail for verification code (up to {max_wait_seconds}s)...")

    while time.time() < deadline:
        try:
            code = _check_inbox_for_code(sender_hint)
            if code:
                return code
        except Exception as e:
            logger.warning(f"Email poll error: {e}")

        remaining = deadline - time.time()
        if remaining > poll_interval:
            logger.debug(f"Code not found yet, retrying in {poll_interval}s...")
            time.sleep(poll_interval)
        elif remaining > 0:
            time.sleep(remaining)

    logger.warning("Timed out waiting for verification code email")
    return None


def _check_inbox_for_code(sender_hint: str = "") -> str | None:
    """Single inbox check — returns 8-digit code string if found, else None."""
    with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
        mail.login(settings.gmail_address, settings.gmail_app_password)
        mail.select("INBOX")

        # Build search criteria
        if sender_hint:
            criteria = f'(UNSEEN FROM "{sender_hint}")'
        else:
            criteria = "(UNSEEN)"

        _, data = mail.search(None, criteria)
        message_ids = data[0].split()

        if not message_ids:
            return None

        # Check the most recent 5 unread messages.
        # Use BODY.PEEK[] instead of RFC822 so the fetch does NOT auto-mark
        # the message as \Seen — we only mark it seen if we actually use the code.
        for msg_id in reversed(message_ids[-5:]):
            _, msg_data = mail.fetch(msg_id, "(BODY.PEEK[])")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            body = _extract_body(msg)
            code = _find_verification_code(body)
            if code:
                logger.info(f"Verification code found in email from: {msg.get('From', '?')}")
                # Mark read so we don't reuse this code on the next poll
                mail.store(msg_id, "+FLAGS", "\\Seen")
                return code

    return None


def _extract_body(msg: email.message.Message) -> str:
    """Concatenate all text/plain and text/html parts from the email."""
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    parts.append(
                        part.get_payload(decode=True).decode("utf-8", errors="replace")
                    )
                except Exception:
                    pass
    else:
        try:
            parts.append(
                msg.get_payload(decode=True).decode("utf-8", errors="replace")
            )
        except Exception:
            pass
    return " ".join(parts)


def _find_verification_code(text: str) -> str | None:
    """
    Extract a verification code from email body text.

    Strategy:
    1. Prominent HTML tags (<h1>/<h2>/<b>/<strong>) — ATS platforms put codes here
    2. Context-aware plain text: alphanumeric token after "code:" / "code is" etc.
    3. Standalone 8-digit codes: 12345678
    4. Space/dash-separated pairs: 1234 5678 / 1234-5678
    5. 6-digit codes (fallback): 123456
    """
    def _is_mixed(s: str) -> bool:
        return bool(re.search(r'[A-Za-z]', s) and re.search(r'[0-9]', s))

    # 1. Extract content from prominent tags — strip inner HTML, check for code
    for tag in ('h1', 'h2', 'b', 'strong', 'span', 'td', 'p'):
        for m in re.finditer(
            rf'<{tag}[^>]*>(.*?)</{tag}>',
            text,
            re.IGNORECASE | re.DOTALL,
        ):
            inner = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            # Accept 6-12 char tokens: pure digit OR mixed alnum
            token_m = re.fullmatch(r'[A-Za-z0-9]{6,12}', inner)
            if token_m:
                return inner

    # 2. Context-aware: token immediately after "code" keyword in plain text
    for m in re.finditer(
        r'(?:code|security code|verification code)\s*[:\-]?\s*([A-Za-z0-9]{6,12})',
        text,
        re.IGNORECASE,
    ):
        candidate = m.group(1)
        if _is_mixed(candidate) or candidate.isdigit():
            return candidate

    # 3. 8 contiguous digits
    m = re.search(r'(?<!\d)(\d{8})(?!\d)', text)
    if m:
        return m.group(1)

    # 4. 4+4 with separator
    m = re.search(r'(?<!\d)(\d{4})[\s\-](\d{4})(?!\d)', text)
    if m:
        return m.group(1) + m.group(2)

    # 5. 6-digit fallback
    m = re.search(r'(?<!\d)(\d{6})(?!\d)', text)
    if m:
        return m.group(1)

    return None
