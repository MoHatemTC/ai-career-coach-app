import pytest
from datetime import datetime, timezone, timedelta
from backend.services.ingestion import WuzzufScraperClient

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
