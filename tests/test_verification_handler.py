"""
test_verification_handler.py

End-to-end test for handle_verification_code():
  1. Opens a local page that mimics Greenhouse's security code form.
  2. Calls handle_verification_code() with the real Greenhouse sender.
  3. Asserts the code field was filled and the submit button clicked.

Prerequisites:
  - Unread email from no-reply@us.greenhouse-mail.io in the Gmail inbox.
  - GMAIL_ADDRESS and GMAIL_APP_PASSWORD set in .env.

Run with:
    PYTHONPATH=. python3 tests/test_verification_handler.py
"""
import asyncio
from pathlib import Path
from app.automation.playwright_engine import launch_browser, close_browser
from app.automation.submission_handler import handle_verification_code
from app.utils.logger import logger

VERIFICATION_PAGE = Path(__file__).parent / "test_verification_form.html"
GREENHOUSE_SENDER = "no-reply@us.greenhouse-mail.io"


def _build_test_page(char_boxes: bool = False) -> Path:
    """
    Write a minimal HTML page that mimics Greenhouse's security code screen.

    char_boxes=False → single text input (original style)
    char_boxes=True  → one input[maxlength="1"] per character (box style)
    """
    if char_boxes:
        # 8 individual character boxes — mirrors real Greenhouse layout
        boxes = "\n    ".join(
            f'<input type="text" maxlength="1" '
            f'style="font-size:1.4rem;width:36px;text-align:center;margin:2px" />'
            for _ in range(8)
        )
        form_body = f"""
    <div id="char-inputs" style="display:flex;justify-content:center;gap:4px">
      {boxes}
    </div>"""
        js_collect = """
      var inputs = document.querySelectorAll('#char-inputs input');
      var code = Array.from(inputs).map(i => i.value).join('');"""
    else:
        form_body = """
    <input
      type="text"
      id="security_code"
      name="code"
      maxlength="20"
      placeholder="Enter code"
      style="font-size:1.4rem;padding:10px;width:200px;text-align:center"
    />"""
        js_collect = """
      var code = document.getElementById('security_code').value;"""

    html = f"""<!DOCTYPE html>
<html>
<head><title>Security Code – Test</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center">
  <h2>Enter your security code</h2>
  <p>Copy and paste this code into the security code field on your application.</p>
  <form id="verify-form" onsubmit="handleSubmit(event)">
    {form_body}
    <br/><br/>
    <button type="submit" style="padding:10px 30px;font-size:1rem">Verify</button>
  </form>
  <p id="result" style="margin-top:20px;font-weight:bold;color:green"></p>
  <script>
    function handleSubmit(e) {{
      e.preventDefault();
      {js_collect}
      document.getElementById('result').textContent =
        code ? 'Code submitted: ' + code : 'No code entered';
    }}
  </script>
</body>
</html>"""
    VERIFICATION_PAGE.write_text(html)
    return VERIFICATION_PAGE


async def _run_scenario(label: str, char_boxes: bool, sender_hint: str) -> bool:
    page_path = _build_test_page(char_boxes=char_boxes)
    page_url = f"file://{page_path.resolve()}"

    playwright, browser, context, page = await launch_browser(headless=False)
    try:
        await page.goto(page_url)
        await page.wait_for_timeout(1000)

        success = await handle_verification_code(page, sender_hint=sender_hint)
        await page.wait_for_timeout(2000)

        result_text = await page.text_content("#result")

        if char_boxes:
            boxes = await page.query_selector_all('input[maxlength="1"]')
            entered = "".join([await b.input_value() for b in boxes])
        else:
            entered = await page.input_value('input[name="code"]')

        logger.info(f"─── {label} ─────────────────────────────────")
        if success and entered and not entered.strip() == "":
            logger.info(f"✅ PASS")
            logger.info(f"   Code entered : {entered!r}")
            logger.info(f"   Page result  : {result_text!r}")
            passed = True
        elif entered:
            logger.warning(f"⚠️  PARTIAL — filled {entered!r} but submit returned {success}")
            passed = False
        else:
            logger.error(f"❌ FAIL — nothing entered (handler returned {success})")
            passed = False
        logger.info("─────────────────────────────────────────────────")

        await page.wait_for_timeout(2000)
        return passed
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        return False
    finally:
        await close_browser(playwright, browser)


async def run_test():
    logger.info("=== Verification Handler Tests ===")

    p1 = await _run_scenario(
        "Scenario 1: single text field",
        char_boxes=False,
        sender_hint=GREENHOUSE_SENDER,
    )
    p2 = await _run_scenario(
        "Scenario 2: individual character boxes",
        char_boxes=True,
        sender_hint=GREENHOUSE_SENDER,
    )

    logger.info("=== Summary ===")
    logger.info(f"  Single field  : {'✅ PASS' if p1 else '❌ FAIL'}")
    logger.info(f"  Char boxes    : {'✅ PASS' if p2 else '❌ FAIL'}")


if __name__ == "__main__":
    asyncio.run(run_test())
