"""Career coach chatbot UI — main entry point.

Two tabs: "Career Chat" (upload CV -> edit parsed profile -> see matches) and
"Settings" (notification email/phone).

What is real and what is not:
  REAL   — CV upload/parsing (backend /upload), the editable profile form,
           notification settings (persisted to SQLite via /notifications/*),
           and the whole matching chain (backend /matching/pipeline: Qdrant
           retrieval, LLM re-ranking, and the Match Explanation Agent).
  MOCKED — only the chat's intent routing, which is keyword matching. It is
           marked in place; see `_route_message` below.

Run it (backend must be running separately):

    uvicorn backend.main:app --reload          # terminal 1
    streamlit run streamlit_app/chatbot_ui.py  # terminal 2
"""

import sys
import time
from pathlib import Path

import streamlit as st

# `streamlit run` adds this file's directory to sys.path implicitly, but other
# runners (tests, `python -m`) do not. Make it explicit so the sibling-module
# imports below work everywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_client  # noqa: E402
from pipeline_stub import (  # noqa: E402
    EXPLANATION_KEYS,
    MATCH_RESULT_KEYS,
    run_matching_pipeline,
)

st.set_page_config(page_title="AI Career Coach", page_icon="💼", layout="wide")

# --- session state ------------------------------------------------------------
# profile: the parsed-then-edited profile. matches: last pipeline output.
# chat: the visible message history, list of {"role", "content"}.
st.session_state.setdefault("profile", None)
st.session_state.setdefault("matches", None)
st.session_state.setdefault("chat", [])
# notification: last Trigger Now digest. None = never triggered, [] = triggered
# but nothing to recommend — the UI distinguishes the two.
st.session_state.setdefault("notification", None)


def _render_bullets(label: str, items) -> None:
    """Render one labelled list section, skipping it when empty.

    The explanation's list fields all default to empty in the real
    `MatchExplanation`, so a partially-populated response renders cleanly
    instead of showing empty headings.
    """
    if not items:
        return
    if isinstance(items, str):  # tolerate a single string where a list is expected
        items = [items]
    st.markdown(f"**{label}**")
    for item in items:
        st.markdown(f"- {item}")


def render_match_card(result: dict) -> None:
    """Render one match result.

    Reads exactly the keys in `MATCH_RESULT_KEYS`, with the nested
    `explanation` following `EXPLANATION_KEYS` — the same shape as the real
    `MatchExplanation`. If the pipeline's return shape changes, this function
    changes with it (see pipeline_stub.py).
    """
    explanation = result.get("explanation") or {}

    with st.container(border=True):
        st.subheader(result.get("job_title", "Untitled role"))
        st.caption(result.get("company", "Unknown company"))

        url = result.get("url")
        if url:
            # link_button rather than a markdown link: it is the primary action
            # on a match card and needs to be obvious, not buried in prose.
            st.link_button("🔗 Open job posting", url)
            st.caption(url)

        summary = explanation.get("overall_alignment_summary")
        if summary:
            st.markdown(summary)

        _render_bullets("✅ Strengths", explanation.get("strengths"))
        _render_bullets("⚠️ Gaps / missing requirements",
                        explanation.get("gaps_or_missing_requirements"))
        _render_bullets("💡 Recommendations", explanation.get("recommendations"))
        _render_bullets("➡️ Next steps", explanation.get("next_steps"))


def _as_list(value) -> list:
    """Coerce a profile field into a list (the parser may return either)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def _as_text(value) -> str:
    """Coerce a profile field into display text."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value)


# Chat appearance. The transcript is a fixed-height scroll area so the input
# box keeps its position no matter how long the conversation gets.
CHAT_HEIGHT = 380
USER_AVATAR = "🧑"
ASSISTANT_AVATAR = "💼"


# How many recommendations a triggered notification carries. A digest is a
# nudge, not a job board — three is enough to act on.
NOTIFICATION_RECOMMENDATION_LIMIT = 3


def build_notification_recommendations(matches: list, limit: int = None) -> list:
    """Reduce pipeline results to the lines a job-match digest would carry.

    This is the payload the notifications lane will eventually email or text.
    It is built from the *same* pipeline output the Career Chat renders, so a
    notification can never recommend something the app itself would not — one
    backend model, one set of results.

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


# Words that mean "run the matching pipeline". This is a placeholder for the
# intent-routing layer Fady owns — when that lands, replace `_route_message`
# wholesale rather than growing this list. Keeping it dumb and obvious is
# deliberate: it should not be mistaken for real intent classification.
_MATCH_INTENT_WORDS = ("match", "job", "find", "search", "opportunit", "role")


def _route_message(text: str) -> str:
    """Decide what a chat message should do, and return the reply.

    PLACEHOLDER routing — keyword matching, not intent classification. The real
    router is Fady's; this exists so the chat is usable in the meantime and so
    there is one obvious function to replace.
    """
    lowered = text.lower()

    if not any(word in lowered for word in _MATCH_INTENT_WORDS):
        return (
            "I can only do one thing so far: **find and rank job matches**.\n\n"
            "Try asking me to *find matching jobs*.\n\n"
            ":gray[I match on keywords for now, so I will miss anything phrased "
            "differently. General conversation is not wired up yet.]"
        )

    if st.session_state.profile is None:
        return (
            "I need your profile first. Upload a CV above, click **Parse CV**, "
            "then ask me again."
        )

    try:
        st.session_state.matches = run_matching_pipeline(st.session_state.profile)
    except api_client.BackendError as exc:
        return (
            f"I could not run the matching pipeline.\n\n"
            f":red[{exc}]\n\n"
            "Check that the backend is running and that the job collection has "
            "been seeded."
        )

    count = len(st.session_state.matches or [])
    if not count:
        return (
            "No matches came back. The job collection is probably empty. Run an "
            "ingestion from the dashboard, then ask me again."
        )
    return f"Found and ranked **{count}** match(es). They are below. 👇"


# --- header -------------------------------------------------------------------
st.title("💼 AI Career Coach")

backend_ok, backend_msg = api_client.health_check()
if not backend_ok:
    st.error(f"{backend_msg}\n\nStart it with: `uvicorn backend.main:app --reload`")
else:
    st.caption(f"Connected to {api_client.BASE_URL}")

chat_tab, settings_tab = st.tabs(["Career Chat", "Settings"])


# =============================== CAREER CHAT ==================================
with chat_tab:
    st.header("1. Upload your CV")
    uploaded = st.file_uploader(
        "PDF or DOCX", type=["pdf", "docx"],
        help="Sent to the backend's real /upload endpoint for parsing.",
    )

    if uploaded is not None and st.button("Parse CV", type="primary"):
        with st.spinner("Parsing your CV..."):
            try:
                profile = api_client.upload_cv(uploaded.name, uploaded.getvalue())
                st.session_state.profile = profile
                st.session_state.matches = None  # stale once the profile changes
                st.success("CV parsed. Review and edit below.")
            except api_client.BackendError as exc:
                st.error(str(exc))

    # --- chat ------------------------------------------------------------------
    # Sits above the profile form: it is the primary way to drive the app, and
    # the form below is for correcting what the parser got wrong.
    st.divider()
    st.header("2. Chat")
    st.caption(
        "Ask me to find matches. Retrieval, ranking and the written "
        "explanations are all real."
    )

    # Fixed-height scrollable transcript. Without it the block grows with every
    # message and pushes the input box down the page; with it the input stays
    # put and the history scrolls inside.
    transcript = st.container(height=CHAT_HEIGHT, border=False)
    with transcript:
        if not st.session_state.chat:
            st.chat_message("assistant", avatar=ASSISTANT_AVATAR).markdown(
                "Hi. Upload your CV above, then ask me to find matches."
            )
        for message in st.session_state.chat:
            avatar = (
                USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
            )
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

    prompt = st.chat_input("Ask me to find matching jobs")
    if prompt:
        # Append both turns, then rerun so the whole transcript renders from
        # state in one place. Rendering the new pair inline here instead would
        # draw it *below* the input widget, which is why the box appeared to
        # jump around between sends.
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.spinner("Working..."):
            reply = _route_message(prompt)
        st.session_state.chat.append({"role": "assistant", "content": reply})
        st.rerun()

    # --- 3. editable profile --------------------------------------------------
    if st.session_state.profile is not None:
        st.divider()
        st.header("3. Review your profile")
        st.caption(
            "The parser's output is a starting point. Correct anything it got "
            "wrong before confirming."
        )

        profile = st.session_state.profile
        with st.form("profile_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", value=_as_text(profile.get("name")))
                email = st.text_input("Email", value=_as_text(profile.get("email")))
            with col2:
                phone = st.text_input("Phone", value=_as_text(profile.get("phone")))
                title = st.text_input(
                    "Current / target title",
                    value=_as_text(profile.get("title") or profile.get("current_title")),
                )

            parsed_skills = _as_list(profile.get("skills"))
            skills = st.multiselect(
                "Skills",
                options=parsed_skills,
                default=parsed_skills,
                accept_new_options=True,
                help="Remove anything wrong, or type to add skills the parser missed.",
            )

            experience = st.text_area(
                "Experience", value=_as_text(profile.get("experience")), height=120
            )
            education = st.text_area(
                "Education", value=_as_text(profile.get("education")), height=80
            )

            confirmed = st.form_submit_button("Confirm & find matches", type="primary")

        if confirmed:
            st.session_state.profile = {
                "name": name,
                "email": email,
                "phone": phone,
                "title": title,
                "skills": skills,
                "experience": experience,
                "education": education,
            }
            with st.spinner("Finding matches..."):
                try:
                    st.session_state.matches = run_matching_pipeline(
                        st.session_state.profile
                    )
                except api_client.BackendError as exc:
                    st.session_state.matches = None
                    st.error(str(exc))

    # --- 4. results -----------------------------------------------------------
    if st.session_state.matches is not None:
        st.divider()
        st.header("4. Your matches")
        st.info(
            "The whole chain is real: CV parsing, Qdrant retrieval, LLM "
            "re-ranking, and the written explanations. A card shows a "
            "placeholder summary only if its posting is missing from the "
            "database, which means Qdrant and SQLite have drifted apart.",
            icon="🧪",
        )
        for result in st.session_state.matches:
            missing = [k for k in MATCH_RESULT_KEYS if k not in result]
            if missing:
                st.warning(f"Result is missing expected keys: {missing}")
            missing_expl = [
                k for k in EXPLANATION_KEYS
                if k not in (result.get("explanation") or {})
            ]
            if missing_expl:
                st.warning(f"Explanation is missing expected keys: {missing_expl}")
            render_match_card(result)


# ================================= SETTINGS ===================================
with settings_tab:
    st.header("Notification settings")
    st.caption(
        "Saved to the backend's SQLite database, so they survive a restart. "
        "Readable by the notifications lane at "
        "`GET /notifications/settings/{user_id}`."
    )

    existing = None
    if backend_ok:
        try:
            existing = api_client.get_notification_settings()
        except api_client.BackendError as exc:
            st.warning(str(exc))

    with st.form("settings_form"):
        settings_email = st.text_input(
            "Email", value=(existing or {}).get("email") or ""
        )
        settings_phone = st.text_input(
            "Phone", value=(existing or {}).get("phone") or ""
        )
        saved = st.form_submit_button("Save", type="primary")

    if saved:
        try:
            result = api_client.save_notification_settings(
                settings_email, settings_phone
            )
            st.success("Settings saved.")
            st.json(result)
        except api_client.BackendError as exc:
            st.error(str(exc))

    # --- Trigger Now ----------------------------------------------------------
    st.divider()
    st.header("Job match notification")
    st.caption(
        "Runs the same pipeline the Career Chat uses (Qdrant retrieval, then "
        "the LLM re-ranker) and shows the digest here. Nothing is emailed or "
        "texted; delivery belongs to the notifications lane."
    )
    st.caption(
        "Each trigger ingests fresh postings first, so the pool grows between "
        "runs. Results only change when the sources actually publish something "
        "new that outranks what you have already seen; this is not a shuffle."
    )
    ingest_limit = st.number_input(
        "Jobs to fetch per source", min_value=1, max_value=50, value=10,
        help="Higher values pull more postings into the pool per trigger.",
    )

    if st.button("🔔 Trigger Now", type="primary"):
        if st.session_state.profile is None:
            st.warning(
                "No profile yet. Upload a CV in the Career Chat tab and click "
                "**Parse CV** first. The digest is built from your profile."
            )
        else:
            try:
                # Ingest first, so the digest can surface postings that did not
                # exist last time rather than re-ranking a frozen pool.
                with st.spinner("Fetching new jobs..."):
                    run_id = api_client.trigger_ingestion(limit=int(ingest_limit))
                    run = api_client.wait_for_ingestion(run_id)

                inserted = run.get("jobs_inserted", 0)
                updated = run.get("jobs_updated", 0)
                if run.get("status") == "running":
                    st.info(
                        "Ingestion is still going; matching against what has "
                        "landed so far."
                    )
                elif run.get("error_message"):
                    # partial/failed still leaves earlier sources' jobs usable
                    st.warning(f"Some sources failed: {run['error_message']}")
                st.caption(
                    f"Ingestion run {run_id}: {inserted} new, {updated} updated, "
                    f"{run.get('jobs_embedded', 0)} embedded."
                )

                with st.spinner("Building your digest..."):
                    matches = run_matching_pipeline(st.session_state.profile)
                    st.session_state.matches = matches
                    st.session_state.notification = (
                        build_notification_recommendations(matches)
                    )
            except api_client.BackendError as exc:
                st.session_state.notification = None
                st.error(f"Could not build the digest: {exc}")

            recommendations = st.session_state.notification
            if recommendations:
                # The UI notification itself, plus a persistent copy below
                # since a toast disappears after a few seconds.
                st.toast(
                    f"{len(recommendations)} job recommendation(s) ready.",
                    icon="🔔",
                )
                st.success(
                    f"Your digest: {len(recommendations)} recommendation(s)."
                )
                for index, item in enumerate(recommendations, start=1):
                    with st.container(border=True):
                        st.markdown(f"**{index}. {item['job_title']}**")
                        st.caption(item["company"])
                        if item["url"]:
                            st.link_button("🔗 Open job posting", item["url"])
            elif recommendations is not None:
                st.info(
                    "No recommendations to send. The job collection may be "
                    "empty. Run an ingestion from the dashboard first."
                )
