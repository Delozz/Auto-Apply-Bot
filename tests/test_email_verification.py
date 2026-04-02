"""
test_email_verification.py

Sends a fake 8-digit verification code email to devoninternships@gmail.com
(from itself via SMTP), then immediately runs fetch_verification_code() to
verify the IMAP reader can find and extract it.

Run with:
    PYTHONPATH=. python3 tests/test_email_verification.py
"""
import imaplib
import smtplib
import time
import random
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.utils.logger import logger


# ─── Send a fake verification code email ──────────────────────────────────────

def send_test_code_email(code: str) -> bool:
    """Send an email containing a fake verification code to the Gmail inbox."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your verification code"
    msg["From"] = settings.gmail_address
    msg["To"] = settings.gmail_address

    body_text = f"Your verification code is: {code}\n\nDo not share this code with anyone."
    body_html = f"""
    <html><body>
      <p>Your application verification code is:</p>
      <h2 style="letter-spacing: 4px;">{code}</h2>
      <p>This code expires in 10 minutes.</p>
    </body></html>
    """

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_address, settings.gmail_app_password)
            server.sendmail(settings.gmail_address, settings.gmail_address, msg.as_string())
        logger.info(f"Test email sent with code: {code}")
        return True
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        return False


# ─── Direct IMAP diagnostic — show exactly what the reader sees ───────────────

def diagnose_inbox(sender_hint: str = "") -> None:
    """
    Print a raw diagnostic of all UNSEEN emails in the inbox so we can
    see exactly what the IMAP reader is working with.
    """
    logger.info("─── IMAP Diagnostic ───────────────────────────────────────")
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
            mail.login(settings.gmail_address, settings.gmail_app_password)
            mail.select("INBOX")

            criteria = f'(UNSEEN FROM "{sender_hint}")' if sender_hint else "(UNSEEN)"
            _, data = mail.search(None, criteria)
            message_ids = data[0].split()
            logger.info(f"UNSEEN messages matching '{criteria}': {len(message_ids)}")

            for msg_id in reversed(message_ids[-5:]):
                _, msg_data = mail.fetch(msg_id, "(BODY.PEEK[])")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                logger.info(f"  From: {msg.get('From')} | Subject: {msg.get('Subject')}")

                # Extract body
                body_parts = []
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() in ("text/plain", "text/html"):
                            try:
                                body_parts.append(
                                    part.get_payload(decode=True).decode("utf-8", errors="replace")
                                )
                            except Exception:
                                pass
                else:
                    try:
                        body_parts.append(
                            msg.get_payload(decode=True).decode("utf-8", errors="replace")
                        )
                    except Exception:
                        pass

                body = " ".join(body_parts)
                logger.info(f"  Body preview: {body[:200]!r}")

    except Exception as e:
        logger.error(f"IMAP diagnostic failed: {e}")
    logger.info("───────────────────────────────────────────────────────────")


# ─── Main test ────────────────────────────────────────────────────────────────

def run_test():
    fake_code = str(random.randint(10000000, 99999999))  # 8 digits
    logger.info(f"=== Starting email verification test (code: {fake_code}) ===")

    # Step 1: Send the email
    sent = send_test_code_email(fake_code)
    if not sent:
        logger.error("FAIL — could not send test email (check SMTP credentials)")
        return

    # Step 2: Wait for delivery
    logger.info("Waiting 10s for email delivery...")
    time.sleep(10)

    # Step 3: Run raw IMAP diagnostic first
    diagnose_inbox(sender_hint=settings.gmail_address)

    # Step 4: Run the actual fetch function
    logger.info("Running fetch_verification_code()...")
    from app.utils.email_reader import fetch_verification_code
    code = fetch_verification_code(
        sender_hint=settings.gmail_address,
        max_wait_seconds=30,
        poll_interval=3,
    )

    # Step 5: Report result
    logger.info("─── Result ────────────────────────────────────────────────")
    if code == fake_code:
        logger.info(f"✅ PASS — fetched code '{code}' matches sent code '{fake_code}'")
    elif code:
        logger.warning(f"⚠️  PARTIAL — fetched '{code}' but expected '{fake_code}'")
    else:
        logger.error(f"❌ FAIL — could not retrieve code (expected '{fake_code}')")
    logger.info("───────────────────────────────────────────────────────────")


if __name__ == "__main__":
    run_test()
