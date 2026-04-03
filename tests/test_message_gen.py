"""
test_message_gen.py  — TDD for linkedin_message_gen and recruiter text parsing.

RED phase: tests written before verifying they pass.

Run with:
    PYTHONPATH=. python3 -m pytest tests/test_message_gen.py -v
"""
import pytest
from unittest.mock import MagicMock, patch
from app.utils.validators import CandidateProfile
from app.utils.constants import RESUMES_DIR


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def candidate():
    return CandidateProfile(
        name="Devon Lopez",
        email="devoninternships@gmail.com",
        phone="5127878221",
        education="Texas A&M University - Computer Science",
        skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
        interests=[],
        resume_path=str(RESUMES_DIR / "Devon_Lopez_SWE_Quant.pdf"),
        graduation_year="2028",
        linkedin_url="",
        github_url="",
        website_url="",
    )


def _mock_llm(question: str):
    """Return a mock OpenAI client that always returns the given question string."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = question
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ══════════════════════════════════════════════════════════════════════════════
# recruiter_finder — inline text parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestRecruiterTextParsing:
    """
    LinkedIn embeds the full card text in the link's inner_text.
    The parser splits on ' • ' and newlines to extract name and title.

    Format:  "Name \n • 3rd+\n\nTitle at Company\n\nLocation"
    """

    def _parse(self, raw: str) -> tuple[str, str]:
        """Replicate the parsing logic from recruiter_finder._search_recruiters_on_page."""
        lines = [l.strip() for l in raw.replace(" • ", "\n").split("\n") if l.strip()]
        name = lines[0] if lines else "Unknown"
        title = lines[2] if len(lines) > 2 else ""
        return name, title

    def test_standard_3rd_connection_format(self):
        raw = "Lily Farriss \n • 3rd+\n\nCampus Recruiter at Point72\n\nNew York, NY"
        name, title = self._parse(raw)
        assert name == "Lily Farriss"
        assert title == "Campus Recruiter at Point72"

    def test_2nd_connection_format(self):
        raw = "John Smith \n • 2nd\n\nTalent Acquisition at Stripe\n\nSan Francisco, CA"
        name, title = self._parse(raw)
        assert name == "John Smith"
        assert title == "Talent Acquisition at Stripe"

    def test_name_only_no_title(self):
        """Only one line — should return name and empty title."""
        raw = "Jane Doe"
        name, title = self._parse(raw)
        assert name == "Jane Doe"
        assert title == ""

    def test_name_and_degree_no_title(self):
        """Name + connection degree but no title line."""
        raw = "Jane Doe \n • 1st"
        name, title = self._parse(raw)
        assert name == "Jane Doe"
        assert title == ""

    def test_empty_string_returns_unknown(self):
        name, title = self._parse("")
        assert name == "Unknown"
        assert title == ""

    def test_whitespace_stripped_from_name(self):
        raw = "  Alice B. Cooper  \n • 3rd+\n\nRecruiter at FAANG\n\nRemote"
        name, title = self._parse(raw)
        assert name == "Alice B. Cooper"

    def test_hyphenated_name_preserved(self):
        raw = "Mary-Jane Watson \n • 3rd+\n\nUniversity Recruiter at Acme\n\nBoston, MA"
        name, title = self._parse(raw)
        assert name == "Mary-Jane Watson"

    def test_recruiting_keyword_in_title(self):
        """Title must contain a recruiting keyword for the recruiter to be selected."""
        recruiting_keywords = ["recruit", "talent", "hiring", "university", "campus", "hr", "people", "acquisition"]
        raw = "Bob Ross \n • 3rd+\n\nSenior Recruiter at Point72\n\nNew York"
        _, title = self._parse(raw)
        assert any(kw in title.lower() for kw in recruiting_keywords)

    def test_non_recruiting_title_detected(self):
        """Software engineers should NOT be flagged as recruiters."""
        recruiting_keywords = ["recruit", "talent", "hiring", "university", "campus", "hr", "people", "acquisition"]
        raw = "Alice Dev \n • 3rd+\n\nSoftware Engineer at Point72\n\nNew York"
        _, title = self._parse(raw)
        assert not any(kw in title.lower() for kw in recruiting_keywords)


# ══════════════════════════════════════════════════════════════════════════════
# linkedin_message_gen — message construction and character limit
# ══════════════════════════════════════════════════════════════════════════════

class TestMessageGeneration:
    """Business rules: first name only, ≤200 chars, ends with a question."""

    def _generate(self, candidate, recruiter_name: str, company: str, role: str,
                  question: str = "What qualities do you look for?") -> str:
        from app.outreach.linkedin_message_gen import generate_recruiter_message
        with patch("app.outreach.linkedin_message_gen.client", _mock_llm(question)):
            return generate_recruiter_message(candidate, recruiter_name, company, role)

    def test_message_starts_with_hello_first_name(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert msg.startswith("Hello Lily,")

    def test_message_does_not_contain_last_name(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert "Farriss" not in msg

    def test_message_contains_candidate_name(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert "Devon Lopez" in msg

    def test_message_contains_role(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert "Quant Intern" in msg

    def test_message_contains_company(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert "Point72" in msg

    def test_message_under_200_chars(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern")
        assert len(msg) <= 200

    def test_long_question_truncated_to_200(self, candidate):
        long_question = "X" * 300
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern",
                              question=long_question)
        assert len(msg) <= 200
        assert msg.endswith("...")

    def test_short_question_not_truncated(self, candidate):
        msg = self._generate(candidate, "Lily Farriss", "Point72", "Quant Intern",
                              question="What do you look for?")
        assert not msg.endswith("...")

    def test_single_name_recruiter(self, candidate):
        """Recruiter with no last name should still work."""
        msg = self._generate(candidate, "Beyonce", "Acme Corp", "SWE Intern")
        assert msg.startswith("Hello Beyonce,")

    def test_opening_line_format(self, candidate):
        msg = self._generate(candidate, "John Smith", "Stripe", "Backend Intern")
        expected_opening = (
            "Hello John, my name is Devon Lopez and I am excited "
            "to apply for the position of Backend Intern at Stripe. "
        )
        assert msg.startswith(expected_opening)

    def test_different_companies_produce_different_openings(self, candidate):
        msg_a = self._generate(candidate, "Alice R.", "Stripe", "SWE Intern")
        msg_b = self._generate(candidate, "Alice R.", "Robinhood", "SWE Intern")
        assert "Stripe" in msg_a
        assert "Robinhood" in msg_b
        assert msg_a != msg_b

    def test_very_long_role_still_under_200_chars(self, candidate):
        """Long role names must not push the message over 200 chars."""
        long_role = "Quantitative Researcher and Machine Learning Infrastructure Intern"
        msg = self._generate(candidate, "Lily Farriss", "Point72", long_role)
        assert len(msg) <= 200

    def test_empty_recruiter_name_does_not_crash(self, candidate):
        """An empty recruiter name string must not raise IndexError."""
        msg = self._generate(candidate, "", "Acme", "SWE Intern")
        assert isinstance(msg, str)
        assert len(msg) <= 200
