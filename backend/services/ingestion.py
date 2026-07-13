import abc
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List
import requests
import re
from bs4 import BeautifulSoup

from backend.models.job import JobPosting

class BaseJobIngestionClient(abc.ABC):
    @abc.abstractmethod
    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        pass

class ArbeitnowIngestionClient(BaseJobIngestionClient):
    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        url = "https://www.arbeitnow.com/api/job-board-api"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        jobs = []
        for item in data.get("data", [])[:limit]:
            created_at = item.get("created_at")
            if created_at:
                date_val = datetime.fromtimestamp(created_at, tz=timezone.utc)
            else:
                date_val = datetime.now(timezone.utc)
            
            jobs.append(JobPosting(
                title=item.get("title", ""),
                company=item.get("company_name", ""),
                location=item.get("location", ""),
                description=item.get("description", ""),
                skills=item.get("tags", []),
                salary=None, 
                source="Arbeitnow",
                url=item.get("url", ""),
                date=date_val
            ))
        return jobs

class WuzzufScraperClient(BaseJobIngestionClient):
    """
    WARNING: Wuzzuf has no public API. This scraper is approved for internal/testing use only 
    and is not intended for published/production deployment in its current form to respect ToS.
    """
    def __init__(self, cache_file: str = "data/cache/wuzzuf_scraped.json"):
        self.cache_file = cache_file
        self.base_url = "https://wuzzuf.net/search/jobs/?q=&a=hpb"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _ensure_cache_dir(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

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

    def get_jobs(self, limit: int = 10) -> List[JobPosting]:
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                return [JobPosting(**job) for job in cached_data[:limit]]

        jobs = []
        try:
            response = requests.get(self.base_url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            title_links = soup.select('h2 a[href^="/jobs/p/"]')
            
            for title_link in title_links[:limit]:
                h2_elem = title_link.parent
                title = title_link.text.strip()
                url = title_link.get("href", "")
                
                if url and not url.startswith("http"):
                    url = "https://wuzzuf.net" + url
                
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
                skills_div = h2_elem.parent.find_next_sibling("div")
                if skills_div:
                    for elem in skills_div.find_all(["a", "span"]):
                        text = elem.text.replace("", "").replace("\u00b7", "").strip(" -,\n")
                        if text and len(text) > 1 and text not in skills:
                            skills.append(text)
                            
                jobs.append(JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    description=f"Job at {company} in {location}.",
                    skills=skills,
                    salary=None,
                    source="Wuzzuf-Scraper",
                    url=url,
                    date=date_val
                ))
            
            self._ensure_cache_dir()
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump([job.model_dump(mode="json") for job in jobs], f, indent=2)
                
            time.sleep(2) # Politeness delay
            
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
                    
                jobs.append(JobPosting(
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    skills=item.get("skills", []),
                    salary=item.get("salary"),
                    source="Mock-MENA",
                    url=item.get("url", ""),
                    date=date_val
                ))
            return jobs
