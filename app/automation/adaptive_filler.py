"""
adaptive_filler.py

An LLM-powered form filler that works on ANY application form
without needing hardcoded selectors.

How it works:
1. Scan the page DOM to extract every visible form field + its label
2. Send the field map + candidate profile to the LLM
3. LLM returns a filling plan: [{label, value, action}]
4. Execute each action using the right Playwright method

This handles Greenhouse, Lever, Workday, and any custom ATS
without any company-specific configuration.
"""
import json
from playwright.async_api import Page
from openai import OpenAI
from app.config import settings
from app.utils.validators import CandidateProfile, JobPosting, FormManifest
from app.automation.playwright_engine import random_delay
from app.automation.form_filler import select_react_dropdown, _fill_by_label
from app.utils.logger import logger

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


# ─── Step 1: DOM Scanner ──────────────────────────────────────────────────────

async def scan_form_fields(page: Page) -> list[dict]:
    """
    Scan the page and extract every visible form field with its label.
    Returns a list of field descriptors the LLM can reason about.
    """
    fields = await page.evaluate("""
    () => {
        const results = [];

        function getLabel(el) {
            // Try for attribute
            if (el.id) {
                const lbl = document.querySelector(`label[for="${el.id}"]`);
                if (lbl) return lbl.innerText.trim().replace(/[*]/g, '').trim();
            }
            // Try aria-label
            if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
            // Try placeholder
            if (el.placeholder) return el.placeholder.trim();
            // Try closest label
            const closest = el.closest('label');
            if (closest) return closest.innerText.trim();
            // Try previous sibling label
            let prev = el.previousElementSibling;
            while (prev) {
                if (prev.tagName === 'LABEL' || prev.className.includes('label')) {
                    return prev.innerText.trim().replace(/[*]/g, '').trim();
                }
                prev = prev.previousElementSibling;
            }
            // Try parent's label child
            const parent = el.parentElement;
            if (parent) {
                const parentLabel = parent.querySelector('label, .label, [class*="label"]');
                if (parentLabel) return parentLabel.innerText.trim().replace(/[*]/g, '').trim();
            }
            return '';
        }

        function isVisible(el) {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 &&
                   window.getComputedStyle(el).display !== 'none' &&
                   window.getComputedStyle(el).visibility !== 'hidden';
        }

        // Standard text inputs
        document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type])').forEach(el => {
            if (!isVisible(el)) return;
            const label = getLabel(el);
            if (!label && !el.placeholder) return;
            results.push({
                type: 'text',
                label: label || el.placeholder,
                selector: el.id ? `#${el.id}` : null,
                name: el.name || '',
                placeholder: el.placeholder || '',
            });
        });

        // Textareas
        document.querySelectorAll('textarea').forEach(el => {
            if (!isVisible(el)) return;
            const label = getLabel(el);
            results.push({
                type: 'textarea',
                label: label || el.placeholder || 'textarea',
                selector: el.id ? `#${el.id}` : null,
                name: el.name || '',
                placeholder: el.placeholder || '',
            });
        });

        // Native selects
        document.querySelectorAll('select').forEach(el => {
            if (!isVisible(el)) return;
            const label = getLabel(el);
            const options = Array.from(el.options).map(o => o.text).filter(t => t && t !== 'Select...' && t !== '-- Select --');
            results.push({
                type: 'select',
                label: label || 'dropdown',
                selector: el.id ? `#${el.id}` : null,
                name: el.name || '',
                options: options.slice(0, 20),
            });
        });

        // React Select / custom dropdowns (identified by .select__label or combobox role)
        document.querySelectorAll('.select, [class*="select-shell"]').forEach(el => {
            if (!isVisible(el)) return;
            const labelEl = el.querySelector('.select__label, label, [class*="label"]');
            if (!labelEl) return;
            const label = labelEl.innerText.trim().replace(/[*]/g, '').trim();
            if (!label) return;
            // Don't duplicate if we already caught this
            const already = results.find(r => r.label === label && r.type === 'react_select');
            if (!already) {
                results.push({
                    type: 'react_select',
                    label: label,
                    selector: null,
                });
            }
        });

        // File inputs
        document.querySelectorAll('input[type="file"]').forEach(el => {
            if (!isVisible(el)) return;
            const label = getLabel(el);
            results.push({
                type: 'file',
                label: label || 'file upload',
                selector: el.id ? `#${el.id}` : null,
                name: el.name || '',
                accepts: el.accept || '',
            });
        });

        // Checkboxes
        document.querySelectorAll('input[type="checkbox"]').forEach(el => {
            if (!isVisible(el)) return;
            const label = getLabel(el);
            if (label) {
                results.push({
                    type: 'checkbox',
                    label: label,
                    selector: el.id ? `#${el.id}` : null,
                    name: el.name || '',
                });
            }
        });

        return results;
    }
    """)

    logger.info(f"DOM scan found {len(fields)} form fields")
    return fields


# ─── Step 1b: Manifest Merger ─────────────────────────────────────────────────

def merge_manifest_with_dom(dom_fields: list[dict], manifest: FormManifest) -> list[dict]:
    """
    Enrich DOM-scanned fields with vision manifest data.
    The manifest may have fields the DOM scan missed (shadow DOM, custom components).
    For fields found in both, the manifest's option list takes precedence.
    """
    manifest_index = {f.label.strip().lower(): f for f in manifest.fields}

    merged = []
    dom_labels_seen: set[str] = set()

    for dom_field in dom_fields:
        label = (dom_field.get("label") or "").strip().lower()
        dom_labels_seen.add(label)
        if label in manifest_index:
            mf = manifest_index[label]
            if mf.options:
                dom_field = {**dom_field, "options": mf.options}
            if mf.required:
                dom_field = {**dom_field, "required": True}
        merged.append(dom_field)

    # Add manifest fields not found in DOM scan
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

    logger.info(f"Merged: {len(dom_fields)} DOM + {len(manifest.fields)} manifest → {len(merged)} total fields")
    return merged


# ─── Step 2: LLM Field Mapper ─────────────────────────────────────────────────

def get_filling_plan(
    fields: list[dict],
    candidate: CandidateProfile,
    job: JobPosting,
    cover_letter: str = "",
    why_interested: str = "",
) -> list[dict]:
    """
    Send the field map + candidate profile to the LLM.
    Returns a filling plan: list of {label, value, action, skip_if_missing}.

    The LLM figures out which value goes in which field — no hardcoding needed.
    """
    candidate_data = {
        "name": candidate.name,
        "first_name": candidate.name.split()[0],
        "last_name": candidate.name.split()[-1],
        "email": candidate.email,
        "phone": candidate.phone,
        "phone_digits_only": candidate.phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", ""),
        "education": candidate.education,
        "school": "Texas A&M University- College Station",
        "location": "Cedar Park, Texas, United States",
        "city": "Cedar Park",
        "graduation": "June 2028",
        "degree": "Bachelor's",
        "linkedin": candidate.linkedin_url or "",
        "github": candidate.github_url or "",
        "website": candidate.website_url or "",
        "authorized_to_work": "Yes",
        "requires_sponsorship": "No",
        "currently_enrolled": "Yes",
        "gender": "Male",
        "hispanic": "Yes",
        "race": "White",
        "veteran": "I am not a protected veteran",
        "disability": "No, I do not have a disability and have not had one in the past",
        "how_heard": "LinkedIn",
        "cover_letter": cover_letter[:300] + "..." if len(cover_letter) > 300 else cover_letter,
        "why_interested": why_interested[:400] + "..." if len(why_interested) > 400 else why_interested,
    }

    fields_json = json.dumps(fields, indent=2)
    candidate_json = json.dumps(candidate_data, indent=2)

    prompt = f"""You are filling out a job application form for {job.role} at {job.company}.

CANDIDATE PROFILE:
{candidate_json}

FORM FIELDS FOUND ON PAGE:
{fields_json}

INSTRUCTIONS:
- For each field, determine the correct value from the candidate profile
- Match fields by their label text (case-insensitive, partial match is fine)
- For dropdowns (select/react_select), pick the option that most closely matches
- For file fields (resume/CV), use the value "UPLOAD_RESUME"
- For cover letter file fields, use "UPLOAD_COVER_LETTER"
- For privacy/acknowledgement checkboxes, use "CHECK"
- Skip fields you can't confidently fill (leave them out of the response)
- For essay questions about "why interested", use the why_interested text
- For cover letter text fields, use the cover_letter text

Return ONLY valid JSON array, no markdown, no explanation:
[
  {{"label": "exact label text from form", "value": "value to fill", "action": "fill|select|react_select|file|checkbox"}},
  ...
]

Actions:
- "fill" = type into text input or textarea
- "select" = native HTML select dropdown
- "react_select" = custom React Select dropdown
- "file" = file upload input
- "checkbox" = check a checkbox"""

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw.strip())
        logger.info(f"LLM generated filling plan with {len(plan)} actions")
        return plan
    except Exception as e:
        logger.error(f"LLM filling plan failed: {e}")
        return []


# ─── Step 3: Execute Plan ─────────────────────────────────────────────────────

async def execute_filling_plan(
    page: Page,
    plan: list[dict],
    resume_path: str,
    cover_letter_path: str = "",
) -> dict:
    """
    Execute the LLM-generated filling plan action by action.
    Returns a summary of what was filled, skipped, and failed.
    """
    results = {"filled": 0, "skipped": 0, "failed": 0}

    for action in plan:
        label = action.get("label", "")
        value = action.get("value", "")
        action_type = action.get("action", "fill")

        if not label or not value:
            continue

        try:
            if action_type == "file":
                path = resume_path if value == "UPLOAD_RESUME" else cover_letter_path
                if path:
                    selectors = [
                        f'input[type="file"][id*="resume"]' if value == "UPLOAD_RESUME" else 'input[type="file"][id*="cover"]',
                        'input[type="file"]',
                    ]
                    for sel in selectors:
                        el = await page.query_selector(sel)
                        if el:
                            await el.set_input_files(path)
                            await random_delay(1.0, 2.0)
                            logger.debug(f"Uploaded file for: {label}")
                            results["filled"] += 1
                            break
                else:
                    results["skipped"] += 1
                continue

            elif action_type == "checkbox" and value == "CHECK":
                filled = False
                # Try by label text
                try:
                    label_el = await page.query_selector(f'label:has-text("{label[:30]}")')
                    if label_el:
                        for_attr = await label_el.get_attribute("for")
                        if for_attr:
                            cb = await page.query_selector(f'#{for_attr}')
                            if cb and not await cb.is_checked():
                                await cb.check()
                                await random_delay(0.1, 0.2)
                                filled = True
                except Exception:
                    pass
                if filled:
                    results["filled"] += 1
                    logger.debug(f"Checked: {label}")
                else:
                    results["skipped"] += 1
                continue

            elif action_type == "react_select":
                success = await select_react_dropdown(page, label[:30], value)
                results["filled" if success else "skipped"] += 1
                continue

            elif action_type == "select":
                # Try native select by label
                try:
                    label_el = await page.query_selector(f'label:has-text("{label[:30]}")')
                    if label_el:
                        for_attr = await label_el.get_attribute("for")
                        if for_attr:
                            await page.select_option(f'#{for_attr}', label=value)
                            await random_delay(0.1, 0.2)
                            results["filled"] += 1
                            logger.debug(f"Selected '{value}' for: {label}")
                            continue
                except Exception:
                    pass
                results["skipped"] += 1
                continue

            else:  # fill — text input or textarea
                filled = await _fill_by_label(page, label[:40], value)
                if not filled:
                    # Try by placeholder
                    try:
                        el = await page.query_selector(f'input[placeholder*="{label[:20]}"], textarea[placeholder*="{label[:20]}"]')
                        if el and await el.is_visible():
                            await page.fill(f'input[placeholder*="{label[:20]}"]', value)
                            filled = True
                    except Exception:
                        pass
                results["filled" if filled else "skipped"] += 1
                if filled:
                    logger.debug(f"Filled '{label}': {value[:30]}")

        except Exception as e:
            logger.warning(f"Action failed for '{label}': {e}")
            results["failed"] += 1

    logger.info(f"Filling plan executed: {results['filled']} filled, {results['skipped']} skipped, {results['failed']} failed")
    return results


# ─── Master adaptive filler ───────────────────────────────────────────────────

async def adaptive_fill(
    page: Page,
    candidate: CandidateProfile,
    job: JobPosting,
    resume_path: str,
    cover_letter: str = "",
    cover_letter_path: str = "",
    why_interested: str = "",
    manifest: FormManifest | None = None,
):
    """
    Main entry point — scans the page, asks the LLM what to fill,
    and executes the filling plan. Works on ANY form without config.

    Falls back gracefully — any field it can't figure out stays empty
    for you to fill manually at the approval gate.
    """
    logger.info("Starting adaptive form fill...")

    # Step 1: Scan the DOM
    await random_delay(1.0, 1.5)  # let page fully render
    fields = await scan_form_fields(page)

    if not fields:
        logger.warning("No form fields detected — page may not have loaded fully")
        return

    # Enrich with vision manifest when available
    if manifest:
        fields = merge_manifest_with_dom(fields, manifest)

    # Step 2: Ask LLM for filling plan
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

    # Step 3: Execute
    await execute_filling_plan(
        page=page,
        plan=plan,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )

    logger.info("Adaptive fill complete ✅")