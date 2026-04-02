# Plan: Post-Application Recruiter Outreach

## Summary
After a job application is submitted via `run_pipeline.py`, automatically search LinkedIn for a recruiter at the applied company, generate a personalized 280-character connection message referencing the specific role, present a human-approval gate, send the connection request if approved, and deduplicate so the same company is never targeted twice.

## User Story
As Devon (the job applicant), I want the bot to automatically reach out to a recruiter at each company I apply to, so that my application gets a human touchpoint without me having to manually search LinkedIn after every submission.

## Problem → Solution
Outreach infrastructure exists but requires a manually maintained `OUTREACH_TARGETS` list, opens a new browser per operation (losing LinkedIn session state), and has no deduplication. → Hook `run_post_application_outreach()` into `run_pipeline.py` post-submit, share a single authenticated LinkedIn session across search + connect, and track sent outreach in `data/outreach_log.json`.

## Metadata
- **Complexity**: Medium
- **Source PRD**: N/A
- **PRD Phase**: N/A
- **Estimated Files**: 9 files (2 new, 7 modified)

---

## UX Design

### Before
```
[Application submitted]
       ↓
mark_as_applied() called
       ↓
Pipeline moves to next job
       ↓
User must manually open LinkedIn,
find a recruiter, write a message,
and send a connection request
```

### After
```
[Application submitted]
       ↓
mark_as_applied() called
       ↓
LinkedIn browser opens automatically
       ↓
Recruiter found at company
       ↓
Personalized message generated (role-specific)
       ↓
┌─────────────────────────────────────────────┐
│  Recruiter : Jane Doe                       │
│  Profile   : linkedin.com/in/jane-doe       │
│  Message   : Hi Jane, I just applied for    │
│              the Quant Dev Intern role at   │
│              Point72 and wanted to connect. │
│              What qualities stand out in    │
│              top candidates?                │
│                                             │
│  Send connection request? [y/n]:            │
└─────────────────────────────────────────────┘
       ↓
Outreach logged → pipeline continues
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Post-submit | Nothing happens | LinkedIn opens automatically | Happens inside `process_job()` |
| Recruiter gate | N/A | `y/n` prompt with full message preview | Human always approves before send |
| Duplicate run | Would re-send | Skipped silently | Checked via `outreach_log.json` |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `app/workflows/run_pipeline.py` | 178-192 | Integration point — post-submit block |
| P0 | `app/utils/application_tracker.py` | all | Pattern to mirror for outreach tracker |
| P0 | `app/automation/playwright_engine.py` | 1-46 | `launch_browser` signature to extend |
| P1 | `app/outreach/recruiter_finder.py` | all | Function to refactor |
| P1 | `app/outreach/connection_handler.py` | all | Function to refactor |
| P1 | `app/outreach/linkedin_message_gen.py` | all | Already works — no changes needed |
| P2 | `app/workflows/outreach_pipeline.py` | all | Fix hardcoded targets |
| P2 | `prompts/recruiter_message.txt` | all | Prompt template already written |

---

## Patterns to Mirror

### LOGGING_PATTERN
// SOURCE: app/utils/application_tracker.py:43
```python
logger.info(f"Tracked: {company} — {role}")
logger.warning(f"Could not update applied_jobs.json: {e}")
```

### JSON_FILE_PATTERN
// SOURCE: app/utils/application_tracker.py:29-44
```python
def mark_as_applied(url: str, company: str, role: str) -> None:
    try:
        existing: list[dict] = []
        if APPLIED_JOBS_FILE.exists():
            with APPLIED_JOBS_FILE.open() as f:
                existing = json.load(f)
        existing.append({
            "url": url,
            "company": company,
            "role": role,
            "submitted_at": datetime.utcnow().isoformat(),
        })
        with APPLIED_JOBS_FILE.open("w") as f:
            json.dump(existing, f, indent=2)
        logger.info(f"Tracked: {company} — {role}")
    except Exception as e:
        logger.warning(f"Could not update applied_jobs.json: {e}")
```

### BROWSER_LAUNCH_PATTERN
// SOURCE: app/automation/playwright_engine.py:1-46
```python
async def launch_browser(headless: bool = False):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 ...",
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()
    return playwright, browser, context, page
```

### ERROR_WRAPPING_PATTERN
// SOURCE: app/workflows/run_pipeline.py:206-210
```python
except KeyboardInterrupt:
    raise
except Exception as e:
    logger.error(f"Failed on {job.company}: {e}")
    return "failed"
```

### HUMAN_GATE_PATTERN
// SOURCE: app/outreach/connection_handler.py:28-35
```python
decision = input(f"\n  Send connection request? [y/n]: ").strip().lower()
if decision == "y":
    await send_btn.click()
    logger.info("✅ Connection request sent")
    return True
else:
    logger.info("⏭️  Skipped")
    return False
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `app/utils/constants.py` | UPDATE | Add `OUTREACH_LOG_FILE`, `LINKEDIN_SESSION_FILE` |
| `app/utils/application_tracker.py` | UPDATE | Add `has_outreach_been_sent()`, `mark_outreach_sent()` |
| `app/automation/playwright_engine.py` | UPDATE | Add `launch_browser_with_session()` |
| `app/outreach/linkedin_auth.py` | CREATE | LinkedIn login + session persistence |
| `app/outreach/recruiter_finder.py` | UPDATE | Refactor to accept existing `page` param |
| `app/outreach/connection_handler.py` | UPDATE | Refactor to accept existing `page` param; handle "More" dropdown |
| `app/outreach/outreach_orchestrator.py` | CREATE | `run_post_application_outreach()` — single entry point |
| `app/workflows/run_pipeline.py` | UPDATE | Import orchestrator; call after `mark_as_applied` |
| `app/workflows/outreach_pipeline.py` | UPDATE | Replace hardcoded `OUTREACH_TARGETS` with `applied_jobs.json` reader |
| `.gitignore` | UPDATE | Exclude `linkedin_session.json`, `outreach_log.json` |

## NOT Building
- Automatic follow-up messages after connection is accepted
- LinkedIn message DMs (only connection request notes)
- Outreach to companies not applied to via this pipeline
- Retry logic for failed connection attempts
- Email outreach (LinkedIn only)

---

## Step-by-Step Tasks

### Task 1: Add constants
- **ACTION**: Add two path constants to `app/utils/constants.py`
- **IMPLEMENT**: After `APPLIED_JOBS_FILE = DATA_DIR / "applied_jobs.json"`, add:
  ```python
  OUTREACH_LOG_FILE = DATA_DIR / "outreach_log.json"
  LINKEDIN_SESSION_FILE = DATA_DIR / "linkedin_session.json"
  ```
- **MIRROR**: NAMING_CONVENTION — `SCREAMING_SNAKE_CASE` `Path` constants, same pattern as `APPLIED_JOBS_FILE`
- **IMPORTS**: None needed
- **GOTCHA**: None
- **VALIDATE**: `python3 -c "from app.utils.constants import OUTREACH_LOG_FILE, LINKEDIN_SESSION_FILE; print(OUTREACH_LOG_FILE)"`

---

### Task 2: Add outreach deduplication to `application_tracker.py`
- **ACTION**: Append two functions to the end of `app/utils/application_tracker.py`
- **IMPLEMENT**:
  ```python
  # extend existing import:
  from app.utils.constants import APPLIED_JOBS_FILE, OUTREACH_LOG_FILE

  def has_outreach_been_sent(company: str) -> bool:
      """Return True if any outreach has already been logged for this company."""
      if not OUTREACH_LOG_FILE.exists():
          return False
      try:
          with OUTREACH_LOG_FILE.open() as f:
              data = json.load(f)
          return any(entry["company"].lower() == company.lower() for entry in data)
      except Exception as e:
          logger.warning(f"Could not read outreach_log.json: {e}")
          return False

  def mark_outreach_sent(company: str, recruiter_name: str, profile_url: str) -> None:
      """Append a sent-outreach record to outreach_log.json."""
      try:
          existing: list[dict] = []
          if OUTREACH_LOG_FILE.exists():
              with OUTREACH_LOG_FILE.open() as f:
                  existing = json.load(f)
          existing.append({
              "company": company,
              "recruiter_name": recruiter_name,
              "profile_url": profile_url,
              "sent_at": datetime.utcnow().isoformat(),
          })
          with OUTREACH_LOG_FILE.open("w") as f:
              json.dump(existing, f, indent=2)
          logger.info(f"Outreach logged: {recruiter_name} @ {company}")
      except Exception as e:
          logger.warning(f"Could not update outreach_log.json: {e}")
  ```
- **MIRROR**: JSON_FILE_PATTERN — identical structure to `mark_as_applied`
- **IMPORTS**: `OUTREACH_LOG_FILE` added to existing constants import
- **GOTCHA**: `datetime` and `json` are already imported in this file
- **VALIDATE**: Write a test that calls `mark_outreach_sent("TestCo", "Jane", "url")` and asserts `has_outreach_been_sent("TestCo")` returns `True` and `has_outreach_been_sent("testco")` (lowercase) also returns `True`

---

### Task 3: Add `launch_browser_with_session` to `playwright_engine.py`
- **ACTION**: Add new function after the existing `launch_browser` function
- **IMPLEMENT**:
  ```python
  async def launch_browser_with_session(session_path: str, headless: bool = False):
      """
      Launch browser loading stored cookies/localStorage from session_path if it exists.
      Returns same (playwright, browser, context, page) tuple as launch_browser().
      """
      from pathlib import Path
      playwright = await async_playwright().start()
      browser = await playwright.chromium.launch(
          headless=headless,
          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
      )
      storage_state = str(session_path) if Path(session_path).exists() else None
      context = await browser.new_context(
          user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
          viewport={"width": 1280, "height": 800},
          locale="en-US",
          storage_state=storage_state,
      )
      await context.add_init_script(
          "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
      )
      page = await context.new_page()
      return playwright, browser, context, page
  ```
- **MIRROR**: BROWSER_LAUNCH_PATTERN — identical flags, user agent, viewport, init script
- **IMPORTS**: `async_playwright` already imported; `Path` imported locally to avoid circular risk
- **GOTCHA**: `storage_state=None` is valid Playwright — it just means no stored state; don't pass an empty string or it'll error
- **VALIDATE**: Call with a non-existent path and confirm a browser opens without error

---

### Task 4: Create `app/outreach/linkedin_auth.py`
- **ACTION**: Create new file
- **IMPLEMENT**:
  ```python
  """
  linkedin_auth.py — LinkedIn login and session persistence.
  Saves browser storage state (cookies + localStorage) to
  data/linkedin_session.json after a successful login.
  """
  from app.automation.playwright_engine import (
      launch_browser_with_session, close_browser, random_delay, human_type
  )
  from app.utils.constants import LINKEDIN_SESSION_FILE
  from app.config import settings
  from app.utils.logger import logger


  async def ensure_linkedin_session(page) -> bool:
      """Return True if the browser is already authenticated on LinkedIn."""
      try:
          await page.goto("https://www.linkedin.com/feed/", timeout=30000)
          await random_delay(2.0, 3.0)
          nav = await page.query_selector("nav.global-nav")
          if nav:
              logger.info("LinkedIn session active — no login needed")
              return True
          return False
      except Exception as e:
          logger.warning(f"Could not verify LinkedIn session: {e}")
          return False


  async def linkedin_login(page, context) -> bool:
      """
      Full email/password login. Saves storage state on success.
      Pauses for manual CAPTCHA completion if a checkpoint is detected.
      """
      email = settings.linkedin_email
      password = settings.linkedin_password
      if not email or not password:
          logger.error("linkedin_email and linkedin_password must be set in .env")
          return False
      try:
          await page.goto("https://www.linkedin.com/login", timeout=30000)
          await random_delay(1.5, 3.0)
          await human_type(page, 'input[name="session_key"]', email)
          await random_delay(0.5, 1.2)
          await human_type(page, 'input[name="session_password"]', password)
          await random_delay(0.8, 1.5)
          submit_btn = await page.query_selector('button[type="submit"]')
          if submit_btn:
              await submit_btn.click()
          await random_delay(3.0, 5.0)
          # Handle checkpoint / CAPTCHA
          if "checkpoint" in page.url or "challenge" in page.url:
              logger.warning("LinkedIn checkpoint detected — complete it in the browser then press Enter")
              input("  Press Enter after completing the checkpoint...")
              await random_delay(2.0, 3.0)
          nav = await page.query_selector("nav.global-nav")
          if not nav:
              logger.error("LinkedIn login failed — check credentials")
              return False
          await context.storage_state(path=str(LINKEDIN_SESSION_FILE))
          logger.info(f"LinkedIn session saved to {LINKEDIN_SESSION_FILE}")
          return True
      except Exception as e:
          logger.error(f"LinkedIn login error: {e}")
          return False


  async def get_authenticated_linkedin_page():
      """
      Launch browser with saved session; re-login if session is expired/missing.
      Returns (playwright, browser, context, page) or raises RuntimeError.
      """
      playwright, browser, context, page = await launch_browser_with_session(
          session_path=LINKEDIN_SESSION_FILE,
          headless=False,
      )
      logged_in = await ensure_linkedin_session(page)
      if not logged_in:
          logger.info("Session expired or missing — logging in...")
          success = await linkedin_login(page, context)
          if not success:
              await close_browser(playwright, browser)
              raise RuntimeError("Could not authenticate with LinkedIn")
      return playwright, browser, context, page
  ```
- **MIRROR**: BROWSER_LAUNCH_PATTERN, LOGGING_PATTERN
- **IMPORTS**: `launch_browser_with_session`, `close_browser`, `random_delay`, `human_type` from `playwright_engine`; `LINKEDIN_SESSION_FILE` from `constants`; `settings` from `config`
- **GOTCHA**: `human_type` requires a selector that resolves on the page — `input[name="session_key"]` is the LinkedIn login email field; `input[name="session_password"]` is the password field. These selectors are stable as of 2024.
- **VALIDATE**: Run the manual smoke test in Task 9

---

### Task 5: Refactor `recruiter_finder.py`
- **ACTION**: Replace entire file — split logic into `_search_recruiters_on_page(page, company)` and keep `search_recruiters(company)` as backward-compatible wrapper
- **IMPLEMENT**: See "Refactor `search_recruiters`" section above for full replacement code
- **MIRROR**: ERROR_WRAPPING_PATTERN — `try/except Exception as e` with `logger.warning`
- **IMPORTS**: Add `from playwright.async_api import Page`
- **GOTCHA**: The `_search_recruiters_on_page` helper must NOT open or close a browser — it receives an already-authenticated page. The `search_recruiters` wrapper handles its own browser lifecycle for backward compat.
- **VALIDATE**: `python3 -c "from app.outreach.recruiter_finder import search_recruiters, _search_recruiters_on_page; print('OK')"`

---

### Task 6: Refactor `connection_handler.py`
- **ACTION**: Replace entire file — split logic into `_send_connection_on_page(page, profile_url, message, recruiter_name)` and keep `send_connection_request` as wrapper; add "More" dropdown fallback
- **IMPLEMENT**: See "Refactor `send_connection_request`" section above for full replacement code
- **MIRROR**: HUMAN_GATE_PATTERN — show full message preview before asking y/n
- **IMPORTS**: Add `from playwright.async_api import Page`
- **GOTCHA 1**: "Connect" may be inside a "More" dropdown — check top-level first, then click "More" and look in `.artdeco-dropdown__content button:has-text("Connect")`
- **GOTCHA 2**: After clicking "Connect" the modal may show "Send without a note" on some profiles instead of "Add a note" — log a warning if not found but proceed with sending
- **GOTCHA 3**: After the user declines with "n", the modal must be dismissed — click `button:has-text("Discard")` or `button[aria-label="Dismiss"]` to avoid leaving a stale modal on the page
- **VALIDATE**: `python3 -c "from app.outreach.connection_handler import _send_connection_on_page, send_connection_request; print('OK')"`

---

### Task 7: Create `app/outreach/outreach_orchestrator.py`
- **ACTION**: Create new file containing `run_post_application_outreach(company, role, candidate)`
- **IMPLEMENT**:
  ```python
  """
  outreach_orchestrator.py

  Single entry point for post-application LinkedIn outreach.
  Called from run_pipeline.py after mark_as_applied().
  """
  from app.outreach.linkedin_auth import get_authenticated_linkedin_page
  from app.outreach.recruiter_finder import _search_recruiters_on_page
  from app.outreach.connection_handler import _send_connection_on_page
  from app.outreach.linkedin_message_gen import generate_recruiter_message
  from app.utils.application_tracker import has_outreach_been_sent, mark_outreach_sent
  from app.utils.validators import CandidateProfile
  from app.automation.playwright_engine import close_browser, random_delay
  from app.utils.logger import logger


  async def run_post_application_outreach(
      company: str,
      role: str,
      candidate: CandidateProfile,
      max_recruiters: int = 1,
  ) -> None:
      """
      Full post-application outreach flow.
      Skips silently if outreach already sent for this company.
      """
      if has_outreach_been_sent(company):
          logger.info(f"Outreach already sent for {company} — skipping")
          return

      logger.info(f"\nStarting recruiter outreach for {company} ({role})")

      playwright = browser = None
      try:
          playwright, browser, context, page = await get_authenticated_linkedin_page()

          recruiters = await _search_recruiters_on_page(page, company, max_results=max_recruiters)
          if not recruiters:
              logger.warning(f"No recruiters found for {company} — outreach skipped")
              return

          for recruiter in recruiters:
              recruiter_name = recruiter["name"]
              profile_url = recruiter.get("profile_url", "")
              if not profile_url:
                  continue

              message = generate_recruiter_message(
                  candidate=candidate,
                  recruiter_name=recruiter_name,
                  company=company,
                  role=role,
              )

              sent = await _send_connection_on_page(
                  page=page,
                  profile_url=profile_url,
                  message=message,
                  recruiter_name=recruiter_name,
              )

              if sent:
                  mark_outreach_sent(company, recruiter_name, profile_url)
                  break  # one connection per company per run

              await random_delay(5.0, 10.0)

      except RuntimeError as e:
          logger.error(f"Outreach aborted — LinkedIn auth failed: {e}")
      except Exception as e:
          logger.error(f"Outreach failed for {company}: {e}")
      finally:
          if playwright and browser:
              await close_browser(playwright, browser)
  ```
- **MIRROR**: ERROR_WRAPPING_PATTERN, LOGGING_PATTERN
- **IMPORTS**: As shown — all from within the project
- **GOTCHA**: `playwright = browser = None` before the try block so `finally` can safely check them even if `get_authenticated_linkedin_page` raises before assigning
- **VALIDATE**: `python3 -c "from app.outreach.outreach_orchestrator import run_post_application_outreach; print('OK')"`

---

### Task 8: Hook into `run_pipeline.py`
- **ACTION**: Add import and post-submit outreach call
- **IMPLEMENT**:

  **Import** (add after line with `from app.utils.application_tracker import load_applied_urls, mark_as_applied`):
  ```python
  from app.outreach.outreach_orchestrator import run_post_application_outreach
  ```

  **Post-submit block** — current code:
  ```python
  await handle_verification_code(page, sender_hint="no-reply@us.greenhouse-mail.io")
  mark_as_applied(job.application_url, job.company, job.role)
  confirmed = await confirm_submission(page)
  status = "submitted" if confirmed else "submit_attempted"
  ```
  Replace with:
  ```python
  await handle_verification_code(page, sender_hint="no-reply@us.greenhouse-mail.io")
  mark_as_applied(job.application_url, job.company, job.role)
  confirmed = await confirm_submission(page)
  status = "submitted" if confirmed else "submit_attempted"

  # Post-application: recruiter outreach on LinkedIn
  # Wrapped in try/except — outreach failure must never affect submission status
  try:
      await run_post_application_outreach(
          company=job.company,
          role=job.role,
          candidate=CANDIDATE,
      )
  except Exception as _outreach_err:
      logger.warning(f"Outreach step failed (submission already recorded): {_outreach_err}")
  ```
- **MIRROR**: ERROR_WRAPPING_PATTERN
- **GOTCHA**: The outreach call opens its OWN browser (via `get_authenticated_linkedin_page`). It runs after the application form browser is closed (the `finally: await close_browser(...)` in `process_job` runs after this block). Order is: submit → verify code → mark applied → confirm → **outreach** → close app browser.
- **VALIDATE**: Dry-run the pipeline — after a submission, observe "Starting recruiter outreach for X" in logs

---

### Task 9: Fix `outreach_pipeline.py`
- **ACTION**: Replace hardcoded `OUTREACH_TARGETS` with a function that reads `applied_jobs.json`
- **IMPLEMENT**:

  Add imports after existing imports:
  ```python
  import json
  from app.utils.constants import APPLIED_JOBS_FILE
  ```

  Replace hardcoded list with:
  ```python
  def _load_outreach_targets() -> list[dict]:
      """Read company+role pairs from applied_jobs.json."""
      if not APPLIED_JOBS_FILE.exists():
          logger.warning("applied_jobs.json not found — no outreach targets")
          return []
      try:
          with APPLIED_JOBS_FILE.open() as f:
              data = json.load(f)
          return [{"company": e["company"], "role": e["role"]} for e in data]
      except Exception as e:
          logger.warning(f"Could not read applied_jobs.json for outreach: {e}")
          return []
  ```

  In `_outreach_pipeline_async`, replace `for target in OUTREACH_TARGETS:` with:
  ```python
  targets = _load_outreach_targets()
  logger.info(f"Loaded {len(targets)} outreach target(s) from applied_jobs.json")
  for target in targets:
  ```
- **MIRROR**: JSON_FILE_PATTERN
- **GOTCHA**: `outreach_pipeline.py` still imports `CANDIDATE` from `apply_pipeline.py` — leave that import alone; it's fine
- **VALIDATE**: `python3 -c "from app.workflows.outreach_pipeline import _load_outreach_targets; print('OK')"`

---

### Task 10: Update `.gitignore`
- **ACTION**: Append two lines
- **IMPLEMENT**:
  ```
  data/linkedin_session.json
  data/outreach_log.json
  ```
- **GOTCHA**: `linkedin_session.json` contains live LinkedIn cookies — committing it is a security risk
- **VALIDATE**: `git status` after creating these files shows them as ignored

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `has_outreach_been_sent` — no file | Any company | `False` | Yes — missing file |
| `has_outreach_been_sent` — found | Company in log | `True` | No |
| `has_outreach_been_sent` — case insensitive | `"point72"` when log has `"Point72"` | `True` | Yes |
| `mark_outreach_sent` — creates file | New company | File created with entry | Yes — first write |
| `mark_outreach_sent` — appends | Existing file | New entry added, old preserved | No |
| `_load_outreach_targets` — no file | N/A | `[]` | Yes |
| `_load_outreach_targets` — valid file | `applied_jobs.json` with 3 entries | List of 3 dicts | No |

### Edge Cases Checklist
- [ ] `applied_jobs.json` does not exist when outreach pipeline runs
- [ ] Recruiter search returns empty list (no recruiters found)
- [ ] LinkedIn "Connect" button hidden behind "More" dropdown
- [ ] LinkedIn shows security checkpoint on login
- [ ] Profile shows "Follow" only (creator account)
- [ ] User presses `n` at approval gate
- [ ] Same company submitted twice — second run skips outreach

---

## Validation Commands

### Import Check
```bash
PYTHONPATH=. python3 -c "
from app.utils.constants import OUTREACH_LOG_FILE, LINKEDIN_SESSION_FILE
from app.utils.application_tracker import has_outreach_been_sent, mark_outreach_sent
from app.automation.playwright_engine import launch_browser_with_session
from app.outreach.linkedin_auth import get_authenticated_linkedin_page
from app.outreach.recruiter_finder import _search_recruiters_on_page
from app.outreach.connection_handler import _send_connection_on_page
from app.outreach.outreach_orchestrator import run_post_application_outreach
print('All imports OK')
"
```
EXPECT: `All imports OK`

### Deduplication Test
```bash
PYTHONPATH=. python3 -c "
from app.utils.application_tracker import mark_outreach_sent, has_outreach_been_sent
mark_outreach_sent('TestCo', 'Jane Doe', 'https://linkedin.com/in/janedoe')
assert has_outreach_been_sent('TestCo') == True
assert has_outreach_been_sent('testco') == True
assert has_outreach_been_sent('OtherCo') == False
print('Deduplication OK')
"
```
EXPECT: `Deduplication OK`

### Manual — LinkedIn Auth Smoke Test
```bash
PYTHONPATH=. python3 -c "
import asyncio
from app.outreach.linkedin_auth import get_authenticated_linkedin_page
from app.automation.playwright_engine import close_browser
async def test():
    pl, br, ctx, pg = await get_authenticated_linkedin_page()
    print('Logged in — URL:', pg.url)
    await close_browser(pl, br)
asyncio.run(test())
"
```
EXPECT: Browser opens, logs in, prints feed URL, saves `data/linkedin_session.json`

### Manual — Full Orchestrator Dry Run
```bash
PYTHONPATH=. python3 -c "
import asyncio
from app.outreach.outreach_orchestrator import run_post_application_outreach
from app.utils.validators import CandidateProfile
from app.utils.constants import RESUMES_DIR
CANDIDATE = CandidateProfile(
    name='Devon Lopez', email='devoninternships@gmail.com', phone='5127878221',
    education='Texas A&M University - Computer Science',
    skills=['Python', 'C++', 'SQL', 'Data Structures', 'Algorithms'],
    interests=['Quantitative Finance'],
    resume_path=str(RESUMES_DIR / 'Devon_Lopez_SWE_Quant.pdf'),
)
asyncio.run(run_post_application_outreach('Stripe', 'Software Engineer Intern', CANDIDATE))
"
```
EXPECT: LinkedIn opens, finds recruiter, shows message + gate, waits for y/n

---

## Acceptance Criteria
- [ ] After a submission in `run_pipeline.py`, a LinkedIn browser opens automatically
- [ ] A recruiter at the applied company is found (or gracefully skipped if none)
- [ ] The generated message references the specific role title
- [ ] Human approval gate shows recruiter name, profile URL, and full message before sending
- [ ] Connection request sent (or skipped) without crashing the pipeline
- [ ] `data/outreach_log.json` updated after a send
- [ ] Running the pipeline again for the same company: outreach skipped silently
- [ ] All import checks pass

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LinkedIn selectors change (`.entity-result__item`, `nav.global-nav`) | Medium | Recruiter search breaks | Log a warning and return empty list; fall back gracefully |
| LinkedIn rate-limits connection requests | Low (1/company) | Account flagged | Default `max_recruiters=1`; 30-90s delays preserved in `send_batch_outreach` |
| CAPTCHA on first login | Medium | Auth blocked | `linkedin_login()` pauses with `input()` for manual solve |
| "Connect" behind "More" dropdown | High | Request never sent | Two-step fallback implemented in `_send_connection_on_page` |
| Session expires mid-run | Low | Auth error | `ensure_linkedin_session()` re-logins if nav not found |
