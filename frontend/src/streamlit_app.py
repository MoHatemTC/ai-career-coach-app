"""Streamlit entry point.

Run from the repo root:

    streamlit run frontend/src/streamlit_app.py

PRD 10.1 lists Streamlit/Flask as the v1 frontend (React is a stretch goal),
and there was no frontend in the repo at all when this lane started — so this
app is the shell the Notification Settings tab lives in. Additional pages drop
into frontend/src/pages/ and appear in the sidebar automatically.
"""

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes this file as a script, not as a package module, so the
# repo root is not on sys.path and `from src.api...` would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import client  # noqa: E402

st.set_page_config(
    page_title="Sprints Career Coach",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Sprints Career Coach")
st.caption("Your CV, matched against live job postings — every day, automatically.")

api_up = client.health()
if api_up:
    st.success(f"Connected to the API at {client.API_BASE_URL}")
else:
    st.error(
        f"Cannot reach the API at **{client.API_BASE_URL}**.\n\n"
        "Start it from the repo root with:\n\n"
        "```bash\nuvicorn backend.main:app --reload\n```"
    )

st.markdown(
    """
### Getting started

1. Open **Notification Settings** in the sidebar.
2. Enter your email and phone number, and choose your channels.
3. Use **Preview matches** to check what a digest would contain.
4. Hit **Send test digest** to confirm delivery works end to end.

Once the scheduler is enabled, your top 3 matches arrive automatically at your
chosen local time — no searching required.
"""
)

if api_up:
    left, right = st.columns(2)

    with left:
        st.subheader("Delivery channels")
        try:
            for provider in client.provider_status():
                icon = "✅" if provider["configured"] else "⚠️"
                state = "configured" if provider["configured"] else "not configured"
                st.write(f"{icon} **{provider['channel']}** via `{provider['name']}` — {state}")
        except client.ApiError as exc:
            st.warning(str(exc))

    with right:
        st.subheader("Scheduler")
        try:
            status = client.scheduler_status()
            if status.get("running"):
                st.write("🟢 Running")
                st.write(f"Next tick: `{status.get('next_run_at') or 'unknown'}`")
            else:
                st.write("⚪ Not running")
                st.caption(
                    "Enable it by setting `NOTIFICATIONS_SCHEDULER_ENABLED=true` "
                    "in `.env` and restarting the API."
                )
        except client.ApiError as exc:
            st.warning(str(exc))
