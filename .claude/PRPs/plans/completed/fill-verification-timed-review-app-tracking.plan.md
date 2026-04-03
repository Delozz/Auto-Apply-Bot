# Plan: Fill Verification + Timed Review Gate + Application Tracking

## Summary
After adaptive autofill completes, the LLM verifies all required fields are properly filled via a screenshot. The human approval gate becomes a 15-second countdown that auto-submits on timeout (user can manually submit, skip, or end early). Applied job URLs are persisted to a JSON file so re-running the pipeline never re-applies to already-submitted jobs.

## User Story
As Devon running the apply pipeline repeatedly, I want verified form fills, a timed review prompt that doesn't block indefinitely, and automatic deduplication across runs, so that I can leave the bot running with minimal supervision and never double-apply.

## Problem → Solution
- Current: `pause_for_human_review()` blocks forever waiting for `input()`, no fill verification, `SKIP_ALREADY_APPLIED = True` flag exists but is never wired to actual skip logic → Current: forms may be partially filled and user must always manually approve.
- Desired: Vision LLM verifies fill → 15s countdown prompt auto-submits on timeout → submitted URLs logged to JSON → pipeline skips them next run.

## Metadata
- **Complexity**: Medium
- **Source PRD**: N/A
- **PRD Phase**: N/A
- **Estimated Files**: 4 (2 modified, 1 new, 1 modified lightly)

---

## UX Design

### Before
```
┌─────────────────────────────────────────────┐
│  [Autofill runs]                             │
│  "Review required: SWE Intern @ Stripe"      │
│  Submit? [y=yes / n=skip / q=quit bot]: _    │
│  (waits forever, no fill verification)       │
└─────────────────────────────────────────────┘
```

### After
```
┌─────────────────────────────────────────────┐
│  [Autofill runs]                             │
│  [Vision LLM scans form screenshot]          │
│  "✅ All required fields filled"             │
│    OR                                        │
│  "⚠️  Missing: 'Phone', 'Location'"          │
│                                              │
│  Submit SWE Intern @ Stripe?                 │
│  Auto-submitting in 12s... [s/k/e]:          │
│  (timeout → auto-submit; s=submit now,       │
│   k=skip, e=end bot)                         │
└─────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Post-fill review | Manual input blocks forever | 15s countdown, auto-submit | Daemon thread reads stdin |
| Fill quality | No verification | Vision LLM screenshot check | Logs missing fields, warns user |
| Pipeline re-run | Re-processes same top 10 | Skips already-submitted URLs | JSON file, loaded at startup |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `app/automation/submission_handler.py` | 1-30 | Replace `pause_for_human_review()` entirely |
| P0 | `app/workflows/run_pipeline.py` | 174-200 | Integration point — where verification + new gate plug in |
| P0 | `app/workflows/run_pipeline.py` | 212-264 | Pipeline startup — where skip logic must be added |
| P1 | `app/vision/form_analyzer.py` | 1-50 | Vision LLM call pattern to mirror for verification |
| P1 | `app/config.py` | all | Settings object — vision_model field name |
| P2 | `app/utils/logger.py` | all | Loguru pattern |
| P2 | `app/utils/constants.py` | all | RESUMES_DIR pattern for APPLIED_JOBS_FILE path |

---

## Patterns to Mirror

### LOGGING_PATTERN
```python
# SOURCE: app/automation/submission_handler.py:14-17
logger.info("=" * 60)
logger.info(f"  🔍 REVIEW REQUIRED: {job_role} @ {job_company}")
logger.info("  Form is filled. Please review in the browser window.")
logger.info("=" * 60)
```

### VISION_LLM_CALL_PATTERN
```python
# SOURCE: app/vision/form_analyzer.py (analyze_page_screenshot)
# Uses settings.vision_model via openai-compatible client with base64 screenshot
from app.config import settings
client = openai.AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)
response = await client.chat.completions.create(
    model=settings.vision_model,
    messages=[{"role": "user", "content": [...image content...]}],
    max_tokens=512,
)
```

### SCREENSHOT_PATTERN
```python
# SOURCE: app/vision/form_analyzer.py
screenshot_bytes = await page.screenshot(full_page=True)
b64 = base64.b64encode(screenshot_bytes).decode()
```

### ASYNC_TIMEOUT_INPUT_PATTERN
```python
# New pattern — asyncio Future + daemon thread to make blocking stdin non-blocking
import asyncio, sys, threading

async def _timed_stdin(prompt: str, timeout: float) -> str | None:
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[str] = loop.create_future()

    def _reader():
        try:
            line = sys.stdin.readline().strip().lower()
        except Exception:
            line = ""
        if not fut.done():
            loop.call_soon_threadsafe(fut.set_result, line)

    threading.Thread(target=_reader, daemon=True).start()

    for remaining in range(int(timeout), 0, -1):
        if fut.done():
            break
        print(f"\r  {prompt} — auto-submitting in {remaining}s... [s/k/e]: ", end="", flush=True)
        await asyncio.sleep(1)

    if not fut.done():
        fut.set_result("")   # timeout → treat as auto-submit
        print("\n  ⏰ Time's up — auto-submitting")

    return await fut
```

### CONSTANTS_PATH_PATTERN
```python
# SOURCE: app/utils/constants.py
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
# New constant follows same pattern:
APPLIED_JOBS_FILE = DATA_DIR / "applied_jobs.json"
```

### JSON_FILE_PATTERN
```python
# Pattern used for cover letter saving in cover_letter_gen.py (simple file I/O)
import json
from pathlib import Path

def load_applied_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open() as f:
        data = json.load(f)
    return {entry["url"] for entry in data}
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `app/utils/constants.py` | UPDATE | Add `APPLIED_JOBS_FILE` path constant |
| `app/utils/application_tracker.py` | CREATE | Load/save applied job JSON file |
| `app/automation/submission_handler.py` | UPDATE | Replace `pause_for_human_review()` with timed version; add `verify_form_filled()` |
| `app/workflows/run_pipeline.py` | UPDATE | Call verify step; use new timed gate; load+skip applied URLs; record on submit |

## NOT Building
- Database integration (DB isn't wired into run_pipeline.py; JSON file is simpler and sufficient)
- Re-fill attempts for missing fields (verification is warn-only, not blocking)
- Parallel countdown display (single-line overwrite with `\r` is sufficient)
- Celery/apply_pipeline.py changes (interactive pipeline only)

---

## Step-by-Step Tasks

### Task 1: Add APPLIED_JOBS_FILE constant
- **ACTION**: Add one line to `app/utils/constants.py`
- **IMPLEMENT**: Below `RESUMES_DIR = DATA_DIR / "resumes"`, add `APPLIED_JOBS_FILE = DATA_DIR / "applied_jobs.json"`
- **MIRROR**: CONSTANTS_PATH_PATTERN
- **IMPORTS**: None (Path already imported)
- **GOTCHA**: `DATA_DIR` must already exist before file is written — it does (`data/logs/` and `data/resumes/` already exist so `data/` is present)
- **VALIDATE**: `python3 -c "from app.utils.constants import APPLIED_JOBS_FILE; print(APPLIED_JOBS_FILE)"`

### Task 2: Create app/utils/application_tracker.py
- **ACTION**: Create new file with two functions
- **IMPLEMENT**:
```python
"""
application_tracker.py
Persists submitted application URLs to data/applied_jobs.json so the
pipeline skips already-applied jobs on repeated runs.
"""
import json
from datetime import datetime
from pathlib import Path
from app.utils.constants import APPLIED_JOBS_FILE
from app.utils.logger import logger


def load_applied_urls() -> set[str]:
    """Return set of application URLs already submitted."""
    if not APPLIED_JOBS_FILE.exists():
        return set()
    try:
        with APPLIED_JOBS_FILE.open() as f:
            data = json.load(f)
        return {entry["url"] for entry in data}
    except Exception as e:
        logger.warning(f"Could not read applied_jobs.json: {e}")
        return set()


def mark_as_applied(url: str, company: str, role: str) -> None:
    """Append a successfully submitted job to the tracker file."""
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
- **MIRROR**: JSON_FILE_PATTERN, LOGGING_PATTERN
- **IMPORTS**: json, datetime, pathlib.Path, app.utils.constants.APPLIED_JOBS_FILE, app.utils.logger.logger
- **GOTCHA**: Always read existing list before appending — don't overwrite it
- **VALIDATE**: `python3 -c "from app.utils.application_tracker import load_applied_urls, mark_as_applied; mark_as_applied('http://test.com', 'ACME', 'SWE Intern'); print(load_applied_urls())"`

### Task 3: Add verify_form_filled() to submission_handler.py
- **ACTION**: Add new async function before `pause_for_human_review()`
- **IMPLEMENT**:
```python
import base64
import openai
from app.config import settings

async def verify_form_filled(page: Page) -> tuple[bool, list[str]]:
    """
    Takes a full-page screenshot and asks the vision LLM to identify
    any visibly empty required fields.

    Returns (all_filled: bool, issues: list[str])
    """
    try:
        screenshot_bytes = await page.screenshot(full_page=True)
        b64 = base64.b64encode(screenshot_bytes).decode()

        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        response = await client.chat.completions.create(
            model=settings.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a job application form. Examine every visible field. "
                            "List ONLY the required fields (marked with * or 'required') "
                            "that appear empty or unfilled. "
                            "Reply with a JSON object: "
                            '{"all_filled": true/false, "missing": ["Field Name", ...]}'
                            " If all required fields are filled, return all_filled=true and missing=[]."
                        ),
                    },
                ],
            }],
            max_tokens=256,
        )
        raw = response.choices[0].message.content.strip()
        # Extract JSON even if wrapped in markdown
        if "```" in raw:
            raw = raw.split("```")[1].strip().lstrip("json").strip()
        result = json.loads(raw)
        all_filled = result.get("all_filled", True)
        missing = result.get("missing", [])
        return all_filled, missing
    except Exception as e:
        logger.warning(f"Form verification failed: {e}")
        return True, []   # non-blocking fallback
```
- **MIRROR**: VISION_LLM_CALL_PATTERN, SCREENSHOT_PATTERN
- **IMPORTS**: `import base64`, `import json`, `import openai`, `from app.config import settings` — add to top of submission_handler.py
- **GOTCHA**: Vision model may return markdown-wrapped JSON — strip ``` fences before parsing. Return `(True, [])` on any exception so verification is never a hard blocker.
- **VALIDATE**: Function runs without exception; check logs show warning on model error rather than crash.

### Task 4: Replace pause_for_human_review() with timed version
- **ACTION**: Replace the existing `pause_for_human_review()` function body entirely
- **IMPLEMENT**:
```python
import threading
import sys

async def pause_for_human_review(page: Page, job_company: str, job_role: str, timeout: int = 15) -> bool:
    """
    Timed review gate. Shows a countdown and auto-submits on timeout.
    User can type 's' to submit now, 'k' to skip, 'e' to end the bot.

    Returns True to submit, False to skip. Raises KeyboardInterrupt to end.
    """
    logger.info("=" * 60)
    logger.info(f"  REVIEW: {job_role} @ {job_company}")
    logger.info("  [s] submit now  |  [k] skip  |  [e] end bot")
    logger.info("=" * 60)

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[str] = loop.create_future()

    def _reader():
        try:
            line = sys.stdin.readline().strip().lower()
        except Exception:
            line = ""
        if not fut.done():
            loop.call_soon_threadsafe(fut.set_result, line)

    threading.Thread(target=_reader, daemon=True).start()

    for remaining in range(timeout, 0, -1):
        if fut.done():
            break
        print(f"\r  Auto-submitting in {remaining:2d}s... [s/k/e]: ", end="", flush=True)
        await asyncio.sleep(1)

    print()  # newline after countdown

    if not fut.done():
        fut.set_result("")   # timeout → auto-submit

    decision = await fut

    if decision.startswith("e"):
        logger.info("Bot stopped by user")
        raise KeyboardInterrupt
    elif decision.startswith("k"):
        logger.info("Skipped")
        return False
    else:
        # 's', '', or timeout all result in submit
        logger.info("Submitting" if decision else "Auto-submitting (timeout)")
        return True
```
- **MIRROR**: ASYNC_TIMEOUT_INPUT_PATTERN, LOGGING_PATTERN
- **IMPORTS**: `import asyncio`, `import threading`, `import sys` — add to top of submission_handler.py
- **GOTCHA**: `asyncio.get_event_loop()` is fine here since this always runs inside an asyncio context. The daemon thread will be abandoned on timeout — this is intentional; stdin input after timeout is silently discarded.
- **VALIDATE**: Run pipeline on a test job, let the 15s expire — bot should auto-submit. Type 'k' mid-countdown — bot should skip.

### Task 5: Wire verification + tracking into run_pipeline.py
- **ACTION**: Three changes to `run_pipeline.py`
- **IMPLEMENT**:

**5a — Import new modules** (add to imports at top):
```python
from app.automation.submission_handler import (
    pause_for_human_review, click_submit, confirm_submission,
    handle_verification_code, verify_form_filled,
)
from app.utils.application_tracker import load_applied_urls, mark_as_applied
```

**5b — Load applied URLs and filter at pipeline startup** (in `run_full_pipeline()`, after scoring, before processing):
```python
# Load already-applied URLs and filter out duplicates
applied_urls = load_applied_urls()
if applied_urls and SKIP_ALREADY_APPLIED:
    before = len(qualified)
    qualified = [j for j in qualified if j["application_url"] not in applied_urls]
    logger.info(f"Skipped {before - len(qualified)} already-applied jobs")
```
Place this block right after `logger.info(f"Qualified (above threshold): {len(qualified)}")`.

**5c — Call verify_form_filled() and mark_as_applied() in process_job()**:

After the Greenhouse-specific fill block and before the review gate, insert:
```python
# Verify fill quality via vision LLM
logger.info("Verifying form fill via vision LLM...")
all_filled, missing = await verify_form_filled(page)
if all_filled:
    logger.info("✅ All required fields appear filled")
else:
    logger.warning(f"⚠️  Potentially missing fields: {missing}")
```

After `confirmed = await confirm_submission(page)` and before `status = "submitted"...`, insert:
```python
if confirmed:
    mark_as_applied(job.application_url, job.company, job.role)
```

- **MIRROR**: LOGGING_PATTERN
- **IMPORTS**: Already covered in 5a
- **GOTCHA**: `verify_form_filled()` must be called BEFORE `pause_for_human_review()` so the user sees the verification result during their review window. `mark_as_applied()` must only be called when `confirmed=True`, not on `submit_attempted`.
- **VALIDATE**: Run pipeline; check `data/applied_jobs.json` exists and has entries after a submit. Re-run — same jobs should be skipped.

---

## Testing Strategy

### Manual Validation Steps
- [ ] Run pipeline to a form, let 15s expire — browser submits automatically
- [ ] Run pipeline, type 'k' during countdown — job is skipped
- [ ] Run pipeline, type 'e' during countdown — bot stops cleanly
- [ ] Run pipeline, type 's' at second 8 — submits immediately
- [ ] After a submission, check `data/applied_jobs.json` has the entry
- [ ] Re-run pipeline — same job URL is filtered out before processing
- [ ] Vision verification log appears after fill ("✅ All required fields" or warning list)

### Edge Cases Checklist
- [ ] `applied_jobs.json` doesn't exist yet (first run) — `load_applied_urls()` returns empty set
- [ ] `applied_jobs.json` is malformed JSON — `load_applied_urls()` logs warning, returns empty set
- [ ] Vision LLM API errors — `verify_form_filled()` returns `(True, [])`, pipeline continues
- [ ] User types garbage (not s/k/e) during countdown — treated as submit (safe default)
- [ ] Pipeline ends mid-countdown via Ctrl+C — `KeyboardInterrupt` propagates normally
- [ ] `confirm_submission()` returns False — `mark_as_applied()` not called, URL stays un-tracked

---

## Validation Commands

### Static Analysis
```bash
cd /Users/devonlopez07/Documents/Code/auto_apply_bot
PYTHONPATH=. python3 -c "
from app.utils.application_tracker import load_applied_urls, mark_as_applied
from app.automation.submission_handler import verify_form_filled, pause_for_human_review
from app.utils.constants import APPLIED_JOBS_FILE
print('All imports OK')
print('APPLIED_JOBS_FILE:', APPLIED_JOBS_FILE)
"
```
EXPECT: "All imports OK" with path printed, no ImportError

### Tracker Unit Test
```bash
cd /Users/devonlopez07/Documents/Code/auto_apply_bot
PYTHONPATH=. python3 -c "
import json, os
from app.utils.application_tracker import load_applied_urls, mark_as_applied
from app.utils.constants import APPLIED_JOBS_FILE

# Clean state
if APPLIED_JOBS_FILE.exists():
    APPLIED_JOBS_FILE.unlink()

assert load_applied_urls() == set(), 'Should be empty set on missing file'
mark_as_applied('https://jobs.greenhouse.io/test/123', 'ACME', 'SWE Intern')
mark_as_applied('https://jobs.greenhouse.io/test/456', 'Beta Corp', 'Quant Intern')
urls = load_applied_urls()
assert 'https://jobs.greenhouse.io/test/123' in urls
assert 'https://jobs.greenhouse.io/test/456' in urls
assert len(urls) == 2
print('Tracker tests passed')
"
```
EXPECT: "Tracker tests passed"

### Full Pipeline Smoke Test
```bash
cd /Users/devonlopez07/Documents/Code/auto_apply_bot
PYTHONPATH=. python3 app/workflows/run_pipeline.py
```
EXPECT: Pipeline starts, shows "Skipped X already-applied jobs" on re-run, vision verification logs appear after fill, 15s countdown visible before submission.

---

## Acceptance Criteria
- [ ] After fill, vision LLM scans form and logs missing required fields (or confirms all filled)
- [ ] Review prompt shows 15-second countdown with `[s/k/e]` options
- [ ] Timeout auto-submits without user input
- [ ] `s` key submits immediately; `k` skips; `e` ends the bot
- [ ] On confirmed submission, URL written to `data/applied_jobs.json`
- [ ] On pipeline restart, already-applied URLs are filtered before processing
- [ ] `SKIP_ALREADY_APPLIED = False` bypasses the filter (existing flag honored)
- [ ] All error paths (bad JSON file, vision API error) are non-fatal

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| stdin readline blocks after timeout | Medium | Thread leaks | Thread is daemon=True — exits with process |
| Vision model returns non-JSON | Medium | Verification skipped | Strip markdown fences + return `(True, [])` fallback |
| confirmed=False on real submission | Low | URL not tracked, re-applied next run | Add manual note in summary to check browser |
| applied_jobs.json write fails (disk full) | Low | Dedup lost | Log warning; next run may re-apply to same job |

## Notes
- The `SKIP_ALREADY_APPLIED = True` flag in `run_pipeline.py:81` exists but was never wired to actual logic — this plan wires it.
- Verification is warn-only intentionally: the LLM may hallucinate missing fields on partial screenshots. The user sees the warning during the countdown and can override.
- The timed gate replaces the old gate completely — there's no backward-compatible flag needed since this is an improvement, not a breaking change.
