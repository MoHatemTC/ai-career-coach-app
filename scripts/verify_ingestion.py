"""Manual verification for the ingestion clients.

Pulls a few postings from each source and prints every `JobPosting` field so a
reviewer can eyeball that all fields populate correctly across sources. Live
sources (Arbeitnow, Wuzzuf) hit the network and may fail offline — that is
reported per source rather than crashing the whole script; the offline
Mock-MENA source always works.

Run from the repo root:

    python scripts/verify_ingestion.py
"""

import sys
from pathlib import Path

# Running `python scripts/verify_ingestion.py` puts scripts/ on sys.path, not
# the repo root, so `import backend...` would fail. Add the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.ingestion import (  # noqa: E402
    ArbeitnowIngestionClient,
    MockMenaIngestionClient,
    WuzzufScraperClient,
)

CLIENTS = {
    "Arbeitnow": ArbeitnowIngestionClient,
    "Wuzzuf": WuzzufScraperClient,
    "Mock-MENA": MockMenaIngestionClient,
}

# Every field on the JobPosting schema, so nothing silently goes unchecked.
FIELDS = [
    "job_id", "title", "company", "location", "description", "skills",
    "job_type", "work_mode", "career_level", "experience_years",
    "salary", "source", "url", "date",
]


def verify(name: str, client_cls, limit: int = 3) -> None:
    print("=" * 70)
    print(f"SOURCE: {name}")
    print("=" * 70)
    try:
        jobs = client_cls().get_jobs(limit=limit)
    except Exception as exc:  # noqa: BLE001 - report and continue to next source
        print(f"  FAILED to fetch: {exc}\n")
        return

    if not jobs:
        print("  (no jobs returned)\n")
        return

    for i, job in enumerate(jobs, 1):
        print(f"\n  --- job {i}/{len(jobs)} ---")
        for field in FIELDS:
            value = getattr(job, field)
            if field == "description" and isinstance(value, str) and len(value) > 100:
                value = value[:100] + "…"
            print(f"    {field:17}: {value}")
    print()


def main() -> None:
    for name, client_cls in CLIENTS.items():
        verify(name, client_cls)


if __name__ == "__main__":
    main()
