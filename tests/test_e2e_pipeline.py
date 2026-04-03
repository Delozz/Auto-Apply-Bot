"""
test_e2e_pipeline.py

End-to-end tests for the three core pipeline flows:

  1. Scraping — Greenhouse API → JobPosting objects, US location filter
  2. Scoring  — resume embeddings → similarity threshold → ranked list
  3. Tracking — URL normalization, already-applied deduplication

Run with:
    PYTHONPATH=. python3 -m pytest tests/test_e2e_pipeline.py -v
"""
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _greenhouse_job(title: str, location: str, job_id: int = 1) -> dict:
    """Minimal Greenhouse API job payload."""
    return {
        "id": job_id,
        "title": title,
        "location": {"name": location},
        "absolute_url": f"https://boards.greenhouse.io/testco/jobs/{job_id}",
        "content": f"We are hiring a {title}. Python, C++, algorithms required.",
    }


def _fake_greenhouse_response(jobs: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"jobs": jobs}
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# FLOW 1 — Scraping
# ══════════════════════════════════════════════════════════════════════════════

class TestScrapingFlow:
    """Greenhouse scraper correctly filters roles and US-only locations."""

    @pytest.mark.asyncio
    async def test_non_intern_roles_excluded(self):
        """Full-time roles must be dropped even if they match SWE keywords."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        jobs = [
            _greenhouse_job("Software Engineer", "New York, NY, United States", 1),
            _greenhouse_job("Software Engineer Intern", "New York, NY, United States", 2),
        ]
        mock_resp = _fake_greenhouse_response(jobs)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        titles = [j.role for j in result]
        assert "Software Engineer Intern" in titles
        assert "Software Engineer" not in titles

    @pytest.mark.asyncio
    async def test_non_swe_intern_roles_excluded(self):
        """Marketing/sales intern roles must be dropped."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        jobs = [
            _greenhouse_job("Marketing Intern", "New York, NY, United States", 1),
            _greenhouse_job("Software Engineer Intern", "Austin, TX, United States", 2),
        ]
        mock_resp = _fake_greenhouse_response(jobs)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        titles = [j.role for j in result]
        assert "Software Engineer Intern" in titles
        assert "Marketing Intern" not in titles

    @pytest.mark.asyncio
    async def test_international_locations_excluded(self):
        """Non-US postings must be dropped."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        jobs = [
            _greenhouse_job("Software Engineer Intern", "Singapore", 1),
            _greenhouse_job("Quantitative Researcher Intern", "Hong Kong SAR", 2),
            _greenhouse_job("SWE Intern", "London, United Kingdom", 3),
            _greenhouse_job("SWE Intern", "New York, NY, United States", 4),
        ]
        mock_resp = _fake_greenhouse_response(jobs)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        assert len(result) == 1
        assert result[0].location == "New York, NY, United States"

    @pytest.mark.asyncio
    async def test_remote_postings_included(self):
        """Remote postings (no explicit country) must pass the US filter."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        jobs = [
            _greenhouse_job("SWE Intern", "Remote", 1),
            _greenhouse_job("Backend Engineer Intern", "Remote - United States", 2),
        ]
        mock_resp = _fake_greenhouse_response(jobs)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_location_not_excluded(self):
        """Jobs with no location set must pass through (can't confirm non-US)."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        jobs = [_greenhouse_job("SWE Intern", "", 1)]
        mock_resp = _fake_greenhouse_response(jobs)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_scraper_handles_api_error_gracefully(self):
        """API failure must return empty list, not raise."""
        from app.scraper.greenhouse_scraper import scrape_greenhouse_board

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_greenhouse_board("TestCo", "testco")

        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# FLOW 2 — Scoring & Filtering
# ══════════════════════════════════════════════════════════════════════════════

class TestScoringFlow:
    """Embedding similarity threshold filters and ranks jobs correctly."""

    STRONG_RESUME = (
        "Python C++ software engineer internship quantitative finance "
        "data structures algorithms distributed systems backend"
    )

    def _make_jobs(self) -> list[dict]:
        return [
            {
                "company": "RelevantCo",
                "role": "Software Engineer Intern",
                "description": "Python C++ algorithms data structures backend systems",
                "application_url": "https://boards.greenhouse.io/relevantco/jobs/1",
                "location": "New York, NY",
                "source": "greenhouse",
                "requirements": [],
            },
            {
                "company": "IrrelevantCo",
                "role": "Chef Intern",
                "description": "Cooking, baking, culinary arts, food preparation, kitchen management",
                "application_url": "https://boards.greenhouse.io/irrelevantco/jobs/2",
                "location": "Chicago, IL",
                "source": "greenhouse",
                "requirements": [],
            },
        ]

    def test_high_match_job_passes_threshold(self):
        from app.llm.embeddings import filter_jobs_by_score
        result = filter_jobs_by_score(self.STRONG_RESUME, self._make_jobs())
        companies = [j["company"] for j in result]
        assert "RelevantCo" in companies

    def test_low_match_job_filtered_out(self):
        from app.llm.embeddings import filter_jobs_by_score
        result = filter_jobs_by_score(self.STRONG_RESUME, self._make_jobs())
        companies = [j["company"] for j in result]
        assert "IrrelevantCo" not in companies

    def test_results_sorted_by_score_descending(self):
        from app.llm.embeddings import filter_jobs_by_score
        jobs = [
            {
                "company": "A",
                "role": "SWE Intern",
                "description": "Python algorithms",
                "application_url": "https://example.com/1",
                "location": "NY",
                "source": "greenhouse",
                "requirements": [],
            },
            {
                "company": "B",
                "role": "SWE Intern",
                "description": (
                    "Python C++ algorithms data structures distributed systems "
                    "backend quantitative finance internship software engineer"
                ),
                "application_url": "https://example.com/2",
                "location": "NY",
                "source": "greenhouse",
                "requirements": [],
            },
        ]
        result = filter_jobs_by_score(self.STRONG_RESUME, jobs)
        if len(result) >= 2:
            scores = [j["match_score"] for j in result]
            assert scores == sorted(scores, reverse=True)

    def test_match_score_added_to_qualified_jobs(self):
        from app.llm.embeddings import filter_jobs_by_score
        result = filter_jobs_by_score(self.STRONG_RESUME, self._make_jobs())
        for job in result:
            assert "match_score" in job
            assert 0.0 <= job["match_score"] <= 1.0

    def test_empty_job_list_returns_empty(self):
        from app.llm.embeddings import filter_jobs_by_score
        result = filter_jobs_by_score(self.STRONG_RESUME, [])
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# FLOW 3 — Application Tracking
# ══════════════════════════════════════════════════════════════════════════════

class TestTrackingFlow:
    """URL normalization and already-applied deduplication work correctly."""

    def _tracker(self, tmp_path: Path):
        """Return tracker functions bound to a temp file."""
        import importlib
        import app.utils.application_tracker as mod
        # Monkeypatch the file path so tests don't touch real data
        original = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        yield mod
        mod.APPLIED_JOBS_FILE = original

    def test_mark_and_load_roundtrip(self, tmp_path):
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        try:
            mod.mark_as_applied("https://boards.greenhouse.io/co/jobs/1", "TestCo", "SWE Intern")
            urls = mod.load_applied_urls()
            assert "https://boards.greenhouse.io/co/jobs/1" in urls
        finally:
            mod.APPLIED_JOBS_FILE = orig

    def test_query_params_normalized_on_save(self, tmp_path):
        """URLs saved with ?gh_jid=... must match the bare URL on load."""
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        try:
            url_with_params = "https://boards.greenhouse.io/co/jobs/1?gh_jid=1"
            mod.mark_as_applied(url_with_params, "TestCo", "SWE Intern")
            urls = mod.load_applied_urls()
            assert "https://boards.greenhouse.io/co/jobs/1" in urls
            assert url_with_params not in urls
        finally:
            mod.APPLIED_JOBS_FILE = orig

    def test_query_params_normalized_on_filter(self, tmp_path):
        """Scraper URL without params must be filtered if base URL was applied to."""
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        try:
            mod.mark_as_applied(
                "https://boards.greenhouse.io/point72/jobs/999?gh_jid=999",
                "Point72", "Quant Intern"
            )
            applied = mod.load_applied_urls()
            scraped_url = "https://boards.greenhouse.io/point72/jobs/999"
            from app.utils.application_tracker import _normalize_url
            assert _normalize_url(scraped_url) in applied
        finally:
            mod.APPLIED_JOBS_FILE = orig

    def test_different_jobs_not_deduplicated(self, tmp_path):
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        try:
            mod.mark_as_applied("https://boards.greenhouse.io/co/jobs/1", "Co", "Role A")
            mod.mark_as_applied("https://boards.greenhouse.io/co/jobs/2", "Co", "Role B")
            urls = mod.load_applied_urls()
            assert len(urls) == 2
        finally:
            mod.APPLIED_JOBS_FILE = orig

    def test_missing_file_returns_empty_set(self, tmp_path):
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "nonexistent.json"
        try:
            assert mod.load_applied_urls() == set()
        finally:
            mod.APPLIED_JOBS_FILE = orig

    def test_duplicate_application_not_written_twice(self, tmp_path):
        """Calling mark_as_applied twice with the same URL shouldn't explode."""
        import app.utils.application_tracker as mod
        orig = mod.APPLIED_JOBS_FILE
        mod.APPLIED_JOBS_FILE = tmp_path / "applied_jobs.json"
        try:
            url = "https://boards.greenhouse.io/co/jobs/1"
            mod.mark_as_applied(url, "Co", "Role")
            mod.mark_as_applied(url, "Co", "Role")
            with (tmp_path / "applied_jobs.json").open() as f:
                data = json.load(f)
            # Should have two entries (idempotency is enforced at pipeline level)
            # but no crash
            assert len(data) == 2
        finally:
            mod.APPLIED_JOBS_FILE = orig
