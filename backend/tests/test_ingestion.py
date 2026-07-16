import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models.job import JobPosting
from backend.services.ingestion import (
    WuzzufScraperClient,
    classify_wuzzuf_tag,
    make_job_id,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_parse_relative_time():
    client = WuzzufScraperClient()

    test_cases = [
        ("1 minute ago", timedelta(minutes=1)),
        ("5 minutes ago", timedelta(minutes=5)),
        ("1 hour ago", timedelta(hours=1)),
        ("3 hours ago", timedelta(hours=3)),
        ("1 day ago", timedelta(days=1)),
        ("2 days ago", timedelta(days=2)),
        ("1 week ago", timedelta(weeks=1)),
        ("3 weeks ago", timedelta(weeks=3)),
        ("1 month ago", timedelta(days=30)),
        ("6 months ago", timedelta(days=180)),
        ("1 year ago", timedelta(days=365)),
        ("2 years ago", timedelta(days=730)),
        ("Just now", timedelta(0)),
        ("invalid string", timedelta(0))
    ]

    for time_str, expected_delta in test_cases:
        before = datetime.now(timezone.utc)
        result = client._parse_relative_time(time_str)
        after = datetime.now(timezone.utc)

        expected_min = before - expected_delta
        expected_max = after - expected_delta

        assert expected_min <= result <= expected_max, \
            f"Failed for '{time_str}'. Expected between {expected_min} and {expected_max}, got {result}"


def test_classify_wuzzuf_tag_job_type():
    assert classify_wuzzuf_tag("Full Time") == ("job_type", "Full Time")
    assert classify_wuzzuf_tag("Part Time") == ("job_type", "Part Time")
    assert classify_wuzzuf_tag("Freelance / Project") == ("job_type", "Freelance / Project")


def test_classify_wuzzuf_tag_work_mode():
    assert classify_wuzzuf_tag("On-site") == ("work_mode", "On-site")
    assert classify_wuzzuf_tag("Remote") == ("work_mode", "Remote")
    assert classify_wuzzuf_tag("Hybrid") == ("work_mode", "Hybrid")


def test_classify_wuzzuf_tag_career_level():
    assert classify_wuzzuf_tag("Entry Level") == ("career_level", "Entry Level")
    assert classify_wuzzuf_tag("Experienced") == ("career_level", "Experienced")
    assert classify_wuzzuf_tag("Manager") == ("career_level", "Manager")


def test_classify_wuzzuf_tag_experience_years():
    assert classify_wuzzuf_tag("5 - 10 Yrs of Exp") == ("experience_years", "5 - 10 Yrs of Exp")
    assert classify_wuzzuf_tag("1 - 3 Yrs of Exp") == ("experience_years", "1 - 3 Yrs of Exp")
    assert classify_wuzzuf_tag("10+ Yrs of Exp") == ("experience_years", "10+ Yrs of Exp")


def test_classify_wuzzuf_tag_real_skills_pass_through():
    assert classify_wuzzuf_tag("Python") == ("skill", "Python")
    assert classify_wuzzuf_tag("React.js") == ("skill", "React.js")
    assert classify_wuzzuf_tag("Content Marketing") == ("skill", "Content Marketing")


def test_make_job_id_deterministic_sha256_of_url():
    url = "https://wuzzuf.net/jobs/p/example"
    expected = hashlib.sha256(url.encode()).hexdigest()[:16]
    assert make_job_id(url) == expected
    assert make_job_id(url) == make_job_id(url)
    assert make_job_id(url) != make_job_id(url + "-other")


def _valid_posting_kwargs(**overrides):
    kwargs = dict(
        job_id=make_job_id("https://example.com/job/1"),
        title="Backend Engineer",
        company="Acme",
        location="Cairo, Egypt",
        description="A job.",
        skills=["Python"],
        source="Test",
        url="https://example.com/job/1",
        date=datetime.now(timezone.utc),
    )
    kwargs.update(overrides)
    return kwargs


def test_jobposting_rejects_blank_title_and_company():
    with pytest.raises(ValidationError):
        JobPosting(**_valid_posting_kwargs(title="   "))
    with pytest.raises(ValidationError):
        JobPosting(**_valid_posting_kwargs(company=""))


def test_jobposting_rejects_non_http_url():
    with pytest.raises(ValidationError):
        JobPosting(**_valid_posting_kwargs(url="ftp://example.com/job"))
    with pytest.raises(ValidationError):
        JobPosting(**_valid_posting_kwargs(url="/jobs/p/relative-only"))


def test_parse_search_results_splits_metadata_out_of_skills():
    client = WuzzufScraperClient(fetch_descriptions=False)
    html = load_fixture("wuzzuf_search_results.html")

    jobs = client._parse_search_results(html, limit=10)

    assert len(jobs) == 2

    first = jobs[0]
    assert first.title == "Senior Python Developer"
    assert first.company == "TechCorp"
    assert first.location == "Cairo, Egypt"
    assert first.url == "https://wuzzuf.net/jobs/p/111-senior-python-developer-cairo"
    assert first.job_id == make_job_id(first.url)
    assert first.skills == ["Python", "Django", "PostgreSQL"]
    assert first.job_type == "Full Time"
    assert first.work_mode == "On-site"
    assert first.career_level == "Experienced"
    assert first.experience_years == "5 - 10 Yrs of Exp"

    second = jobs[1]
    assert second.skills == ["SEO", "Content Marketing"]
    assert second.job_type == "Part Time"
    assert second.work_mode == "Remote"
    assert second.career_level == "Manager"
    assert second.experience_years == "10+ Yrs of Exp"


def test_parse_search_results_respects_limit():
    client = WuzzufScraperClient(fetch_descriptions=False)
    html = load_fixture("wuzzuf_search_results.html")

    jobs = client._parse_search_results(html, limit=1)

    assert len(jobs) == 1
    assert jobs[0].title == "Senior Python Developer"


def test_parse_job_description_extracts_heading_anchored_sections():
    client = WuzzufScraperClient(fetch_descriptions=False)
    html = load_fixture("wuzzuf_job_page.html")

    description = client._parse_job_description(html)

    assert description is not None
    assert "ingestion pipeline" in description          # Job Description section
    assert "Django and PostgreSQL" in description       # Job Requirements section
    assert "font-size" not in description               # inline <style> stripped
    assert "Similar Jobs" not in description            # unrelated sections excluded
    assert "Apply for a Senior Python Developer" not in description  # meta not used
    assert "<p>" not in description                     # HTML stripped


def test_parse_job_description_falls_back_to_meta():
    client = WuzzufScraperClient(fetch_descriptions=False)
    html = (
        '<html><head>'
        '<meta name="description" content="Meta fallback description for the job.">'
        '</head><body></body></html>'
    )

    assert client._parse_job_description(html) == "Meta fallback description for the job."


def test_parse_job_description_returns_none_when_nothing_found():
    client = WuzzufScraperClient(fetch_descriptions=False)

    assert client._parse_job_description("<html><body>nothing here</body></html>") is None
