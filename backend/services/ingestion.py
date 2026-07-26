import abc
import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
import requests
import re
from bs4 import BeautifulSoup
from pydantic import ValidationError

from backend.models.job import JobPosting


def make_job_id(url: str) -> str:
    """Deterministic id for a posting, derived from its URL — the same
    posting always hashes to the same id across runs, so it is safe to
    use as a cache/deduplication key."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# Wuzzuf renders job-type, work-mode, seniority, and experience-range
# chips in the same div as real skills. These buckets classify each chip
# mechanically so only real skills reach JobPosting.skills — unmatched
# metadata strings would otherwise pollute downstream skill-frequency
# counts (skill-gap lane) as fake "unknown skills".
_JOB_TYPE_TAGS = {
    "full time", "part time", "freelance / project", "freelance",
    "internship", "shift based", "contract", "temporary",
}
_WORK_MODE_TAGS = {
    "on-site", "onsite", "remote", "hybrid", "work from home",
}
_CAREER_LEVEL_TAGS = {
    "entry level", "experienced", "manager", "senior management",
    "senior management/head", "c-level executive", "student",
    "fresh grad", "not specified",
}
# "5 - 10 Yrs of Exp", "10+ Yrs of Exp"
_EXPERIENCE_RE = re.compile(r'(\d+\s*-\s*\d+|\d+\s*\+)\s*yrs?', re.IGNORECASE)


def classify_wuzzuf_tag(tag: str) -> Tuple[str, str]:
    """Classify one raw Wuzzuf chip into ('job_type' | 'work_mode' |
    'career_level' | 'experience_years' | 'skill', cleaned_text) so the
    scraper can route it into the matching JobPosting field."""
    cleaned = tag.strip()
    normalized = " ".join(cleaned.lower().split())

    if normalized in _JOB_TYPE_TAGS:
        return "job_type", cleaned
    if normalized in _WORK_MODE_TAGS:
        return "work_mode", cleaned
    if normalized in _CAREER_LEVEL_TAGS:
        return "career_level", cleaned
    if _EXPERIENCE_RE.search(normalized):
        return "experience_years", cleaned
    return "skill", cleaned


class BaseJobIngestionClient(abc.ABC):
    @abc.abstractmethod
    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        pass

class ArbeitnowIngestionClient(BaseJobIngestionClient):
    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        response = requests.get(self.API_URL)
        response.raise_for_status()
        data = response.json()

        jobs = []
        for item in data.get("data", [])[:limit]:
            created_at = item.get("created_at")
            if created_at:
                date_val = datetime.fromtimestamp(created_at, tz=timezone.utc)
            else:
                date_val = datetime.now(timezone.utc)

            url = item.get("url", "")
            job_types = item.get("job_types") or []

            try:
                jobs.append(JobPosting(
                    job_id=make_job_id(url),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    skills=item.get("tags", []),
                    job_type=", ".join(job_types) if job_types else None,
                    work_mode="Remote" if item.get("remote") else None,
                    salary=None,
                    source="Arbeitnow",
                    url=url,
                    date=date_val
                ))
            except ValidationError as e:
                print(f"Skipping invalid Arbeitnow posting ({url}): {e}")
        return jobs

class WuzzufScraperClient(BaseJobIngestionClient):
    """
    WARNING: Wuzzuf has no public API. This scraper is approved for internal/testing use only
    and is not intended for published/production deployment in its current form to respect ToS.
    """
    # No query params: the previous "/search/jobs/?q=&a=hpb" redirected to
    # ?start=4 (page 5 of results); this resolves cleanly to page 1.
    SEARCH_URL = "https://wuzzuf.net/search/jobs"
    BASE_URL = "https://wuzzuf.net"
    TITLE_LINK_SELECTOR = 'h2 a[href^="/jobs/p/"]'
    # Wuzzuf job pages carry no JSON-LD (verified live 2026-07-16); the
    # description lives in <section> blocks whose <h2> heading text is
    # stable across deploys, unlike the hashed CSS class names.
    DESCRIPTION_SECTION_HEADINGS = ("Job Description", "Job Requirements")
    REQUEST_DELAY_SECONDS = 2  # politeness delay between page fetches

    def __init__(self, cache_file: str = "data/cache/wuzzuf_scraped.json",
                 fetch_descriptions: bool = True):
        self.cache_file = cache_file
        self.fetch_descriptions = fetch_descriptions
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _ensure_cache_dir(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def _load_cache(self, limit: int) -> Optional[List[JobPosting]]:
        if not os.path.exists(self.cache_file):
            return None
        with open(self.cache_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        try:
            return [JobPosting(**job) for job in cached_data[:limit]]
        except ValidationError:
            # Cache predates a schema change — ignore it and re-scrape.
            return None

    def _parse_relative_time(self, time_str: str) -> datetime:
        now = datetime.now(timezone.utc)
        time_str = time_str.lower().strip()
        match = re.search(r'(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago', time_str)
        result = now
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if unit == 'minute':
                result = now - timedelta(minutes=val)
            elif unit == 'hour':
                result = now - timedelta(hours=val)
            elif unit == 'day':
                result = now - timedelta(days=val)
            elif unit == 'week':
                result = now - timedelta(weeks=val)
            elif unit == 'month':
                result = now - timedelta(days=val*30)
            elif unit == 'year':
                result = now - timedelta(days=val*365)
        return result

    def _parse_job_description(self, html: str) -> Optional[str]:
        """Extract the real description text from a single job page.

        Anchors on the "Job Description" / "Job Requirements" <h2> headings
        and takes the text of the <section> that wraps each one — heading
        text is stable across deploys, unlike Wuzzuf's hashed CSS class
        names. Falls back to the page's meta description.
        """
        soup = BeautifulSoup(html, "html.parser")

        parts = []
        seen_containers = set()
        for heading in soup.find_all("h2"):
            label = heading.get_text(strip=True)
            if label not in self.DESCRIPTION_SECTION_HEADINGS:
                continue
            container = heading.find_parent("section") or heading.parent
            if container is None or id(container) in seen_containers:
                continue
            seen_containers.add(id(container))

            for tag in container.find_all(["style", "script"]):
                tag.decompose()
            heading.extract()
            text = container.get_text(" ", strip=True)
            if text:
                parts.append(f"{label}: {text}")

        if parts:
            return "\n\n".join(parts)

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _fetch_job_description(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            time.sleep(self.REQUEST_DELAY_SECONDS)
            return self._parse_job_description(response.text)
        except Exception as e:
            print(f"Fetching description failed for {url}: {e}")
            return None

    def _parse_search_results(self, html: str, limit: int) -> List[JobPosting]:
        """Parse the search-results page into JobPosting objects.

        Descriptions here are placeholders — get_jobs() replaces them with
        real page content when fetch_descriptions is enabled.
        """
        soup = BeautifulSoup(html, "html.parser")
        title_links = soup.select(self.TITLE_LINK_SELECTOR)

        jobs = []
        for title_link in title_links[:limit]:
            h2_elem = title_link.parent
            title = title_link.text.strip()
            url = title_link.get("href", "")

            if url and not url.startswith("http"):
                url = self.BASE_URL + url

            company_div = h2_elem.find_next_sibling("div")
            date_val = datetime.now(timezone.utc)
            if company_div:
                company_elem = company_div.find("a")
                company = company_elem.text.strip().replace("-", "").strip() if company_elem else "Unknown Company"

                location_elem = company_div.find("span")
                location = location_elem.text.strip() if location_elem else "Unknown Location"

                time_elem = company_div.find("div")
                if time_elem:
                    date_val = self._parse_relative_time(time_elem.text)
            else:
                company = "Unknown Company"
                location = "Unknown Location"

            skills = []
            job_type = None
            work_mode = None
            career_level = None
            experience_years = None
            skills_div = h2_elem.parent.find_next_sibling("div")
            if skills_div:
                for elem in skills_div.find_all(["a", "span"]):
                    text = elem.text.replace("·", "").strip(" -,\n")
                    if not text or len(text) <= 1:
                        continue

                    category, value = classify_wuzzuf_tag(text)
                    if category == "skill":
                        if value not in skills:
                            skills.append(value)
                    elif category == "job_type" and job_type is None:
                        job_type = value
                    elif category == "work_mode" and work_mode is None:
                        work_mode = value
                    elif category == "career_level" and career_level is None:
                        career_level = value
                    elif category == "experience_years" and experience_years is None:
                        experience_years = value

            try:
                jobs.append(JobPosting(
                    job_id=make_job_id(url),
                    title=title,
                    company=company,
                    location=location,
                    description=f"Job at {company} in {location}.",
                    skills=skills,
                    job_type=job_type,
                    work_mode=work_mode,
                    career_level=career_level,
                    experience_years=experience_years,
                    salary=None,
                    source="Wuzzuf-Scraper",
                    url=url,
                    date=date_val
                ))
            except ValidationError as e:
                print(f"Skipping invalid Wuzzuf posting ({url}): {e}")

        return jobs

    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        cached = self._load_cache(limit)
        if cached is not None:
            return cached

        jobs = []
        try:
            response = requests.get(self.SEARCH_URL, headers=self.headers)
            response.raise_for_status()

            jobs = self._parse_search_results(response.text, limit)

            time.sleep(self.REQUEST_DELAY_SECONDS)

            if self.fetch_descriptions:
                for job in jobs:
                    description = self._fetch_job_description(job.url)
                    if description:
                        job.description = description

            self._ensure_cache_dir()
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump([job.model_dump(mode="json") for job in jobs], f, indent=2)

        except Exception as e:
            print(f"Scraping failed: {e}")

        return jobs

class MockMenaIngestionClient(BaseJobIngestionClient):
    def __init__(self, fallback_file: str = "data/sample_jobs_mena.json"):
        self.fallback_file = fallback_file

    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        if not os.path.exists(self.fallback_file):
            return []

        with open(self.fallback_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            jobs = []
            for item in data[:limit]:
                date_str = item.get("date")
                try:
                    date_val = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else datetime.now(timezone.utc)
                except Exception:
                    date_val = datetime.now(timezone.utc)

                url = item.get("url", "")
                try:
                    jobs.append(JobPosting(
                        job_id=make_job_id(url),
                        title=item.get("title", ""),
                        company=item.get("company", ""),
                        location=item.get("location", ""),
                        description=item.get("description", ""),
                        skills=item.get("skills", []),
                        job_type=item.get("job_type"),
                        work_mode=item.get("work_mode"),
                        career_level=item.get("career_level"),
                        experience_years=item.get("experience_years"),
                        salary=item.get("salary"),
                        source="Mock-MENA",
                        url=url,
                        date=date_val
                    ))
                except ValidationError as e:
                    print(f"Skipping invalid mock posting ({url}): {e}")
            return jobs
