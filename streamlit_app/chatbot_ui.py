"""Career coach chatbot UI — main entry point.

Two tabs: "Career Chat" (upload CV -> edit parsed profile -> see matches) and
"Settings" (notification email/phone).

What is real and what is not:
  REAL   — CV upload/parsing (backend /upload), the editable profile form, and
           notification settings (persisted to SQLite via /notifications/*).
  MOCKED — the matching results, which come from
           `pipeline_stub.run_matching_pipeline`. See that file; it is the one
           function to replace when the real chain is ready.

Run it (backend must be running separately):

    uvicorn backend.main:app --reload          # terminal 1
    streamlit run streamlit_app/chatbot_ui.py  # terminal 2
"""

import sys
from pathlib import Path

import streamlit as st

# `streamlit run` adds this file's directory to sys.path implicitly, but other
# runners (tests, `python -m`) do not. Make it explicit so the sibling-module
# imports below work everywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_client  # noqa: E402
from pipeline_stub import MATCH_RESULT_KEYS, run_matching_pipeline  # noqa: E402

st.set_page_config(page_title="AI Career Coach", page_icon="💼", layout="wide")

# --- session state ------------------------------------------------------------
# profile: the parsed-then-edited profile. matches: last pipeline output.
st.session_state.setdefault("profile", None)
st.session_state.setdefault("matches", None)


def render_match_card(result: dict) -> None:
    """Render one match result.

    Reads exactly the keys in `MATCH_RESULT_KEYS` — if the pipeline's return
    shape changes, this function changes with it (see pipeline_stub.py).
    """
    with st.container(border=True):
        st.subheader(result.get("job_title", "Untitled role"))
        st.caption(result.get("company", "Unknown company"))
        st.markdown(f"**✅ Strength**  \n{result.get('strength', '—')}")
        st.markdown(f"**⚠️ Weakness**  \n{result.get('weakness', '—')}")
        st.markdown(f"**💡 Recommendation**  \n{result.get('recommendation', '—')}")


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
                st.success("CV parsed — review and edit below.")
            except api_client.BackendError as exc:
                st.error(str(exc))

    # --- 2. editable profile --------------------------------------------------
    if st.session_state.profile is not None:
        st.divider()
        st.header("2. Review your profile")
        st.caption(
            "The parser's output is a starting point — correct anything it got "
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
                st.session_state.matches = run_matching_pipeline(
                    st.session_state.profile
                )

    # --- 3. results -----------------------------------------------------------
    if st.session_state.matches is not None:
        st.divider()
        st.header("3. Your matches")
        st.info(
            "⚠️ These results are **mock data** — the matching chain "
            "(retrieval → ranking → explanations) is not wired up yet. "
            "The CV parsing above is real.",
            icon="🧪",
        )
        for result in st.session_state.matches:
            missing = [k for k in MATCH_RESULT_KEYS if k not in result]
            if missing:
                st.warning(f"Result is missing expected keys: {missing}")
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
