"""Tests for the daily top-3 job match notification lane.

Covers the two things the task brief calls out as the success standard:
"tested for both contact settings configuration and automated notification
dispatch."

The matching *scorer* is stubbed throughout. It builds a SentenceTransformer
at import and downloads ~90MB of weights, which does not belong in a unit
test — and what needs testing here is the selection, threshold, fallback, and
idempotency logic around the score, not the embedding maths itself.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.features.notifications import dispatcher, matching_bridge, settings_service
from backend.features.notifications.providers.base import NotificationProvider
from backend.features.notifications.renderer import (
    render_email_html,
    render_email_subject,
    render_email_text,
    render_whatsapp_text,
)
from backend.features.notifications.schema import (
    DeliveryResult,
    DigestPayload,
    TopJobMatch,
)
from backend.models.db_models import JobPostingORM, NotificationLogORM
from backend.models.user import (
    NotificationSettings,
    NotificationSettingsUpdate,
    ProfileSnapshot,
    UserCreate,
    normalize_phone,
)
from backend.services.database import Base


@pytest.fixture
def db():
    """Isolated in-memory database per test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_jobs(db):
    now = datetime.now(timezone.utc)
    for index in range(5):
        db.add(
            JobPostingORM(
                job_id=f"job_{index}",
                title=f"Python Developer {index}",
                company="Tech Solutions",
                required_skills=["python", "fastapi"],
                skills=["python", "fastapi"],
                min_experience=1,
                description="Great role",
                location="Cairo",
                work_type="Full-time",
                salary=15000,
                source="test",
                url=f"https://jobs.example.com/{index}",
                date=now - timedelta(hours=index),
            )
        )
    db.commit()
    return db


def make_user(db, user_id="user_1", **settings_overrides):
    # Defaults first so a caller can override email/phone (including to None)
    # without colliding with a hardcoded keyword.
    settings_kwargs = {
        "email": "candidate@example.com",
        "phone": "+201001234567",
        **settings_overrides,
    }
    settings = NotificationSettings(**settings_kwargs)
    return settings_service.upsert_user(
        db,
        UserCreate(
            user_id=user_id,
            full_name="Menna Hatem",
            settings=settings,
            profile=ProfileSnapshot(
                current_title="Backend Developer",
                skills=["python", "fastapi"],
                experience_years=2,
                location="Cairo",
            ),
        ),
    )


@pytest.fixture
def fixed_scores(monkeypatch):
    """Deterministic descending scores: job_0 -> 90, job_1 -> 80, ..."""

    def fake_score(profile, job):
        index = int(job.job_id.split("_")[1])
        return 90.0 - (index * 10)

    monkeypatch.setattr(matching_bridge, "_score_fn", lambda: fake_score)
    return fake_score


# --- Contact settings configuration ----------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+201001234567", "+201001234567"),
        ("+20 (100) 123-4567", "+201001234567"),
        ("00201001234567", "+201001234567"),
        ("  ", None),
        (None, None),
    ],
)
def test_normalize_phone_accepts_common_formats(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("bad", ["12345", "+1234567890123456789"])
def test_normalize_phone_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        normalize_phone(bad)


def test_settings_roundtrip(db):
    user = make_user(db)
    assert user.settings.email == "candidate@example.com"
    assert user.settings.phone == "+201001234567"

    fetched = settings_service.get_user(db, "user_1")
    assert fetched is not None
    assert fetched.profile.skills == ["python", "fastapi"]


def test_patch_only_touches_supplied_fields(db):
    make_user(db)

    updated = settings_service.update_settings(
        db, "user_1", NotificationSettingsUpdate(min_match_score=75.0)
    )

    assert updated.settings.min_match_score == 75.0
    # Untouched fields must survive a partial update.
    assert updated.settings.email == "candidate@example.com"
    assert updated.settings.phone == "+201001234567"


def test_patch_can_explicitly_clear_a_field(db):
    make_user(db)
    updated = settings_service.update_settings(
        db, "user_1", NotificationSettingsUpdate.model_validate({"phone": None})
    )
    assert updated.settings.phone is None


def test_invalid_timezone_is_rejected():
    with pytest.raises(ValueError):
        NotificationSettings(timezone="Mars/Olympus_Mons")


def test_invalid_timezone_is_rejected_on_partial_update_too():
    """Regression: the PATCH model validated phone but not timezone.

    A bad timezone passed validation, was written to the row, and then raised
    on every subsequent read of that user — a bad form value became a
    permanent 500 on their settings page.
    """
    with pytest.raises(ValueError):
        NotificationSettingsUpdate(timezone="Mars/Base")


def test_is_reachable_requires_address_on_an_enabled_channel(db):
    user = make_user(db, notify_via_whatsapp=False, notify_via_email=False)
    assert user.is_reachable() is False

    user = make_user(db, "user_2", phone=None, email=None)
    assert user.is_reachable() is False

    assert make_user(db, "user_3").is_reachable() is True


def test_disabled_user_is_not_notifiable(db):
    make_user(db, notifications_enabled=False)
    assert settings_service.list_notifiable_users(db) == []


# --- Matching pipeline integration -----------------------------------------


def test_returns_exactly_top_three_highest_scoring(db, seeded_jobs, fixed_scores):
    user = make_user(db, min_match_score=0.0)

    matches = matching_bridge.get_top_matches(db, user, top_n=3)

    assert [m.job.job_id for m in matches] == ["job_0", "job_1", "job_2"]
    assert [m.match_score for m in matches] == [90.0, 80.0, 70.0]


def test_threshold_filters_low_scores(db, seeded_jobs, fixed_scores):
    user = make_user(db, min_match_score=75.0)
    matches = matching_bridge.get_top_matches(db, user, top_n=3)
    assert [m.job.job_id for m in matches] == ["job_0", "job_1"]


def test_matches_use_the_canonical_job_schema(db, seeded_jobs, fixed_scores):
    """The digest payload must carry backend/models/job.py, not job_posting.py."""
    user = make_user(db, min_match_score=0.0)
    job = matching_bridge.get_top_matches(db, user, top_n=1)[0].job

    assert job.skills == ["python", "fastapi"]  # canonical field name
    assert job.url.startswith("https://")
    assert job.source == "test"
    assert not hasattr(job, "required_skills")


def test_previously_sent_jobs_are_excluded(db, seeded_jobs, fixed_scores):
    user = make_user(db, min_match_score=0.0)
    db.add(
        NotificationLogORM(
            user_id="user_1",
            channel="email",
            status="sent",
            job_ids=["job_0", "job_1"],
            sent_on_local_date="2026-07-01",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    excluded = matching_bridge.recently_notified_job_ids(db, "user_1")
    matches = matching_bridge.get_top_matches(db, user, top_n=3, exclude_job_ids=excluded)

    assert [m.job.job_id for m in matches] == ["job_2", "job_3", "job_4"]


def test_dedupe_window_expires(db, seeded_jobs):
    db.add(
        NotificationLogORM(
            user_id="user_1",
            channel="email",
            status="sent",
            job_ids=["job_0"],
            sent_on_local_date="2026-01-01",
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
    )
    db.commit()
    assert matching_bridge.recently_notified_job_ids(db, "user_1", window_days=7) == set()


def test_row_without_url_is_skipped_when_no_fallback(db, fixed_scores):
    """A job with no link is useless in a digest — it must not be sent."""
    db.add(
        JobPostingORM(
            job_id="job_0",
            title="No URL Role",
            company="Acme",
            required_skills=["python"],
            date=datetime.now(timezone.utc),
        )
    )
    db.commit()
    user = make_user(db, min_match_score=0.0)

    assert matching_bridge.get_top_matches(db, user) == []

    with_fallback = matching_bridge.get_top_matches(
        db, user, app_base_url="https://coach.example.com"
    )
    assert with_fallback[0].job.url == "https://coach.example.com/jobs/job_0"


# --- Rendering --------------------------------------------------------------


@pytest.fixture
def payload(db, seeded_jobs, fixed_scores):
    user = make_user(db, min_match_score=0.0)
    return DigestPayload(
        user_id="user_1",
        full_name="Menna Hatem",
        matches=matching_bridge.get_top_matches(db, user, top_n=3),
        generated_at=datetime.now(timezone.utc),
    )


def test_email_renders_every_match_with_a_link(payload):
    html = render_email_html(payload, "https://coach.example.com")
    for match in payload.matches:
        assert match.job.title in html
        assert match.job.url in html
    assert "https://coach.example.com/settings" in html


def test_plain_text_alternative_is_populated(payload):
    text = render_email_text(payload)
    assert "Menna Hatem" in text
    assert payload.matches[0].job.title in text


def test_whatsapp_body_is_short_enough_to_avoid_truncation(payload):
    body = render_whatsapp_text(payload)
    assert payload.matches[0].job.url in body
    # WhatsApp folds long bodies behind "Read more", hiding the links.
    assert len(body) < 1024


def test_subject_reflects_match_count(payload):
    assert "top 3" in render_email_subject(payload)


# --- Dispatch ---------------------------------------------------------------


class StubProvider(NotificationProvider):
    def __init__(self, channel, name, configured=True, succeeds=True):
        self.channel = channel
        self.name = name
        self._configured = configured
        self._succeeds = succeeds
        self.calls = []

    def is_configured(self):
        return self._configured

    def send(self, payload, recipient):
        self.calls.append(recipient)
        if self._succeeds:
            return DeliveryResult.ok(self.channel, self.name, "msg-1")
        return DeliveryResult.failed(self.channel, self.name, "simulated failure")


def use_providers(monkeypatch, *providers):
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: list(providers))


def test_whatsapp_is_preferred_and_email_not_used_on_success(
    db, seeded_jobs, fixed_scores, monkeypatch
):
    whatsapp = StubProvider("whatsapp", "postpeer")
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, whatsapp, email)
    user = make_user(db, min_match_score=0.0)

    outcome, results = dispatcher.send_digest_for_user(db, user)

    assert outcome == "notified"
    assert whatsapp.calls == ["+201001234567"]
    assert email.calls == []  # fallback, not fan-out
    assert results[-1].success


def test_falls_back_to_email_when_whatsapp_fails(
    db, seeded_jobs, fixed_scores, monkeypatch
):
    whatsapp = StubProvider("whatsapp", "postpeer", succeeds=False)
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, whatsapp, email)
    user = make_user(db, min_match_score=0.0)

    outcome, results = dispatcher.send_digest_for_user(db, user)

    assert outcome == "notified"
    assert email.calls == ["candidate@example.com"]
    assert [r.success for r in results] == [False, True]


def test_falls_back_when_whatsapp_is_unconfigured(
    db, seeded_jobs, fixed_scores, monkeypatch
):
    whatsapp = StubProvider("whatsapp", "postpeer", configured=False)
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, whatsapp, email)
    user = make_user(db, min_match_score=0.0)

    outcome, _ = dispatcher.send_digest_for_user(db, user)

    assert outcome == "notified"
    assert whatsapp.calls == []
    assert email.calls == ["candidate@example.com"]


def test_provider_exception_does_not_escape(db, seeded_jobs, fixed_scores, monkeypatch):
    class Exploding(StubProvider):
        def send(self, payload, recipient):
            raise RuntimeError("provider blew up")

    use_providers(monkeypatch, Exploding("whatsapp", "postpeer"), StubProvider("email", "smtp"))
    user = make_user(db, min_match_score=0.0)

    outcome, results = dispatcher.send_digest_for_user(db, user)

    assert outcome == "notified"
    assert results[0].success is False
    assert "provider blew up" in results[0].error


def test_second_run_same_day_is_suppressed(db, seeded_jobs, fixed_scores, monkeypatch):
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, email)
    user = make_user(db, min_match_score=0.0, notify_via_whatsapp=False)

    assert dispatcher.send_digest_for_user(db, user)[0] == "notified"
    assert dispatcher.send_digest_for_user(db, user)[0] == "already_sent"
    assert len(email.calls) == 1


def test_force_overrides_the_daily_guard(db, seeded_jobs, fixed_scores, monkeypatch):
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, email)
    user = make_user(db, min_match_score=0.0, notify_via_whatsapp=False)

    dispatcher.send_digest_for_user(db, user)
    outcome, _ = dispatcher.send_digest_for_user(db, user, force=True)

    assert outcome == "notified"
    assert len(email.calls) == 2


def test_no_matches_sends_nothing(db, seeded_jobs, fixed_scores, monkeypatch):
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, email)
    user = make_user(db, min_match_score=99.0)  # nothing clears this

    outcome, _ = dispatcher.send_digest_for_user(db, user)

    assert outcome == "no_matches"
    assert email.calls == []


def test_dry_run_transmits_nothing(db, seeded_jobs, fixed_scores, monkeypatch):
    email = StubProvider("email", "smtp")
    use_providers(monkeypatch, email)
    user = make_user(db, min_match_score=0.0)

    outcome, _ = dispatcher.send_digest_for_user(db, user, dry_run=True)

    assert outcome == "notified"
    assert email.calls == []


def test_delivery_is_logged_for_audit(db, seeded_jobs, fixed_scores, monkeypatch):
    use_providers(monkeypatch, StubProvider("email", "smtp"))
    user = make_user(db, min_match_score=0.0, notify_via_whatsapp=False)

    dispatcher.send_digest_for_user(db, user)

    log = db.query(NotificationLogORM).one()
    assert log.status == "sent"
    assert len(log.job_ids) == 3
    assert log.match_scores == [90.0, 80.0, 70.0]


def test_run_continues_when_one_user_fails(db, seeded_jobs, fixed_scores, monkeypatch):
    """A single bad user must not abort the nightly run for everyone else."""
    use_providers(monkeypatch, StubProvider("email", "smtp"))
    make_user(db, "good_user", min_match_score=0.0, notify_via_whatsapp=False)
    make_user(db, "bad_user", min_match_score=0.0, notify_via_whatsapp=False)

    original = dispatcher.send_digest_for_user

    def explode_for_bad_user(session, user, **kwargs):
        if user.user_id == "bad_user":
            raise RuntimeError("boom")
        return original(session, user, **kwargs)

    monkeypatch.setattr(dispatcher, "send_digest_for_user", explode_for_bad_user)

    summary = dispatcher.run_daily_dispatch(db, respect_send_hour=False)

    assert summary.users_notified == 1
    assert len(summary.errors) == 1
    assert "bad_user" in summary.errors[0]


def test_send_hour_gating_targets_the_users_local_time(
    db, seeded_jobs, fixed_scores, monkeypatch
):
    use_providers(monkeypatch, StubProvider("email", "smtp"))
    now_cairo_hour = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Africa/Cairo")
    ).hour

    make_user(db, "due_now", min_match_score=0.0, notify_via_whatsapp=False,
              send_hour_local=now_cairo_hour, timezone="Africa/Cairo")
    make_user(db, "due_later", min_match_score=0.0, notify_via_whatsapp=False,
              send_hour_local=(now_cairo_hour + 5) % 24, timezone="Africa/Cairo")

    summary = dispatcher.run_daily_dispatch(db, respect_send_hour=True)

    assert summary.users_notified == 1
    assert summary.users_considered == 1


def test_local_date_is_computed_in_the_users_timezone(db):
    user = make_user(db, timezone="Pacific/Kiritimati")  # UTC+14
    moment = datetime(2026, 6, 25, 23, 0, tzinfo=timezone.utc)
    assert dispatcher.local_date_string(user, moment) == "2026-06-26"
