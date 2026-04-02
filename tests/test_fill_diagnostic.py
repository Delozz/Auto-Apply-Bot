"""
test_fill_diagnostic.py

Non-interactive diagnostic run. Scrapes top job, runs vision analysis + adaptive
fill on it, takes a full-page screenshot of the filled form, then quits without
submitting. Outputs a detailed fill report to stdout.

Run with:
    PYTHONPATH=. python3 tests/test_fill_diagnostic.py
"""
import asyncio
import json
from pathlib import Path
from app.scraper.greenhouse_scraper import scrape_all_greenhouse
from app.llm.resume_tailor import extract_resume_text
from app.llm.embeddings import filter_jobs_by_score
from app.llm.cover_letter_gen import generate_cover_letter, save_cover_letter
from app.llm.resume_pdf_gen import generate_tailored_pdf
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.automation.adaptive_filler import adaptive_fill, scan_form_fields
from app.automation.form_filler import fill_greenhouse_application
from app.vision.form_analyzer import analyze_form_with_vision
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="5127878221",
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "master_resume.pdf"),
    graduation_year="2028",
    linkedin_url="https://www.linkedin.com/in/devon-lopez1",
    github_url="https://github.com/Delozz",
    website_url="",
)

SCREENSHOT_PATH = Path("data/logs/diagnostic_form.png")
SCREENSHOT_FULL_PATH = Path("data/logs/diagnostic_form_full.png")


async def run_diagnostic():
    print("\n" + "="*60)
    print("DIAGNOSTIC: Vision Form Analyzer Test")
    print("="*60)

    # Step 1: Scrape and pick top job
    print("\n[1/5] Scraping jobs...")
    jobs = await scrape_all_greenhouse()
    resume_text = extract_resume_text(CANDIDATE.resume_path)
    qualified = filter_jobs_by_score(resume_text, [j.model_dump() for j in jobs])

    if not qualified:
        print("ERROR: No qualified jobs found.")
        return

    top = qualified[0]
    job = JobPosting(**top)
    print(f"  → Top job: [{job.match_score:.3f}] {job.role} @ {job.company}")
    print(f"  → URL: {job.application_url}")

    # Step 2: Generate resume + cover letter (reuse if already exists)
    print("\n[2/5] Generating documents...")
    tailored_resume_path = generate_tailored_pdf(master_resume_path=CANDIDATE.resume_path, job=job)
    candidate_for_job = CANDIDATE.model_copy(update={"resume_path": tailored_resume_path})
    cover_letter = generate_cover_letter(candidate_for_job, job)
    cover_letter_path = save_cover_letter(cover_letter, job.company, job.role)
    print(f"  → Resume: {tailored_resume_path}")
    print(f"  → Cover letter: {cover_letter_path}")

    # Step 3: Open browser, navigate, run vision + fill
    print("\n[3/5] Opening form in browser (headless=False so you can watch)...")
    playwright, browser, context, page = await launch_browser(headless=False)

    try:
        await page.goto(job.application_url, timeout=30000)
        await random_delay(2.5, 3.5)

        # Vision analysis
        print("\n[4/5] Running vision form analysis...")
        try:
            manifest = await analyze_form_with_vision(page, job.application_url)
            print(f"\n  MANIFEST SUMMARY ({len(manifest.fields)} fields):")
            for f in manifest.fields:
                opts = f"  options={f.options[:4]}" if f.options else ""
                print(f"  [{f.field_type:12}] {f.label!r:40}{opts}")
        except Exception as e:
            print(f"  WARNING: Vision analysis failed: {e}")
            manifest = None

        # Adaptive fill
        print("\n[5/5] Running adaptive fill...")
        await adaptive_fill(
            page=page,
            candidate=candidate_for_job,
            job=job,
            resume_path=candidate_for_job.resume_path,
            cover_letter=cover_letter,
            cover_letter_path=cover_letter_path,
            why_interested=cover_letter,
            manifest=manifest,
        )

        # Greenhouse second pass
        if "greenhouse.io" in job.application_url:
            await fill_greenhouse_application(
                page=page,
                candidate=candidate_for_job,
                cover_letter_text=cover_letter,
                cover_letter_path=cover_letter_path,
                city="Cedar Park, Texas, United States",
                why_interested=cover_letter,
                how_did_you_hear="LinkedIn",
                swe_area_1="",
                swe_area_2="",
            )

        # Take screenshots
        await page.evaluate("window.scrollTo(0, 0)")
        await random_delay(0.5, 1.0)
        await page.screenshot(path=str(SCREENSHOT_PATH), full_page=False)
        await page.screenshot(path=str(SCREENSHOT_FULL_PATH), full_page=True)
        print(f"\n  Screenshots saved:")
        print(f"    Viewport: {SCREENSHOT_PATH}")
        print(f"    Full page: {SCREENSHOT_FULL_PATH}")

        # React Select filled value scan (more reliable than checking input.value)
        print("\n" + "="*60)
        print("REACT SELECT FILLED VALUES:")
        print("="*60)
        react_values = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('[class*="select__control"]').forEach(ctrl => {
                if (!ctrl.getBoundingClientRect().width) return;
                // Get the selected value text
                const valueEl = ctrl.querySelector('[class*="select__single-value"]');
                const selectedValue = valueEl ? valueEl.innerText.trim() : '';
                // Get label via walk-up
                let parent = ctrl.parentElement;
                let label = '';
                for (let d = 0; d < 4 && parent && !label; d++) {
                    for (const sib of parent.children) {
                        if (sib.contains(ctrl)) continue;
                        const t = (sib.innerText || '').trim().replace(/[*]/g, '').trim();
                        if (t && t.length < 150 && !sib.querySelector('[class*="select__control"]')) {
                            label = t.split('\\n')[0]; break;
                        }
                    }
                    parent = parent.parentElement;
                }
                results.push({label: label || '(no label)', value: selectedValue || '(empty)'});
            });
            return results;
        }
        """)
        for r in react_values:
            status = "✓" if r['value'] != '(empty)' else "✗"
            print(f"  {status} {r['label']!r:50} → {r['value']!r}")

        # Native text/select field scan
        print("\n" + "="*60)
        print("EMPTY NATIVE FIELDS (text/select with no value):")
        print("="*60)
        fields_after = await page.evaluate("""
        () => {
            const empty = [];
            // Only check non-React-Select text inputs (skip internal select__input)
            document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], textarea').forEach(el => {
                if (el.closest('[class*="select__"]') || el.getAttribute('role') === 'combobox') return;
                if (!el.value && el.offsetWidth > 0) {
                    const lbl = (() => {
                        if (el.id) {
                            const l = document.querySelector(`label[for="${el.id}"]`);
                            if (l) return l.innerText.trim();
                        }
                        return el.placeholder || el.name || '(unknown)';
                    })();
                    empty.push({label: lbl, type: 'text', id: el.id || '', name: el.name || ''});
                }
            });
            document.querySelectorAll('select').forEach(el => {
                const idx = el.selectedIndex;
                const val = idx >= 0 ? el.options[idx]?.text : '';
                if ((!val || val.startsWith('-- ') || val === 'Select') && el.offsetWidth > 0) {
                    const lbl = (() => {
                        if (el.id) {
                            const l = document.querySelector(`label[for="${el.id}"]`);
                            if (l) return l.innerText.trim();
                        }
                        return el.name || '(unknown select)';
                    })();
                    const opts = Array.from(el.options).map(o => o.text).filter(t => t && !t.startsWith('--')).slice(0, 6);
                    empty.push({label: lbl, type: 'select', id: el.id || '', options: opts});
                }
            });
            return empty;
        }
        """)
        if fields_after:
            for f in fields_after:
                opts = f"  available: {f.get('options', [])}" if f.get('options') else ""
                print(f"  EMPTY [{f['type']:6}] {f['label']!r:40}{opts}")
        else:
            print("  All native fields have values.")

        print("\n" + "="*60)
        print("DIAGNOSTIC COMPLETE — browser stays open for 30s, then closes")
        print("="*60)
        await asyncio.sleep(30)

    finally:
        await close_browser(playwright, browser)
        print("\nBrowser closed. NOT submitted.")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
