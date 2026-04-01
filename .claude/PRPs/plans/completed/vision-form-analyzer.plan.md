# Plan: Vision Form Analyzer

## Summary
Add a vision-model-powered form analysis step that screenshots every section of a job application, probes each dropdown to capture its actual options, and produces a `FormManifest` — a structured map of every field on the page. The adaptive filler consumes this manifest instead of doing a blind DOM scan, enabling fully automatic form filling on any ATS without `COMPANY_CONFIG` entries.

## User Story
As Devon (the job applicant), I want the bot to visually read any application form and record every field and its available options so that the autofiller can complete the form correctly the first time — without me needing to pre-configure dropdowns per company.

## Problem → Solution
**Current state:** `adaptive_filler.py` DOM-scans for fields but cannot see dropdown options that are lazy-loaded (React Select, Workday, Lever). The second-pass `form_filler.py` uses hardcoded Greenhouse selectors from `COMPANY_CONFIG`, requiring manual discovery per company.

**Desired state:** A vision step runs first, clicks every dropdown open, screenshots the option list, and asks a vision LLM to transcribe it — producing a `FormManifest` with every label, type, and available choices. `adaptive_fill` consumes this manifest so the LLM filling plan can pick exact option strings, not guesses.

## Metadata
- **Complexity**: Medium
- **Source PRD**: N/A
- **PRD Phase**: N/A
- **Estimated Files**: 5 new/modified

---

## UX Design

### Before
```
┌──────────────────────────────────────────────────────┐
│ Pipeline                                              │
│  1. Scrape jobs                                       │
│  2. Score + filter                                    │
│  3. Generate resume + cover letter                    │
│  4. Open form                                         │
│  5. adaptive_fill (DOM scan only)        ← misses     │
│     • React Select options invisible                  │
│     • Lazy dropdowns not expanded                     │
│  6. fill_greenhouse_application          ← hardcoded  │
│     • Requires COMPANY_CONFIG per company             │
│     • Only works on Greenhouse                        │
│  7. Human review gate                                 │
│  8. Submit                                            │
│                                                       │
│  Result: 60-70% fill rate, manually configured        │
└──────────────────────────────────────────────────────┘
```

### After
```
┌──────────────────────────────────────────────────────┐
│ Pipeline                                              │
│  1. Scrape jobs                                       │
│  2. Score + filter                                    │
│  3. Generate resume + cover letter                    │
│  4. Open form                                         │
│  5. analyze_form_with_vision()           ← NEW        │
│     • Full-page screenshot                            │
│     • Click each dropdown → screenshot options        │
│     • Vision LLM → FormManifest (all fields + opts)  │
│  6. adaptive_fill(manifest=manifest)     ← updated    │
│     • Merges manifest + DOM scan                      │
│     • LLM picks from ACTUAL option strings            │
│     • Works on any ATS automatically                  │
│  7. Human review gate                                 │
│  8. Submit                                            │
│                                                       │
│  Result: 85-95% fill rate, zero company config        │
└──────────────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| New company | Add entry to `COMPANY_CONFIG` | Nothing — works automatically | No manual discovery |
| Dropdown filling | Guesses option text from candidate data | Picks from real option list | Exact match, no failures |
| React Select | Second pass with `fill_greenhouse_application` | Vision manifest covers it | Single pass, any ATS |
| Pipeline logs | "Adaptive fill complete" | "Vision analysis: 14 fields found, 6 dropdowns probed" | Better observability |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `app/automation/adaptive_filler.py` | 1-430 | This is what we're augmenting — understand scan + fill flow |
| P0 | `app/workflows/run_pipeline.py` | 83-198 | `process_job()` is where the new step plugs in |
| P0 | `app/config.py` | 1-37 | Settings pattern — how to add `vision_model` |
| P1 | `app/utils/validators.py` | 1-52 | Pydantic model pattern — `FormField`/`FormManifest` go here |
| P1 | `app/automation/playwright_engine.py` | 1-52 | `random_delay`, `launch_browser` — Playwright patterns |
| P2 | `app/llm/cover_letter_gen.py` | 1-42 | OpenAI client instantiation pattern — mirror exactly |
| P2 | `app/automation/form_filler.py` | 120-180 | `select_react_dropdown()` — shows how to interact with React Select |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Groq vision models | Groq docs | `meta-llama/llama-4-scout-17b-16e-instruct` supports image_url input via OpenAI-compatible API |
| OpenAI vision format | OpenAI API docs | Content must be `[{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]` |
| Playwright screenshot | Playwright Python docs | `await page.screenshot(full_page=True)` returns `bytes`; clip to viewport with `clip={"x":0,"y":0,"width":1280,"height":800}` |

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: app/automation/adaptive_filler.py:33, app/llm/cover_letter_gen.py:1
# Files: snake_case. Classes: PascalCase. Functions: snake_case. Async functions same.
async def scan_form_fields(page: Page) -> list[dict]:   # async function
def get_filling_plan(...) -> list[dict]:                 # sync function
class FormManifest(BaseModel):                           # Pydantic model
```

### OPENAI_CLIENT_PATTERN
```python
# SOURCE: app/automation/adaptive_filler.py:25-28, app/llm/cover_letter_gen.py:8-11
# Always instantiate at module level using settings. Use OpenAI (sync) for non-async calls.
from openai import OpenAI
from app.config import settings

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)
```

### ERROR_HANDLING
```python
# SOURCE: app/automation/adaptive_filler.py:252-268, app/automation/adaptive_filler.py:370-375
# Wrap LLM calls in try/except, log with logger.error, return safe fallback.
# Per-field failures use logger.warning and increment "failed" counter — never crash the loop.
try:
    response = client.chat.completions.create(...)
    ...
except Exception as e:
    logger.error(f"LLM filling plan failed: {e}")
    return []

# Per-action failures:
except Exception as e:
    logger.warning(f"Action failed for '{label}': {e}")
    results["failed"] += 1
```

### LOGGING_PATTERN
```python
# SOURCE: app/automation/adaptive_filler.py:169, 377, 399, 419
# Use loguru logger imported from app.utils.logger.
# info = milestone, warning = degraded but ok, error = operation failed, debug = per-field detail
from app.utils.logger import logger

logger.info(f"DOM scan found {len(fields)} form fields")
logger.warning("No form fields detected — page may not have loaded fully")
logger.error(f"Vision analysis failed: {e}")
logger.debug(f"Probing dropdown: {label}")
```

### PLAYWRIGHT_ASYNC_PATTERN
```python
# SOURCE: app/automation/adaptive_filler.py:33-170, app/automation/playwright_engine.py:22-32
# All page interaction is async. Always await random_delay after actions to appear human.
from app.automation.playwright_engine import random_delay

async def probe_dropdown_options(page: Page, selector: str) -> list[str]:
    el = await page.query_selector(selector)
    if el:
        await el.click()
        await random_delay(0.5, 1.0)   # wait for options to render
        screenshot = await page.screenshot(...)
        await page.keyboard.press("Escape")
        await random_delay(0.2, 0.4)
```

### PYDANTIC_MODEL_PATTERN
```python
# SOURCE: app/utils/validators.py:5-33
# All models inherit BaseModel, use Optional for nullable fields, list[str] for arrays.
from pydantic import BaseModel
from typing import Optional

class FormField(BaseModel):
    label: str
    field_type: str
    required: bool = False
    options: list[str] = []
    placeholder: str = ""
    selector_hint: str = ""

class FormManifest(BaseModel):
    url: str
    fields: list[FormField]
    analyzed_at: str
```

### SETTINGS_PATTERN
```python
# SOURCE: app/config.py:1-37
# Add new settings as typed fields on the Settings class with defaults.
class Settings(BaseSettings):
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # ^ Groq's vision-capable model. Same API key + base_url as openai_model.
```

### VISION_API_CALL_PATTERN
```python
# Groq vision (OpenAI-compatible). Image must be base64-encoded PNG passed as data URL.
import base64

screenshot_bytes = await page.screenshot(full_page=False)
b64 = base64.b64encode(screenshot_bytes).decode()

response = client.chat.completions.create(
    model=settings.vision_model,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ],
    }],
    temperature=0.1,
)
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `app/vision/__init__.py` | CREATE | New package marker |
| `app/vision/form_analyzer.py` | CREATE | Core vision analysis module — screenshots + dropdown probing + vision LLM |
| `app/utils/validators.py` | UPDATE | Add `FormField` and `FormManifest` Pydantic models |
| `app/config.py` | UPDATE | Add `vision_model` setting |
| `app/automation/adaptive_filler.py` | UPDATE | Accept optional `FormManifest`, merge with DOM scan in `adaptive_fill()` |
| `app/workflows/run_pipeline.py` | UPDATE | Call `analyze_form_with_vision()` before `adaptive_fill()`, pass manifest |

## NOT Building
- Multi-page form navigation (scrolling between form pages/tabs — page 1 → page 2)
- CAPTCHA detection or solving
- Replacing the human approval gate
- Changes to scraper, outreach pipeline, or cover letter generation
- Saving the manifest to disk or database for replay
- Changes to `form_filler.py` (Greenhouse-specific pass stays as fallback for now)

---

## Step-by-Step Tasks

### Task 1: Add FormField and FormManifest models to validators.py
- **ACTION**: Append two new Pydantic models at the end of `app/utils/validators.py`
- **IMPLEMENT**:
```python
class FormField(BaseModel):
    label: str
    field_type: str  # "text" | "textarea" | "select" | "react_select" | "checkbox" | "radio" | "file"
    required: bool = False
    options: list[str] = []          # Available choices for select/radio
    placeholder: str = ""
    selector_hint: str = ""          # Best CSS selector guess from DOM
    section: str = ""                # Form section heading if detectable

class FormManifest(BaseModel):
    url: str
    fields: list[FormField]
    analyzed_at: str                 # ISO datetime string
```
- **MIRROR**: PYDANTIC_MODEL_PATTERN
- **IMPORTS**: `from pydantic import BaseModel` (already imported), `from typing import Optional` (already imported)
- **GOTCHA**: Do NOT change existing models — only append. The existing `CandidateProfile`, `JobPosting`, `ApplicationResult` must remain identical.
- **VALIDATE**: `python3 -c "from app.utils.validators import FormField, FormManifest; print('ok')"`

---

### Task 2: Add vision_model to config.py
- **ACTION**: Add one field to the `Settings` class in `app/config.py`
- **IMPLEMENT**: Insert after line 12 (`openai_model` field):
```python
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
```
- **MIRROR**: SETTINGS_PATTERN
- **GOTCHA**: This model uses the same `openai_api_key` and `openai_base_url` as the text model — no new credentials needed. The lru_cache on `get_settings()` means this is read once; no config reload needed.
- **VALIDATE**: `python3 -c "from app.config import settings; print(settings.vision_model)"`

---

### Task 3: Create app/vision/__init__.py
- **ACTION**: Create an empty package marker
- **IMPLEMENT**: Empty file (just a newline)
- **MIRROR**: Matches `app/automation/__init__.py`, `app/llm/__init__.py` pattern
- **VALIDATE**: `python3 -c "import app.vision; print('ok')"`

---

### Task 4: Create app/vision/form_analyzer.py
- **ACTION**: Create the core vision analysis module with three functions: `probe_dropdown_options`, `analyze_page_screenshot`, and `analyze_form_with_vision`
- **IMPLEMENT**:

```python
"""
form_analyzer.py

Vision-powered form analysis. Produces a FormManifest — a structured map
of every visible field on the page — by combining:
  1. Full-page screenshots sent to a vision LLM to discover fields
  2. Per-dropdown probing: click open → screenshot options → close
     This captures lazy-loaded React Select options the DOM scan misses.

The FormManifest feeds into adaptive_filler.adaptive_fill() so the LLM
filling plan can reference ACTUAL option strings, not guesses.
"""
import base64
import json
from datetime import datetime
from playwright.async_api import Page
from openai import OpenAI
from app.config import settings
from app.utils.validators import FormField, FormManifest
from app.automation.playwright_engine import random_delay
from app.utils.logger import logger

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


# ─── Dropdown Prober ──────────────────────────────────────────────────────────

async def probe_dropdown_options(page: Page, label: str, trigger_selector: str) -> list[str]:
    """
    Click a dropdown open, screenshot the option list, ask vision LLM to
    transcribe the options, then close the dropdown.

    Returns: list of option strings (empty list if probing fails).
    """
    try:
        el = await page.query_selector(trigger_selector)
        if not el or not await el.is_visible():
            return []

        await el.click()
        await random_delay(0.5, 1.0)  # let options render

        # Screenshot just the visible viewport (options appear in viewport)
        screenshot_bytes = await page.screenshot(full_page=False)
        b64 = base64.b64encode(screenshot_bytes).decode()

        prompt = (
            f"This is a screenshot of a job application form. "
            f"A dropdown labeled '{label}' has been clicked open. "
            f"List EVERY option visible in the dropdown menu as a JSON array of strings. "
            f"Include only the option text, no explanations. "
            f"Return ONLY valid JSON like: [\"Option 1\", \"Option 2\"]"
        )

        response = client.chat.completions.create(
            model=settings.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        options = json.loads(raw.strip())
        logger.debug(f"Probed '{label}': {len(options)} options found")
        return options if isinstance(options, list) else []

    except Exception as e:
        logger.warning(f"Dropdown probe failed for '{label}': {e}")
        return []
    finally:
        # Always close the dropdown
        try:
            await page.keyboard.press("Escape")
            await random_delay(0.2, 0.4)
        except Exception:
            pass


# ─── Page Screenshot Analyzer ─────────────────────────────────────────────────

def analyze_page_screenshot(screenshot_bytes: bytes, scroll_position: int = 0) -> list[dict]:
    """
    Send a viewport screenshot to the vision LLM and get back a list of
    raw field descriptors (label, type, options visible, required, placeholder).

    Returns: list of raw dicts (not yet deduplicated or merged).
    """
    b64 = base64.b64encode(screenshot_bytes).decode()

    prompt = (
        "This is a screenshot of a job application form. "
        "Identify EVERY form field visible in this section. "
        "For each field return a JSON object with: "
        "  label (string — the field's label text), "
        "  field_type (one of: text, textarea, select, react_select, checkbox, radio, file), "
        "  required (true/false — look for asterisk or 'required' text), "
        "  options (array of visible option strings for select/radio, else []), "
        "  placeholder (placeholder text if visible, else ''). "
        "Ignore decorative elements, headers, and buttons. "
        "Return ONLY a valid JSON array, no markdown:\n"
        "[{\"label\": \"First Name\", \"field_type\": \"text\", \"required\": true, \"options\": [], \"placeholder\": \"\"}, ...]"
    )

    try:
        response = client.chat.completions.create(
            model=settings.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        fields = json.loads(raw.strip())
        logger.debug(f"Vision found {len(fields)} fields at scroll position {scroll_position}px")
        return fields if isinstance(fields, list) else []
    except Exception as e:
        logger.error(f"Vision screenshot analysis failed: {e}")
        return []


# ─── Master Analyzer ──────────────────────────────────────────────────────────

async def analyze_form_with_vision(page: Page, url: str) -> FormManifest:
    """
    Full vision analysis of an application form page.

    Steps:
      1. Scroll through the form taking viewport screenshots at each position
      2. Ask vision LLM to describe all fields in each screenshot
      3. Deduplicate fields across screenshots
      4. Probe each select/react_select dropdown to capture actual options
      5. Return a FormManifest with complete, accurate field descriptions

    This runs BEFORE adaptive_fill() so the filling plan has exact option
    strings instead of guessing from field labels alone.
    """
    logger.info("Starting vision form analysis...")
    raw_fields: list[dict] = []

    # Step 1: Scroll through the form, screenshot each viewport section
    viewport_height = 800  # matches playwright_engine.py viewport
    page_height = await page.evaluate("() => document.body.scrollHeight")
    scroll_positions = list(range(0, int(page_height), viewport_height))
    if not scroll_positions:
        scroll_positions = [0]

    logger.info(f"Page height: {page_height}px — taking {len(scroll_positions)} screenshots")

    for scroll_y in scroll_positions:
        await page.evaluate(f"window.scrollTo(0, {scroll_y})")
        await random_delay(0.4, 0.7)
        screenshot_bytes = await page.screenshot(full_page=False)
        section_fields = analyze_page_screenshot(screenshot_bytes, scroll_y)
        raw_fields.extend(section_fields)

    # Scroll back to top for dropdown probing
    await page.evaluate("window.scrollTo(0, 0)")
    await random_delay(0.3, 0.5)

    # Step 2: Deduplicate fields by label (keep first occurrence)
    seen_labels: set[str] = set()
    unique_fields: list[dict] = []
    for f in raw_fields:
        label = (f.get("label") or "").strip().lower()
        if label and label not in seen_labels:
            seen_labels.add(label)
            unique_fields.append(f)

    logger.info(f"Vision analysis: {len(unique_fields)} unique fields after dedup")

    # Step 3: Probe dropdowns to get actual option lists
    # Find all select/react_select elements in the DOM to get their selectors
    dropdown_selectors = await page.evaluate("""
    () => {
        const results = [];

        // Native selects
        document.querySelectorAll('select').forEach(el => {
            if (el.getBoundingClientRect().width > 0) {
                results.push({
                    selector: el.id ? `#${el.id}` : `select[name="${el.name}"]`,
                    kind: 'select',
                    label: (() => {
                        if (el.id) {
                            const lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl) return lbl.innerText.trim().replace(/[*]/g, '').trim();
                        }
                        return el.name || '';
                    })(),
                });
            }
        });

        // React Select controls
        document.querySelectorAll('[class*="select__control"], .select__control').forEach(el => {
            if (el.getBoundingClientRect().width > 0) {
                const container = el.closest('[class*="select"], .select');
                const labelEl = container
                    ? container.querySelector('label, .select__label, [class*="label"]')
                    : null;
                const label = labelEl ? labelEl.innerText.trim().replace(/[*]/g, '').trim() : '';
                if (label) {
                    results.push({ selector: null, kind: 'react_select', label, el_ref: true });
                }
            }
        });

        return results;
    }
    """)

    # Probe each dropdown
    for dd in dropdown_selectors:
        label = dd.get("label", "")
        kind = dd.get("kind", "select")
        selector = dd.get("selector", "")

        if not label:
            continue

        if kind == "react_select":
            # Use label to find the React Select control
            trigger_sel = f'label:has-text("{label[:30]}") ~ div [class*="select__control"], label:has-text("{label[:30]}") + div [class*="select__control"]'
        else:
            trigger_sel = selector

        if not trigger_sel:
            continue

        options = await probe_dropdown_options(page, label, trigger_sel)

        # Merge options into matching unique_field
        for uf in unique_fields:
            if uf.get("label", "").strip().lower() == label.strip().lower():
                if options:
                    uf["options"] = options
                break

    # Step 4: Build FormManifest
    manifest_fields = []
    for uf in unique_fields:
        manifest_fields.append(FormField(
            label=uf.get("label", "").strip(),
            field_type=uf.get("field_type", "text"),
            required=bool(uf.get("required", False)),
            options=uf.get("options", []),
            placeholder=uf.get("placeholder", ""),
            selector_hint=uf.get("selector", "") or "",
            section=uf.get("section", ""),
        ))

    manifest = FormManifest(
        url=url,
        fields=manifest_fields,
        analyzed_at=datetime.utcnow().isoformat(),
    )

    logger.info(
        f"Vision manifest complete: {len(manifest.fields)} fields, "
        f"{sum(1 for f in manifest.fields if f.options)} with options"
    )
    return manifest
```

- **MIRROR**: OPENAI_CLIENT_PATTERN, ERROR_HANDLING, LOGGING_PATTERN, PLAYWRIGHT_ASYNC_PATTERN, VISION_API_CALL_PATTERN
- **IMPORTS**: `base64`, `json`, `datetime`, `Page`, `OpenAI`, `settings`, `FormField`, `FormManifest`, `random_delay`, `logger`
- **GOTCHA 1**: Groq vision requires `base_url` to stay as `https://api.groq.com/openai/v1` — same client works.
- **GOTCHA 2**: `probe_dropdown_options` uses a `finally` block to always press Escape — without this, an open dropdown blocks subsequent clicks.
- **GOTCHA 3**: `page.evaluate("window.scrollTo(...)")` is not async-awaitable in all Playwright versions — use `await page.evaluate(...)` (evaluate IS async).
- **GOTCHA 4**: React Select trigger selector uses CSS sibling combinators (`~`, `+`) — if these fail, fallback to `page.get_by_label(label).locator('..')`.
- **VALIDATE**: `python3 -c "from app.vision.form_analyzer import analyze_form_with_vision; print('ok')"`

---

### Task 5: Update adaptive_filler.py to accept FormManifest
- **ACTION**: Modify `adaptive_fill()` signature to accept optional `manifest: FormManifest | None = None`. When provided, merge manifest fields with DOM-scanned fields before calling `get_filling_plan()`. Update `get_filling_plan()` to use enriched option data from the manifest.
- **IMPLEMENT**:

In `adaptive_filler.py`, add at top of imports:
```python
from app.utils.validators import CandidateProfile, JobPosting, FormManifest
```
(replace the existing `from app.utils.validators import CandidateProfile, JobPosting` line)

Add a new function after `scan_form_fields()`:
```python
def merge_manifest_with_dom(dom_fields: list[dict], manifest: FormManifest) -> list[dict]:
    """
    Enrich DOM-scanned fields with vision manifest data.
    The manifest may have fields the DOM scan missed (shadow DOM, custom components).
    For fields found in both, the manifest's option list takes precedence.
    """
    # Index manifest fields by lowercase label
    manifest_index = {f.label.strip().lower(): f for f in manifest.fields}

    merged = []
    dom_labels_seen = set()

    for dom_field in dom_fields:
        label = (dom_field.get("label") or "").strip().lower()
        dom_labels_seen.add(label)
        if label in manifest_index:
            mf = manifest_index[label]
            # Manifest options override DOM (DOM can't see lazy-loaded options)
            if mf.options:
                dom_field = {**dom_field, "options": mf.options}
            if mf.required:
                dom_field = {**dom_field, "required": True}
        merged.append(dom_field)

    # Add manifest fields not found in DOM scan at all
    for mf in manifest.fields:
        if mf.label.strip().lower() not in dom_labels_seen:
            merged.append({
                "type": mf.field_type,
                "label": mf.label,
                "selector": mf.selector_hint or None,
                "options": mf.options,
                "placeholder": mf.placeholder,
                "required": mf.required,
            })

    logger.info(f"Merged: {len(dom_fields)} DOM fields + {len(manifest.fields)} manifest fields → {len(merged)} total")
    return merged
```

Modify `adaptive_fill()` signature and body:
```python
async def adaptive_fill(
    page: Page,
    candidate: CandidateProfile,
    job: JobPosting,
    resume_path: str,
    cover_letter: str = "",
    cover_letter_path: str = "",
    why_interested: str = "",
    manifest: FormManifest | None = None,    # ← NEW parameter
):
    logger.info("Starting adaptive form fill...")

    await random_delay(1.0, 1.5)
    fields = await scan_form_fields(page)

    if not fields:
        logger.warning("No form fields detected — page may not have loaded fully")
        return

    # Enrich with vision manifest when available
    if manifest:
        fields = merge_manifest_with_dom(fields, manifest)

    plan = get_filling_plan(
        fields=fields,
        candidate=candidate,
        job=job,
        cover_letter=cover_letter,
        why_interested=why_interested,
    )

    if not plan:
        logger.warning("LLM returned empty filling plan")
        return

    await execute_filling_plan(
        page=page,
        plan=plan,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )

    logger.info("Adaptive fill complete ✅")
```

- **MIRROR**: NAMING_CONVENTION, LOGGING_PATTERN, ERROR_HANDLING
- **IMPORTS**: Add `FormManifest` to existing validators import
- **GOTCHA**: `FormManifest | None` union syntax requires Python 3.10+. If the project runs on 3.9, use `Optional[FormManifest]` and add `from typing import Optional`. Check with `python3 --version`. (The existing code uses `list[dict]` without `List` from typing, indicating Python 3.9+ — but `X | None` needs 3.10+.)
- **VALIDATE**: `python3 -c "from app.automation.adaptive_filler import adaptive_fill; print('ok')"`

---

### Task 6: Update run_pipeline.py to call vision analysis
- **ACTION**: In `process_job()`, add vision analysis step between "open form" and "adaptive_fill". Import `analyze_form_with_vision` and pass its manifest to `adaptive_fill`.
- **IMPLEMENT**:

Add to imports section at top of `run_pipeline.py`:
```python
from app.vision.form_analyzer import analyze_form_with_vision
```

Inside `process_job()`, after `await random_delay(2.0, 3.0)` and before the adaptive_fill call, insert:
```python
            # Vision analysis — discovers all fields + probes dropdown options
            logger.info("Running vision form analysis...")
            try:
                manifest = await analyze_form_with_vision(page, job.application_url)
            except Exception as e:
                logger.warning(f"Vision analysis failed, proceeding without manifest: {e}")
                manifest = None
```

Then update the `adaptive_fill` call to pass `manifest=manifest`:
```python
            await adaptive_fill(
                page=page,
                candidate=candidate_for_job,
                job=job,
                resume_path=candidate_for_job.resume_path,
                cover_letter=cover_letter,
                cover_letter_path=cover_letter_path,
                why_interested=why,
                manifest=manifest,    # ← NEW
            )
```

- **MIRROR**: ERROR_HANDLING (vision failure degrades gracefully — pipeline continues without manifest), LOGGING_PATTERN
- **GOTCHA**: The vision step runs with the browser open after `page.goto()` — the form must be loaded before screenshotting. The existing `random_delay(2.0, 3.0)` before this point handles that.
- **GOTCHA**: Do NOT remove `COMPANY_CONFIG` or the Greenhouse second-pass — those stay as fallbacks. Only add the vision step.
- **VALIDATE**: Run `python3 -c "from app.workflows.run_pipeline import process_job; print('ok')"` then test manually on one job.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `analyze_page_screenshot` with blank image | White 1280x800 PNG | Empty list `[]` | Yes — empty form |
| `probe_dropdown_options` when dropdown not found | Selector that matches nothing | `[]` | Yes |
| `merge_manifest_with_dom` with overlapping labels | DOM has "Gender" (no options), manifest has "Gender" (["Male","Female"]) | Merged field has options from manifest | Core case |
| `merge_manifest_with_dom` with manifest-only fields | Manifest has "Work Authorization" not in DOM | Field appears in merged output | Yes — DOM miss |
| `FormManifest` validation | Missing `url` field | Pydantic ValidationError | Edge |

### Edge Cases Checklist
- [ ] Page with zero form fields (scraped wrong URL)
- [ ] Page with 30+ fields (long Workday form)
- [ ] Dropdown with 50+ options (state/country selectors)
- [ ] React Select where label is not adjacent to control
- [ ] Vision LLM returns non-JSON response (markdown wrapper)
- [ ] Vision LLM API rate limit / timeout
- [ ] Dropdown that re-opens after Escape (some custom components)

---

## Validation Commands

### Static Analysis
```bash
cd /Users/devonlopez07/Documents/Code/auto_apply_bot
python3 -m py_compile app/vision/__init__.py app/vision/form_analyzer.py
python3 -m py_compile app/utils/validators.py app/config.py
python3 -m py_compile app/automation/adaptive_filler.py app/workflows/run_pipeline.py
```
EXPECT: No output (zero compile errors)

### Import Check
```bash
PYTHONPATH=. python3 -c "
from app.vision.form_analyzer import analyze_form_with_vision, probe_dropdown_options
from app.utils.validators import FormField, FormManifest
from app.automation.adaptive_filler import adaptive_fill, merge_manifest_with_dom
from app.config import settings
print('vision_model:', settings.vision_model)
print('All imports OK')
"
```
EXPECT: Prints `vision_model: meta-llama/llama-4-scout-17b-16e-instruct` and `All imports OK`

### Live Form Test (Manual)
```bash
PYTHONPATH=. python3 - <<'EOF'
import asyncio
from app.automation.playwright_engine import launch_browser, close_browser
from app.vision.form_analyzer import analyze_form_with_vision

async def test():
    pw, browser, ctx, page = await launch_browser(headless=False)
    await page.goto("https://boards.greenhouse.io/cloudflare/jobs/6137151")
    import asyncio; await asyncio.sleep(3)
    manifest = await analyze_form_with_vision(page, page.url)
    print(f"Fields found: {len(manifest.fields)}")
    for f in manifest.fields:
        print(f"  [{f.field_type}] {f.label} | options: {f.options[:3]}")
    await close_browser(pw, browser)

asyncio.run(test())
EOF
```
EXPECT: Prints 10+ fields, dropdowns show actual option lists

### Full Pipeline Test (Manual)
```bash
PYTHONPATH=. python3 app/workflows/run_pipeline.py
```
EXPECT: Pipeline log shows "Running vision form analysis..." before "Running adaptive form fill..."

---

## Acceptance Criteria
- [ ] `analyze_form_with_vision()` returns a `FormManifest` with at least the same fields as the DOM scan
- [ ] Dropdown fields in the manifest have `options` populated from actual page content (not empty)
- [ ] `adaptive_fill()` accepts `manifest` parameter and uses it without breaking existing behavior when `manifest=None`
- [ ] Pipeline runs end-to-end on a Greenhouse form without errors
- [ ] Vision analysis failure degrades gracefully (pipeline continues, logs warning)
- [ ] No `COMPANY_CONFIG` entries needed for a new company to get dropdown options filled

## Completion Checklist
- [ ] All 6 tasks completed in order
- [ ] `finally: Escape` block present in `probe_dropdown_options` to prevent stuck dropdowns
- [ ] Vision LLM calls use `temperature=0.1` (deterministic)
- [ ] All new functions follow snake_case naming
- [ ] OpenAI client instantiated at module level (not inside functions)
- [ ] `merge_manifest_with_dom` logs merged count
- [ ] `COMPANY_CONFIG` and Greenhouse second-pass left untouched

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Groq vision model doesn't support `data:image/png;base64` format | Low | High | Fallback: use `openai` package directly with GPT-4o-mini vision (same code, different model/key) |
| React Select trigger selector fails on some forms | Medium | Medium | `probe_dropdown_options` returns `[]` — field gets filled from candidate data anyway |
| Vision LLM returns malformed JSON | Medium | Low | `json.loads` in try/except returns `[]` — DOM scan still runs as baseline |
| Page scroll changes form state (SPA routing) | Low | High | Take screenshots without navigation; use `window.scrollTo` not Playwright scroll |
| Rate limiting on Groq vision tier | Medium | Medium | Vision probes one dropdown at a time with `random_delay` between calls |

## Notes
- The `OpenAI` (sync) client is used in `form_analyzer.py` following the same pattern as `adaptive_filler.py` — not `AsyncOpenAI`. This is intentional: the LLM call is blocking but fast, and the existing codebase uses sync OpenAI everywhere in the non-pipeline path.
- `settings.vision_model` can be overridden in `.env` as `VISION_MODEL=gpt-4o-mini` if switching to OpenAI's API (just change `openai_base_url` to `https://api.openai.com/v1` and provide an OpenAI key).
- The Greenhouse second-pass in `run_pipeline.py` is kept intentionally — it handles React Select with hardcoded label matching which may be faster/more reliable than the vision approach for known forms.
