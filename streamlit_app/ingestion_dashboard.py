"""Streamlit dashboard to trigger and monitor the ingestion pipeline.

A separate process from the FastAPI backend — it talks to it purely over HTTP.
Run it with:

    streamlit run streamlit_app/ingestion_dashboard.py

and make sure the backend is up (`uvicorn backend.main:app`). Defaults to
http://127.0.0.1:8000, overridable via BACKEND_HOST / BACKEND_PORT in .env.
"""

import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SOURCES = ["arbeitnow", "wuzzuf", "mock_mena"]


def backend_base_url() -> str:
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = os.getenv("BACKEND_PORT", "8000")
    # 0.0.0.0 is a bind-all address, not reliably connectable from a client;
    # translate it to loopback for outbound requests.
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


BASE_URL = backend_base_url()

st.set_page_config(page_title="Ingestion Dashboard", page_icon="📥", layout="wide")
st.title("📥 Job Ingestion Dashboard")
st.caption(f"Backend: {BASE_URL}")


# --- Trigger a run -----------------------------------------------------------
st.header("Run Ingestion")

with st.form("run_form"):
    selected_sources = st.multiselect(
        "Sources", options=SOURCES, default=SOURCES,
        help="Which ingestion clients to run. Leave all selected for a full pull.",
    )
    limit = st.number_input("Limit per source", min_value=1, max_value=100, value=10)
    submitted = st.form_submit_button("Run Ingestion")

if submitted:
    if not selected_sources:
        st.warning("Select at least one source.")
    else:
        try:
            resp = requests.post(
                f"{BASE_URL}/ingestion/run",
                json={"sources": selected_sources, "limit": int(limit)},
                timeout=10,
            )
            resp.raise_for_status()
            run_id = resp.json()["run_id"]
        except requests.RequestException as exc:
            st.error(f"Could not reach the backend at {BASE_URL}: {exc}")
        else:
            with st.status(f"Run #{run_id} started…", expanded=True) as status_box:
                final = None
                while True:
                    try:
                        run = requests.get(
                            f"{BASE_URL}/ingestion/runs/{run_id}", timeout=10
                        ).json()
                    except requests.RequestException as exc:
                        status_box.update(label=f"Polling failed: {exc}", state="error")
                        break

                    state = run.get("status")
                    status_box.update(
                        label=(
                            f"Run #{run_id}: {state} — "
                            f"fetched {run.get('jobs_fetched', 0)}, "
                            f"inserted {run.get('jobs_inserted', 0)}, "
                            f"updated {run.get('jobs_updated', 0)}, "
                            f"skipped {run.get('jobs_skipped', 0)}"
                        )
                    )
                    if state != "running":
                        final = run
                        break
                    time.sleep(1)

                if final is not None:
                    ok = final["status"] == "success"
                    status_box.update(
                        state="complete" if ok else "error",
                        label=f"Run #{run_id} finished: {final['status']}",
                    )
                    st.write(
                        {
                            "status": final["status"],
                            "jobs_fetched": final["jobs_fetched"],
                            "jobs_inserted": final["jobs_inserted"],
                            "jobs_updated": final["jobs_updated"],
                            "jobs_skipped": final["jobs_skipped"],
                        }
                    )
                    if final.get("error_message"):
                        st.warning(final["error_message"])


# --- Recent runs -------------------------------------------------------------
st.header("Recent Runs")
try:
    runs = requests.get(f"{BASE_URL}/ingestion/runs", timeout=10).json()
    if runs:
        st.dataframe(runs, width="stretch", hide_index=True)
    else:
        st.info("No runs yet — trigger one above.")
except requests.RequestException as exc:
    st.error(f"Could not load runs: {exc}")


# --- Persisted jobs ----------------------------------------------------------
st.header("Persisted Jobs")
col1, col2 = st.columns(2)
with col1:
    jobs_limit = st.number_input("Page size", min_value=1, max_value=200, value=50)
with col2:
    jobs_offset = st.number_input("Offset", min_value=0, value=0, step=int(jobs_limit))

try:
    jobs = requests.get(
        f"{BASE_URL}/ingestion/jobs",
        params={"limit": int(jobs_limit), "offset": int(jobs_offset)},
        timeout=10,
    ).json()
    if jobs:
        st.dataframe(jobs, width="stretch", hide_index=True)
        st.caption(f"Showing {len(jobs)} job(s) from offset {int(jobs_offset)}.")
    else:
        st.info("No persisted jobs on this page.")
except requests.RequestException as exc:
    st.error(f"Could not load jobs: {exc}")
