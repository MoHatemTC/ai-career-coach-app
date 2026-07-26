"""Notification Settings — the settings tab required by the task brief.

Three tabs:
  Contact & channels   email / phone / delivery preferences  (the deliverable)
  Preview matches      what tonight's digest would contain, without sending
  Delivery history     past attempts, for debugging "I never got it"

Note on identity: the app has no authentication yet, so the user is chosen
from a picker instead of taken from a session. When auth lands, replace
`_select_user()` with the signed-in user id — nothing else on this page needs
to change.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import client  # noqa: E402

st.set_page_config(page_title="Notification Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Notification Settings")

TIMEZONES = [
    "Africa/Cairo",
    "Africa/Casablanca",
    "Asia/Dubai",
    "Asia/Riyadh",
    "Europe/Berlin",
    "Europe/London",
    "America/New_York",
    "UTC",
]

NEW_USER_SENTINEL = "➕ Create a new user"


def _select_user() -> str | None:
    """Pick which user we are editing. Stand-in for authentication."""
    try:
        users = client.list_users()
    except client.ApiError as exc:
        st.error(str(exc))
        st.stop()

    options = [user["user_id"] for user in users] + [NEW_USER_SENTINEL]
    choice = st.sidebar.selectbox("User", options, key="selected_user")

    if choice == NEW_USER_SENTINEL:
        st.sidebar.markdown("---")
        with st.sidebar.form("create_user"):
            st.write("**Create a user**")
            new_id = st.text_input("User ID", placeholder="user_1")
            new_name = st.text_input("Full name", placeholder="Menna Hatem")
            if st.form_submit_button("Create"):
                if not new_id.strip():
                    st.sidebar.error("User ID is required.")
                else:
                    try:
                        client.create_user(
                            {"user_id": new_id.strip(), "full_name": new_name.strip()}
                        )
                        st.sidebar.success(f"Created {new_id}")
                        # Clear the widget key so the picker re-reads the list
                        # and lands on the new user.
                        st.session_state.pop("selected_user", None)
                        st.rerun()
                    except client.ApiError as exc:
                        st.sidebar.error(str(exc))
        return None

    return choice


user_id = _select_user()
if user_id is None:
    st.info("Create a user in the sidebar to configure notifications.")
    st.stop()

user = client.get_user(user_id)
if user is None:
    st.error(f"User {user_id} no longer exists.")
    st.stop()

settings = user["settings"]
profile = user["profile"]

st.caption(f"Editing **{user.get('full_name') or user_id}** (`{user_id}`)")

tab_contact, tab_preview, tab_history = st.tabs(
    ["Contact & channels", "Preview matches", "Delivery history"]
)


# --- Tab 1: contact & channels ---------------------------------------------

with tab_contact:
    with st.form("notification_settings"):
        st.subheader("Where should we reach you?")

        col_email, col_phone = st.columns(2)
        with col_email:
            email = st.text_input(
                "Email address",
                value=settings.get("email") or "",
                placeholder="you@example.com",
            )
        with col_phone:
            phone = st.text_input(
                "Phone number (WhatsApp)",
                value=settings.get("phone") or "",
                placeholder="+20 100 123 4567",
                help="International format. Saved as E.164, e.g. +201001234567.",
            )

        st.divider()
        st.subheader("Channels")

        enabled = st.toggle(
            "Send me daily job matches",
            value=settings.get("notifications_enabled", True),
            help="Turn this off to pause all notifications without losing your settings.",
        )

        col_wa, col_mail = st.columns(2)
        with col_wa:
            notify_whatsapp = st.checkbox(
                "WhatsApp (preferred)",
                value=settings.get("notify_via_whatsapp", True),
            )
        with col_mail:
            notify_email = st.checkbox(
                "Email (fallback)",
                value=settings.get("notify_via_email", True),
            )
        st.caption(
            "WhatsApp is tried first. If it is unavailable or fails, the digest "
            "is sent by email instead — you will not get both."
        )

        st.divider()
        st.subheader("Timing & relevance")

        col_hour, col_tz, col_score = st.columns(3)
        with col_hour:
            send_hour = st.number_input(
                "Send at (local hour)",
                min_value=0,
                max_value=23,
                value=int(settings.get("send_hour_local", 8)),
            )
        with col_tz:
            current_tz = settings.get("timezone", "Africa/Cairo")
            tz_options = TIMEZONES if current_tz in TIMEZONES else [current_tz] + TIMEZONES
            timezone = st.selectbox(
                "Timezone", tz_options, index=tz_options.index(current_tz)
            )
        with col_score:
            min_score = st.slider(
                "Minimum match score",
                min_value=0.0,
                max_value=100.0,
                value=float(settings.get("min_match_score", 40.0)),
                step=5.0,
                help="Jobs scoring below this are not sent. Raise it if the digest feels noisy.",
            )

        if st.form_submit_button("Save settings", type="primary"):
            patch = {
                # Empty string would fail EmailStr validation; null clears it.
                "email": email.strip() or None,
                "phone": phone.strip() or None,
                "notifications_enabled": enabled,
                "notify_via_whatsapp": notify_whatsapp,
                "notify_via_email": notify_email,
                "send_hour_local": int(send_hour),
                "timezone": timezone,
                "min_match_score": float(min_score),
            }
            try:
                client.update_settings(user_id, patch)
                st.success("Settings saved.")
                st.rerun()
            except client.ApiError as exc:
                st.error(str(exc))

    # Warn about the combination that silently produces nothing: notifications
    # on, but no reachable address on any enabled channel.
    reachable = (
        settings.get("notifications_enabled")
        and (
            (settings.get("notify_via_whatsapp") and settings.get("phone"))
            or (settings.get("notify_via_email") and settings.get("email"))
        )
    )
    if settings.get("notifications_enabled") and not reachable:
        st.warning(
            "Notifications are on, but no enabled channel has an address. "
            "Add a phone number or an email above, or you will not receive anything."
        )

    st.divider()
    st.subheader("Matching profile")
    if not profile.get("skills"):
        st.warning(
            "This user has no skills stored, so every job scores 0 and no digest "
            "will ever be sent. Upload a CV, or add skills below."
        )

    with st.expander("Edit matching profile", expanded=not profile.get("skills")):
        with st.form("profile_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                current_title = st.text_input(
                    "Current title", value=profile.get("current_title", "")
                )
                location = st.text_input("Location", value=profile.get("location", ""))
                experience_years = st.number_input(
                    "Years of experience",
                    min_value=0,
                    max_value=60,
                    value=int(profile.get("experience_years", 0)),
                )
            with col_b:
                preferred_work_type = st.text_input(
                    "Preferred work type",
                    value=profile.get("preferred_work_type", ""),
                    placeholder="Full-time / Remote",
                )
                salary_expectation = st.number_input(
                    "Salary expectation",
                    min_value=0,
                    value=int(profile.get("salary_expectation", 0)),
                    step=1000,
                )

            skills_raw = st.text_input(
                "Skills (comma separated)",
                value=", ".join(profile.get("skills", [])),
                placeholder="python, fastapi, sql",
            )
            summary = st.text_area("Summary", value=profile.get("summary", ""), height=90)

            if st.form_submit_button("Save profile"):
                try:
                    client.update_profile(
                        user_id,
                        {
                            "current_title": current_title,
                            "skills": [s.strip() for s in skills_raw.split(",") if s.strip()],
                            "experience_years": int(experience_years),
                            "summary": summary,
                            "location": location,
                            "preferred_work_type": preferred_work_type,
                            "salary_expectation": int(salary_expectation),
                        },
                    )
                    st.success("Profile saved.")
                    st.rerun()
                except client.ApiError as exc:
                    st.error(str(exc))


# --- Tab 2: preview --------------------------------------------------------

with tab_preview:
    st.subheader("What tonight's digest would contain")
    st.caption(
        "Runs the real matching pipeline against your stored profile. "
        "Nothing is sent."
    )

    if st.button("Refresh preview"):
        st.rerun()

    try:
        matches = client.preview_matches(user_id, top_n=3, include_recent=True)
    except client.ApiError as exc:
        st.error(str(exc))
        matches = []

    if not matches:
        st.info(
            "No jobs currently clear your minimum match score. "
            "Try lowering the threshold, adding skills to your profile, or "
            "ingesting more job postings."
        )
    else:
        for index, match in enumerate(matches, start=1):
            job = match["job"]
            with st.container(border=True):
                header, score = st.columns([4, 1])
                with header:
                    st.markdown(f"**{index}. {job['title']}**")
                    location = f" · {job['location']}" if job.get("location") else ""
                    st.caption(f"{job['company']}{location}")
                with score:
                    st.metric("Match", f"{match['match_score']:.0f}%")

                chips = [
                    value
                    for value in (
                        job.get("work_mode"),
                        job.get("job_type"),
                        job.get("experience_years"),
                    )
                    if value
                ]
                if chips:
                    st.caption(" · ".join(chips))
                if match.get("reason"):
                    st.info(match["reason"])
                if job.get("skills"):
                    st.caption("Skills: " + ", ".join(job["skills"][:8]))
                st.link_button("View job", job["url"])

    st.divider()
    st.subheader("Test delivery")
    st.caption(
        "Sends this digest now, ignoring the once-per-day limit, so you can "
        "confirm your contact details work."
    )

    col_dry, col_real = st.columns(2)
    with col_dry:
        if st.button("Dry run (render only)"):
            try:
                result = client.send_test(user_id, dry_run=True)
                st.success(f"Outcome: `{result['outcome']}` — nothing transmitted.")
            except client.ApiError as exc:
                st.error(str(exc))

    with col_real:
        if st.button("Send test digest", type="primary"):
            try:
                result = client.send_test(user_id, dry_run=False)
                outcome = result["outcome"]
                if outcome == "notified":
                    for delivery in result["results"]:
                        if delivery["success"]:
                            st.success(
                                f"Sent via **{delivery['channel']}** "
                                f"(`{delivery['provider']}`)."
                            )
                elif outcome == "no_matches":
                    st.warning("Nothing above your score threshold, so nothing was sent.")
                elif outcome == "no_contact":
                    st.warning("No enabled channel has an address. Add one above.")
                else:
                    st.error(f"Delivery failed: `{outcome}`")
                    for delivery in result["results"]:
                        if not delivery["success"]:
                            st.error(
                                f"{delivery['channel']} / {delivery['provider']}: "
                                f"{delivery['error']}"
                            )
            except client.ApiError as exc:
                st.error(str(exc))


# --- Tab 3: history --------------------------------------------------------

with tab_history:
    st.subheader("Recent delivery attempts")
    try:
        logs = client.recent_logs(user_id=user_id, limit=25)
    except client.ApiError as exc:
        st.error(str(exc))
        logs = []

    if not logs:
        st.info("Nothing sent yet.")
    else:
        st.dataframe(
            [
                {
                    "Date": log["sent_on_local_date"],
                    "Channel": log["channel"],
                    "Provider": log["provider"] or "—",
                    "Status": log["status"],
                    "Jobs": len(log["job_ids"]),
                    "Error": log["error_message"] or "",
                }
                for log in logs
            ],
            use_container_width=True,
            hide_index=True,
        )
