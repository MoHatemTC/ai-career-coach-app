"""Builds the job-match digest a notification would carry.

Deliberately free of Streamlit imports. It lives outside `chatbot_ui.py` so it
can be imported and tested directly: importing the UI script executes it in
"bare mode", which leaves Streamlit's container/form context dirty and breaks
any `AppTest` that runs afterwards.

This is the payload the notifications lane will eventually email or text. It is
derived from the *same* pipeline output the Career Chat renders, so a
notification can never recommend something the app itself would not.
"""

from typing import Any, Dict, List, Optional

# How many recommendations a triggered notification carries. A digest is a
# nudge, not a job board; three is enough to act on.
NOTIFICATION_RECOMMENDATION_LIMIT = 3


def build_notification_recommendations(
    matches: Optional[List[Dict[str, Any]]], limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Reduce pipeline results to the lines a job-match digest would carry.

    Nothing is sent from here; sending belongs to the notifications lane.
    """
    limit = NOTIFICATION_RECOMMENDATION_LIMIT if limit is None else limit
    lines = []
    for result in (matches or [])[:limit]:
        lines.append(
            {
                "job_title": result.get("job_title", "Untitled role"),
                "company": result.get("company", "Unknown company"),
                "url": result.get("url"),
            }
        )
    return lines
