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

_SKIP_PROBE_LABELS = {
    "country", "phone country code", "country code", "country/region", "phone",
}
_MAX_OPTIONS = 20  # cap per-field to avoid LLM token bloat


async def probe_dropdown_options(page: Page, label: str, trigger_selector: str | None) -> list[str]:
    """
    Click a dropdown open, read the option list from the DOM, then close.

    For React Select dropdowns, trigger_selector may be None — in that case a
    JS DOM walk finds the control nearest to the label text and clicks it.

    Skips country/phone-code fields (195 options would blow token limits).
    Caps options at _MAX_OPTIONS to keep manifests compact.

    Returns: list of option strings (empty list if probing fails or skipped).
    """
    # Skip country/phone-code pickers — irrelevant and too many options
    if label.strip().lower() in _SKIP_PROBE_LABELS:
        logger.debug(f"Skipping probe for '{label}' (skip set)")
        return []

    try:
        clicked = False

        if trigger_selector:
            el = await page.query_selector(trigger_selector)
            if el and await el.is_visible():
                await el.click()
                clicked = True

        if not clicked:
            # "Label-down" strategy: find the label element first, then locate
            # the nearest select__control in the same container. Tag it with a
            # data attribute so Playwright can click it with real mouse events
            # (JS element.click() doesn't fire proper pointer events for React Select).
            await page.evaluate(f"""
            () => {{
                const needle = {json.dumps(label[:50].lower())};
                const shortNeedle = needle.slice(0, 30);

                // Step 1: find label-like elements whose text matches.
                const candidates = [];
                document.querySelectorAll('label, [class*="label"], span, div').forEach(el => {{
                    if (el.querySelector('[class*="select__control"]')) return;
                    const text = (el.innerText || '').trim().replace(/[*]/g, '').toLowerCase();
                    if (!text || text.length > 200) return;
                    if (text === needle || text.startsWith(shortNeedle) ||
                        (shortNeedle.length >= 6 && text.includes(shortNeedle) && text.length < 80)) {{
                        candidates.push(el);
                    }}
                }});

                // Step 2: for each candidate, walk UP to find a container
                // that holds exactly one select__control.
                for (const labelEl of candidates) {{
                    let container = labelEl.parentElement;
                    for (let d = 0; d < 5 && container; d++) {{
                        const ctrls = container.querySelectorAll('[class*="select__control"]');
                        if (ctrls.length === 1 && ctrls[0].getBoundingClientRect().width > 0) {{
                            ctrls[0].setAttribute('data-probe-click', 'true');
                            return;
                        }}
                        container = container.parentElement;
                    }}
                }}
            }}
            """)
            target = await page.query_selector('[data-probe-click="true"]')
            if target:
                await target.scroll_into_view_if_needed()
                await target.click()
                await page.evaluate('document.querySelector("[data-probe-click]")?.removeAttribute("data-probe-click")')
                clicked = True

        if not clicked:
            logger.debug(f"Could not click dropdown for '{label}'")
            return []

        logger.debug(f"Probing options for '{label}'...")
        await random_delay(0.5, 1.0)  # let options render

        # Read options directly from the DOM — faster and more reliable than
        # screenshotting and calling a vision LLM.
        # Priority: class-based selectors BEFORE [role="option"] to avoid
        # picking up persistent country-code menu nodes from other dropdowns.
        options = await page.evaluate("""
        () => {
            const candidates = [
                // React Select class-based (most specific — avoids cross-dropdown bleed)
                document.querySelectorAll('[class*="select__option"]'),
                document.querySelectorAll('[class*="select__menu"] [class*="option"]'),
                // Generic open menu option class
                document.querySelectorAll('[class*="menu-list"] [class*="option"]'),
                // ARIA listbox — only if class-based gave nothing (more likely to bleed)
                document.querySelectorAll('[role="listbox"] [role="option"]'),
                document.querySelectorAll('[role="option"]'),
            ];
            const junk = new Set(['Select...', '-- Select --', '', 'Loading...']);
            for (const els of candidates) {
                if (!els.length) continue;
                const texts = Array.from(els)
                    .map(el => el.innerText.trim())
                    .filter(t => t && !junk.has(t));
                if (texts.length > 0) return texts;
            }
            // Fallback: native <select> options (for non-React dropdowns)
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                if (sel.offsetWidth > 0 && sel.size > 1) {
                    const opts = Array.from(sel.options)
                        .map(o => o.text.trim())
                        .filter(t => t && !junk.has(t) && !t.startsWith('--'));
                    if (opts.length > 0) return opts;
                }
            }
            return [];
        }
        """)

        if options:
            # Discard country-code-like option lists (e.g. "Afghanistan+93") —
            # these come from the phone country code picker bleeding into other probes.
            import re as _re
            if len(options) > 5 and sum(
                1 for o in options[:10] if _re.search(r'\+\d+$', o)
            ) >= 8:
                logger.debug(f"Discarding country-code options for '{label}' ({len(options)} opts)")
                return []
            capped = options[:_MAX_OPTIONS]
            logger.debug(f"Probed '{label}': {len(options)} options (capped to {len(capped)})")
            return capped

        logger.debug(f"No DOM options found for '{label}' — dropdown may not have opened")
        return []

    except Exception as e:
        logger.warning(f"Dropdown probe failed for '{label}': {e}")
        return []
    finally:
        # Close the dropdown and give React time to unmount the menu DOM node.
        try:
            await page.keyboard.press("Escape")
            await random_delay(0.3, 0.5)
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
    dropdown_selectors = await page.evaluate("""
    () => {
        const results = [];

        // Native selects
        document.querySelectorAll('select').forEach(el => {
            if (el.getBoundingClientRect().width > 0) {
                const label = (() => {
                    if (el.id) {
                        const lbl = document.querySelector(`label[for="${el.id}"]`);
                        if (lbl) return lbl.innerText.trim().replace(/[*]/g, '').trim();
                    }
                    return el.name || '';
                })();
                results.push({
                    selector: el.id ? `#${el.id}` : `select[name="${el.name}"]`,
                    kind: 'select',
                    label: label,
                });
            }
        });

        // React Select controls — walk UP from each control to find the nearest
        // label text (works even when the label is a <div> or <span>, not <label>)
        document.querySelectorAll('[class*="select__control"]').forEach(control => {
            if (!control.getBoundingClientRect().width) return;
            let parent = control.parentElement;
            let label = '';
            for (let depth = 0; depth < 8 && parent && !label; depth++) {
                for (const sibling of parent.children) {
                    if (sibling.contains(control)) continue; // skip the branch with the control
                    const text = (sibling.innerText || '').trim().replace(/[*]/g, '').trim();
                    // Accept short text that looks like a label (not another form widget)
                    if (text && text.length < 120 && !sibling.querySelector('input, select, textarea, [class*="select__control"]')) {
                        label = text.split('\\n')[0].trim(); // first line only
                        break;
                    }
                }
                parent = parent.parentElement;
            }
            if (label && !results.find(r => r.label === label && r.kind === 'react_select')) {
                results.push({ selector: null, kind: 'react_select', label: label });
            }
        });

        return results;
    }
    """)

    logger.debug(f"Dropdown selectors found: {[dd.get('label','?') for dd in dropdown_selectors]}")

    # Probe each dropdown
    for dd in dropdown_selectors:
        label = dd.get("label", "")
        kind = dd.get("kind", "select")
        selector = dd.get("selector", "")

        if not label:
            continue

        if kind == "react_select":
            # Pass None — probe_dropdown_options will use JS DOM walk to find it
            trigger_sel = None
        else:
            trigger_sel = selector

        options = await probe_dropdown_options(page, label, trigger_sel)

        # Merge options into matching unique_field entry
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
