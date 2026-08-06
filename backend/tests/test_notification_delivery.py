"""Tests for the digest delivery lane.

Scope: everything between "a settings row exists" and "a provider was called".
The Contract 6 settings endpoints are covered by `test_notifications.py` and
are not re-tested here.

The matching pipeline and the scorer are both stubbed throughout. Both build a
SentenceTransformer at import and one of them also talks to Qdrant and an LLM
gateway; what needs testing here is the logic around a score, not the embedding
maths or someone else's network.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.features.notifications import dispatcher, matching_bridge
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
from backend.features.notifications.settings_service import (
    DigestRecipient,
    get_recipient,
    list_recipients,
    normalize_phone,
    save_profile_snapshot,
)
from backend.models.db_models import (
    Base,
    JobPostingORM,
    NotificationLogORM,
    NotificationSettings,
)  # noqa: F401  -- JobPostingORM is constructed directly in one test
from backend.models.job import JobPosting
from backend.services.database import get_db


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def session_factory():
    # StaticPool keeps every connection on the SAME in-memory database;
    # without it a second session opens a fresh, tableless one.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory):
    from backend.features.notifications.routes import router

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def make_job(job_id: str, title: str = "Backend Engineer", skills=None) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        title=title,
        company="Acme",
        location="Cairo, Egypt",
        description="Build things.",
        skills=skills or ["python", "fastapi"],
        job_type="Full Time",
        work_mode="Remote",
        career_level="Experienced",
        experience_years="3 - 5 Yrs",
        salary=None,
        source="wuzzuf",
        url=f"https://example.com/jobs/{job_id}",
        date=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def save_settings(
    db,
    user_id="default",
    channels=("email",),
    email="user@example.com",
    phone="+201001234567",
    threshold=0.4,
    frequency="daily",
    profile=None,
    send_hour_local=8,
    tz="Africa/Cairo",
):
    row = NotificationSettings(
        user_id=user_id,
        email=email,
        phone=phone,
        notification_channels=json.dumps(list(channels)),
        frequency=frequency,
        relevance_threshold=threshold,
        full_name="Omar",
        send_hour_local=send_hour_local,
        timezone=tz,
        profile_snapshot=json.dumps(profile if profile is not None else {"skills": ["python"]}),
    )
    db.add(row)
    db.commit()
    return row


def recipient(**overrides) -> DigestRecipient:
    base = dict(
        user_id="default",
        full_name="Omar",
        email="user@example.com",
        phone="+201001234567",
        channels=["email"],
        min_match_score=40.0,
        profile={"skills": ["python"]},
    )
    base.update(overrides)
    return DigestRecipient(**base)


def payload(matches=None) -> DigestPayload:
    return DigestPayload(
        user_id="default",
        full_name="Omar",
        matches=matches
        if matches is not None
        else [TopJobMatch(job=make_job("j1"), match_score=88.0, reason="Strong fit.")],
        generated_at=datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc),
    )


class RecordingProvider(NotificationProvider):
    """A provider that records calls instead of transmitting."""

    def __init__(self, channel, name, configured=True, succeeds=True, raises=False):
        self.channel = channel
        self.name = name
        self._configured = configured
        self._succeeds = succeeds
        self._raises = raises
        self.calls = []

    def is_configured(self):
        return self._configured

    def send(self, payload, recipient_address):
        self.calls.append(recipient_address)
        if self._raises:
            raise RuntimeError("provider exploded")
        if self._succeeds:
            return DeliveryResult.ok(self.channel, self.name, "id-1")
        return DeliveryResult.failed(self.channel, self.name, "nope")


# --- phone normalization ----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+201001234567", "+201001234567"),
        ("+20 (100) 123-4567", "+201001234567"),
        ("00201001234567", "+201001234567"),
        ("  +201001234567  ", "+201001234567"),
    ],
)
def test_phone_is_normalized_to_e164(raw, expected):
    """WhatsApp providers reject non-E.164 numbers, sometimes silently."""
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "12345", "+" + "9" * 20, "abc"])
def test_unusable_phone_becomes_none_rather_than_raising(raw):
    """A bad number should cost that user their WhatsApp channel, not abort
    the run for everyone after them."""
    assert normalize_phone(raw) is None


# --- settings -> recipient --------------------------------------------------


def test_relevance_threshold_is_scaled_to_the_match_score_range(db):
    """Contract 6 stores 0-1; match_score is 0-100. Getting this wrong would
    make a 0.75 threshold pass every job instead of almost none."""
    save_settings(db, threshold=0.75)

    assert get_recipient(db, "default").min_match_score == 75.0


def test_channels_decode_from_json(db):
    save_settings(db, channels=["email", "whatsapp"])

    assert get_recipient(db, "default").channels == ["email", "whatsapp"]


def test_malformed_stored_json_is_survivable(db):
    """A hand-edited row should degrade to "no channels", not 500 the run."""
    row = save_settings(db)
    row.notification_channels = "{not json"
    row.profile_snapshot = "also not json"
    db.commit()

    resolved = get_recipient(db, "default")
    assert resolved.channels == []
    assert resolved.profile == {}


def test_a_user_with_no_selected_channel_is_not_reachable(db):
    save_settings(db, channels=[])

    assert get_recipient(db, "default").is_reachable() is False
    assert list_recipients(db) == []


def test_a_channel_without_an_address_is_not_reachable(db):
    save_settings(db, channels=["whatsapp"], phone=None)

    assert get_recipient(db, "default").is_reachable() is False


def test_unknown_timezone_falls_back_instead_of_raising(db):
    save_settings(db, tz="Mars/Olympus_Mons")

    # Resolvable to *something* is the requirement; a background thread that
    # raises here stops every user after this one.
    assert get_recipient(db, "default").zone() is not None


def test_profile_snapshot_round_trips(db):
    save_settings(db, profile={})

    save_profile_snapshot(db, "default", {"skills": ["python", "sql"], "title": "Dev"})

    assert get_recipient(db, "default").profile["skills"] == ["python", "sql"]


# --- selection --------------------------------------------------------------


def _stub_pipeline(monkeypatch, entries):
    """Replace run_match_pipeline where matching_bridge looks it up."""
    import backend.services.matching_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "run_match_pipeline", lambda *a, **k: entries
    )


def _persist(db, *jobs):
    from backend.models.db_models import job_posting_to_orm

    for job in jobs:
        db.add(job_posting_to_orm(job))
    db.commit()


def test_top_matches_come_from_the_pipeline_and_are_scaled(db, monkeypatch):
    """fit_score is 0-1; the digest speaks 0-100."""
    _persist(db, make_job("j1"))
    _stub_pipeline(monkeypatch, [{"job_id": "j1", "fit_score": 0.82}])

    matches = matching_bridge.get_top_matches(db, recipient())

    assert len(matches) == 1
    assert matches[0].match_score == pytest.approx(82.0)


def test_reason_comes_from_the_explanation_agent(db, monkeypatch):
    _persist(db, make_job("j1"))
    _stub_pipeline(
        monkeypatch,
        [
            {
                "job_id": "j1",
                "fit_score": 0.9,
                "explanation": {"overall_alignment_summary": "Your Python is a fit."},
            }
        ],
    )

    assert matching_bridge.get_top_matches(db, recipient())[0].reason == (
        "Your Python is a fit."
    )


def test_jobs_below_the_threshold_are_dropped(db, monkeypatch):
    _persist(db, make_job("j1"), make_job("j2"))
    _stub_pipeline(
        monkeypatch,
        [{"job_id": "j1", "fit_score": 0.9}, {"job_id": "j2", "fit_score": 0.1}],
    )

    matches = matching_bridge.get_top_matches(db, recipient(min_match_score=50.0))

    assert [match.job.job_id for match in matches] == ["j1"]


def test_results_are_truncated_to_top_n_highest_first(db, monkeypatch):
    _persist(db, make_job("j1"), make_job("j2"), make_job("j3"), make_job("j4"))
    _stub_pipeline(
        monkeypatch,
        [
            {"job_id": "j1", "fit_score": 0.5},
            {"job_id": "j2", "fit_score": 0.9},
            {"job_id": "j3", "fit_score": 0.7},
            {"job_id": "j4", "fit_score": 0.6},
        ],
    )

    matches = matching_bridge.get_top_matches(db, recipient(), top_n=3)

    assert [match.job.job_id for match in matches] == ["j2", "j3", "j4"]


def test_a_ranked_job_missing_from_sqlite_is_omitted(db, monkeypatch):
    """Qdrant and SQLite can drift. Naming a job we cannot look up would mean
    inventing its company, location and link."""
    _persist(db, make_job("j1"))
    _stub_pipeline(
        monkeypatch,
        [{"job_id": "j1", "fit_score": 0.9}, {"job_id": "ghost", "fit_score": 0.95}],
    )

    matches = matching_bridge.get_top_matches(db, recipient())

    assert [match.job.job_id for match in matches] == ["j1"]


def test_recently_sent_jobs_are_excluded(db, monkeypatch):
    """PRD 7.9: don't re-notify about jobs already seen."""
    _persist(db, make_job("j1"), make_job("j2"))
    _stub_pipeline(
        monkeypatch,
        [{"job_id": "j1", "fit_score": 0.95}, {"job_id": "j2", "fit_score": 0.6}],
    )

    matches = matching_bridge.get_top_matches(
        db, recipient(), exclude_job_ids={"j1"}
    )

    assert [match.job.job_id for match in matches] == ["j2"]


def test_dedupe_window_reads_only_successful_recent_sends(db):
    db.add_all(
        [
            NotificationLogORM(
                user_id="default",
                channel="email",
                status="sent",
                job_ids=json.dumps(["recent"]),
                match_scores="[]",
                sent_on_local_date="2026-08-06",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ),
            NotificationLogORM(
                user_id="default",
                channel="email",
                status="failed",
                job_ids=json.dumps(["never-arrived"]),
                match_scores="[]",
                sent_on_local_date="2026-08-06",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ),
            NotificationLogORM(
                user_id="default",
                channel="email",
                status="sent",
                job_ids=json.dumps(["long-ago"]),
                match_scores="[]",
                sent_on_local_date="2026-01-01",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30),
            ),
        ]
    )
    db.commit()

    seen = matching_bridge.recently_notified_job_ids(db, "default")

    # A job the user was never actually told about must not be suppressed.
    assert seen == {"recent"}


def test_no_stored_profile_yields_no_matches(db, monkeypatch):
    """"Your top matches" with nothing to match against would be a lie."""
    _persist(db, make_job("j1"))
    _stub_pipeline(monkeypatch, [{"job_id": "j1", "fit_score": 0.9}])

    assert matching_bridge.get_top_matches(db, recipient(profile={})) == []


def test_one_malformed_stored_row_does_not_cost_the_whole_digest(db, monkeypatch):
    """`JobPosting` requires an http URL. A row that fails validation — written
    before that check, or by hand — must drop one line, not the digest."""
    _persist(db, make_job("good"))
    db.add(
        JobPostingORM(
            job_id="bad",
            title="Broken",
            company="Acme",
            location="Cairo",
            description="",
            skills="[]",
            source="manual",
            url="not-a-url",
            date=datetime(2026, 8, 2, tzinfo=timezone.utc),
        )
    )
    db.commit()

    _stub_pipeline(
        monkeypatch,
        [{"job_id": "bad", "fit_score": 0.99}, {"job_id": "good", "fit_score": 0.8}],
    )

    matches = matching_bridge.get_top_matches(db, recipient())

    assert [match.job.job_id for match in matches] == ["good"]


def test_a_negative_similarity_does_not_blow_up_the_schema(db, monkeypatch):
    """Cosine similarity is defined on [-1, 1], so the scorer really does
    return negative numbers for an unrelated job. `TopJobMatch.match_score` is
    declared 0-100, and an unclamped -6.54 raised a ValidationError that took
    out the whole preview rather than just dropping one row.
    """
    _persist(db, make_job("j1"))

    import backend.services.matching_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module,
        "run_match_pipeline",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no qdrant")),
    )

    import backend.features.matching.scorer as scorer_module

    monkeypatch.setattr(
        scorer_module, "calculate_match_score", lambda profile, job: -6.54
    )

    matches = matching_bridge.get_top_matches(db, recipient(min_match_score=0.0))

    assert [match.match_score for match in matches] == [0.0]


def test_an_out_of_range_fit_score_is_clamped(db, monkeypatch):
    """`fit_score` comes from an LLM, so "nominally 0-1" is not a guarantee."""
    _persist(db, make_job("j1"))
    _stub_pipeline(monkeypatch, [{"job_id": "j1", "fit_score": 1.4}])

    assert matching_bridge.get_top_matches(db, recipient())[0].match_score == 100.0


def test_pipeline_failure_falls_back_to_the_scorer(db, monkeypatch):
    """Qdrant down or locked must not mean no digest — /matching/rank-jobs
    degrades the same way."""
    _persist(db, make_job("j1"), make_job("j2"))

    import backend.services.matching_pipeline as pipeline_module

    def explode(*args, **kwargs):
        raise RuntimeError("qdrant is locked")

    monkeypatch.setattr(pipeline_module, "run_match_pipeline", explode)

    import backend.features.matching.scorer as scorer_module

    monkeypatch.setattr(
        scorer_module,
        "calculate_match_score",
        lambda profile, job: 90.0 if job.job_id == "j2" else 10.0,
    )

    matches = matching_bridge.get_top_matches(db, recipient(min_match_score=50.0))

    assert [match.job.job_id for match in matches] == ["j2"]
    # Nothing on the fallback path can supply an explanation.
    assert matches[0].reason is None


# --- dispatch ---------------------------------------------------------------


def _stub_matches(monkeypatch, matches):
    """Patch selection at the dispatcher's own import site.

    The dispatcher takes `select_top_matches` (which reports *why* a result is
    empty), not the plain list helper, so stubbing the old name silently patched
    nothing and every test using it failed on AttributeError.
    """
    monkeypatch.setattr(
        dispatcher,
        "select_top_matches",
        lambda *a, **k: matching_bridge.Selection(matches=matches),
    )
    monkeypatch.setattr(
        dispatcher, "recently_notified_job_ids", lambda *a, **k: set()
    )


def test_whatsapp_is_tried_first_and_email_is_not_touched_on_success(
    db, monkeypatch
):
    """The chain is a fallback, not a fan-out: one digest, not two."""
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer")
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    outcome, results = dispatcher.send_digest_for_user(
        db, recipient(channels=["whatsapp", "email"])
    )

    assert outcome == "notified"
    assert whatsapp.calls == ["+201001234567"]
    assert email.calls == []
    assert len(results) == 1


def test_a_failing_whatsapp_falls_back_to_email(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer", succeeds=False)
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    outcome, results = dispatcher.send_digest_for_user(
        db, recipient(channels=["whatsapp", "email"])
    )

    assert outcome == "notified"
    assert email.calls == ["user@example.com"]
    assert [result.success for result in results] == [False, True]


def test_a_provider_that_raises_does_not_stop_the_chain(db, monkeypatch):
    """Providers are contracted not to raise; a bug in one must not cost the
    user their digest."""
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer", raises=True)
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    outcome, _ = dispatcher.send_digest_for_user(
        db, recipient(channels=["whatsapp", "email"])
    )

    assert outcome == "notified"
    assert email.calls == ["user@example.com"]


def test_an_unconfigured_provider_is_skipped_not_failed(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer", configured=False)
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    outcome, results = dispatcher.send_digest_for_user(
        db, recipient(channels=["whatsapp", "email"])
    )

    assert outcome == "notified"
    assert whatsapp.calls == []
    # An unconfigured provider produces no log row at all — it never attempted.
    assert len(results) == 1


def test_a_channel_the_user_did_not_select_is_skipped(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer")
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    dispatcher.send_digest_for_user(db, recipient(channels=["email"]))

    assert whatsapp.calls == []
    assert email.calls == ["user@example.com"]


def test_no_matches_sends_nothing(db, monkeypatch):
    """A daily email that says "nothing today" is how a digest gets muted."""
    _stub_matches(monkeypatch, [])
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    outcome, _ = dispatcher.send_digest_for_user(db, recipient())

    assert outcome == "no_matches"
    assert email.calls == []


def test_all_qualifying_jobs_already_sent_is_not_reported_as_a_threshold_problem(
    db, monkeypatch
):
    """The bug this pins: jobs scoring 88 and 45 against a threshold of 30 were
    reported as "no job cleared your relevance threshold", because the de-dupe
    window had removed them. No threshold, however low, can surface a job that
    is being excluded by id — so that message sent people to fix the one thing
    that was never wrong."""
    monkeypatch.setattr(
        dispatcher,
        "select_top_matches",
        lambda *a, **k: matching_bridge.Selection(
            matches=[], cleared_threshold=2, suppressed_as_recent=2
        ),
    )
    monkeypatch.setattr(dispatcher, "recently_notified_job_ids", lambda *a, **k: {"j1"})

    outcome, _ = dispatcher.send_digest_for_user(db, recipient())

    assert outcome == "no_new_matches"


def test_nothing_good_enough_still_reports_no_matches(db, monkeypatch):
    """The other half of the split: when nothing cleared the bar, a lower
    threshold genuinely is the fix and the copy should still say so."""
    monkeypatch.setattr(
        dispatcher,
        "select_top_matches",
        lambda *a, **k: matching_bridge.Selection(
            matches=[], cleared_threshold=0, suppressed_as_recent=0
        ),
    )
    monkeypatch.setattr(dispatcher, "recently_notified_job_ids", lambda *a, **k: set())

    outcome, _ = dispatcher.send_digest_for_user(db, recipient())

    assert outcome == "no_matches"


def test_send_test_does_not_suppress_recently_sent_jobs(db, monkeypatch):
    """A test button that stops working once it has worked is not a test button.

    The de-dupe window protects a *scheduled* digest from repeating itself;
    applied to a manual test send it guarantees failure after the first
    success, which is exactly what was reported.
    """
    seen = {}

    def capture(session, target, top_n=3, exclude_job_ids=None):
        seen["excluded"] = exclude_job_ids
        return matching_bridge.Selection(
            matches=[TopJobMatch(job=make_job("j1"), match_score=80.0)]
        )

    monkeypatch.setattr(dispatcher, "select_top_matches", capture)
    monkeypatch.setattr(
        dispatcher, "recently_notified_job_ids", lambda *a, **k: {"j1", "j2"}
    )
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    outcome, _ = dispatcher.send_digest_for_user(
        db, recipient(), force=True, suppress_recent=False
    )

    assert outcome == "notified"
    assert seen["excluded"] == set(), "a test send must not exclude anything"


def test_scheduled_send_still_suppresses_recently_sent_jobs(db, monkeypatch):
    """The default has to stay on, or the daily digest repeats itself."""
    seen = {}

    def capture(session, target, top_n=3, exclude_job_ids=None):
        seen["excluded"] = exclude_job_ids
        return matching_bridge.Selection(matches=[])

    monkeypatch.setattr(dispatcher, "select_top_matches", capture)
    monkeypatch.setattr(dispatcher, "recently_notified_job_ids", lambda *a, **k: {"j1"})

    dispatcher.send_digest_for_user(db, recipient())

    assert seen["excluded"] == {"j1"}


def test_selection_counts_why_it_came_back_empty(db, monkeypatch):
    """The counters are what make the two empty cases distinguishable without
    scoring everything a second time."""
    _persist(db, make_job("j1"), make_job("j2"))
    _stub_pipeline(
        monkeypatch,
        [{"job_id": "j1", "fit_score": 0.88}, {"job_id": "j2", "fit_score": 0.45}],
    )

    result = matching_bridge.select_top_matches(
        db, recipient(min_match_score=30.0), exclude_job_ids={"j1", "j2"}
    )

    assert result.matches == []
    assert result.cleared_threshold == 2
    assert result.suppressed_as_recent == 2


def test_no_stored_profile_is_reported_distinctly_from_no_matches(db, monkeypatch):
    """Both end in nothing sent, but one is fixed with a CV and the other with
    a lower threshold. Collapsing them sends whoever is debugging a digest to
    tune a slider that was never the problem."""
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    outcome, _ = dispatcher.send_digest_for_user(db, recipient(profile={}))

    assert outcome == "no_profile"
    assert email.calls == []


def test_no_profile_is_checked_before_the_daily_guard(db, monkeypatch):
    """Otherwise a user who was sent to earlier today reports "already_sent"
    and hides the real reason nothing will go tomorrow either."""
    outcome, _ = dispatcher.send_digest_for_user(
        db, recipient(profile={}), force=False
    )

    assert outcome == "no_profile"


def test_unreachable_user_is_reported_not_attempted(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])

    outcome, _ = dispatcher.send_digest_for_user(db, recipient(channels=[]))

    assert outcome == "no_contact"


def test_dry_run_renders_but_transmits_nothing(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    outcome, results = dispatcher.send_digest_for_user(db, recipient(), dry_run=True)

    assert outcome == "notified"
    assert email.calls == []
    assert results[0].channel == "dry-run"


# --- idempotency ------------------------------------------------------------


def test_a_second_run_on_the_same_day_does_not_resend(db, monkeypatch):
    """24 hourly ticks must not produce 24 digests."""
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    first, _ = dispatcher.send_digest_for_user(db, recipient())
    second, _ = dispatcher.send_digest_for_user(db, recipient())

    assert (first, second) == ("notified", "already_sent")
    assert len(email.calls) == 1


def test_force_overrides_the_daily_guard(db, monkeypatch):
    """The "send test" button must not answer "already sent today"."""
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    dispatcher.send_digest_for_user(db, recipient())
    outcome, _ = dispatcher.send_digest_for_user(db, recipient(), force=True)

    assert outcome == "notified"
    assert len(email.calls) == 2


def test_a_failed_send_does_not_consume_the_days_slot(db, monkeypatch):
    """Only a *successful* send counts. Otherwise one SMTP blip costs the user
    the whole day."""
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    failing = RecordingProvider("email", "smtp", succeeds=False)
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [failing])

    dispatcher.send_digest_for_user(db, recipient())

    working = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [working])
    outcome, _ = dispatcher.send_digest_for_user(db, recipient())

    assert outcome == "notified"


def test_weekly_frequency_waits_a_week(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [email])

    dispatcher.send_digest_for_user(db, recipient(frequency="weekly"))

    # Two days later — a new local date, but not a new week.
    row = db.query(NotificationLogORM).one()
    row.sent_on_local_date = "1999-01-01"
    row.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    db.commit()

    outcome, _ = dispatcher.send_digest_for_user(db, recipient(frequency="weekly"))
    assert outcome == "already_sent"

    row.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=8)
    db.commit()

    outcome, _ = dispatcher.send_digest_for_user(db, recipient(frequency="weekly"))
    assert outcome == "notified"


def test_local_date_is_the_users_not_the_servers():
    """The idempotency key is the *user's* calendar day.

    At 21:30 UTC, Cairo is already on the next date. Keying on the server's UTC
    date would let a Cairo user receive a second digest a few hours later, on
    the day they are actually living in.
    """
    late_evening_utc = datetime(2026, 8, 6, 21, 30, tzinfo=timezone.utc)

    cairo = dispatcher.local_date_string(
        recipient(timezone="Africa/Cairo"), late_evening_utc
    )
    utc = dispatcher.local_date_string(recipient(timezone="UTC"), late_evening_utc)

    assert utc == "2026-08-06"
    assert cairo == "2026-08-07"

    # Westward too: 01:30 UTC is still the previous day in New York.
    early_morning_utc = datetime(2026, 8, 6, 1, 30, tzinfo=timezone.utc)
    assert (
        dispatcher.local_date_string(
            recipient(timezone="America/New_York"), early_morning_utc
        )
        == "2026-08-05"
    )


def test_every_attempt_is_logged_including_failures(db, monkeypatch):
    _stub_matches(monkeypatch, [TopJobMatch(job=make_job("j1"), match_score=80.0)])
    whatsapp = RecordingProvider("whatsapp", "postpeer", succeeds=False)
    email = RecordingProvider("email", "smtp")
    monkeypatch.setattr(dispatcher, "build_provider_chain", lambda: [whatsapp, email])

    dispatcher.send_digest_for_user(db, recipient(channels=["whatsapp", "email"]))

    rows = db.query(NotificationLogORM).order_by(NotificationLogORM.id).all()
    assert [(row.channel, row.status) for row in rows] == [
        ("whatsapp", "failed"),
        ("email", "sent"),
    ]
    assert json.loads(rows[1].job_ids) == ["j1"]


# --- run-level behaviour ----------------------------------------------------


def test_one_users_failure_does_not_abort_the_run(db, monkeypatch):
    save_settings(db, user_id="alice", email="alice@example.com")
    save_settings(db, user_id="bob", email="bob@example.com")

    calls = []

    def flaky(session, target, **kwargs):
        calls.append(target.user_id)
        if target.user_id == "alice":
            raise RuntimeError("alice's row is cursed")
        return "notified", []

    monkeypatch.setattr(dispatcher, "send_digest_for_user", flaky)

    summary = dispatcher.run_daily_dispatch(db, respect_send_hour=False)

    assert sorted(calls) == ["alice", "bob"]
    assert summary.users_notified == 1
    assert len(summary.errors) == 1


def test_send_hour_gates_who_is_considered(db, monkeypatch):
    """The hourly tick exists so a user in Cairo and one in London each get
    theirs at their own 8am."""
    save_settings(db, user_id="now", send_hour_local=8, tz="UTC")
    save_settings(db, user_id="later", send_hour_local=23, tz="UTC")

    monkeypatch.setattr(dispatcher, "_is_send_hour", lambda r: r.user_id == "now")
    monkeypatch.setattr(
        dispatcher, "send_digest_for_user", lambda *a, **k: ("notified", [])
    )

    summary = dispatcher.run_daily_dispatch(db, respect_send_hour=True)

    assert summary.users_considered == 1
    assert summary.users_notified == 1


def test_manual_dispatch_ignores_the_send_hour(db, monkeypatch):
    save_settings(db, user_id="later", send_hour_local=23, tz="UTC")
    monkeypatch.setattr(
        dispatcher, "send_digest_for_user", lambda *a, **k: ("notified", [])
    )

    summary = dispatcher.run_daily_dispatch(db, respect_send_hour=False)

    assert summary.users_considered == 1


# --- rendering --------------------------------------------------------------


def test_email_subject_is_singular_for_one_match():
    single = payload([TopJobMatch(job=make_job("j1", "Data Analyst"), match_score=70.0)])

    assert render_email_subject(single) == "1 new job match: Data Analyst"


def test_email_html_carries_the_job_and_the_link():
    html = render_email_html(payload(), app_base_url="http://localhost:5173")

    assert "Backend Engineer" in html
    assert "https://example.com/jobs/j1" in html
    assert "88% match" in html
    assert "http://localhost:5173/app/settings" in html


def test_email_text_part_exists_and_is_not_html():
    """A multipart/alternative mail with no text part is a spam signal."""
    text = render_email_text(payload())

    assert "Backend Engineer" in text
    assert "<table" not in text


def test_whatsapp_markup_is_not_html_escaped():
    """*bold* is WhatsApp's own markup; escaping it would show the asterisks."""
    body = render_whatsapp_text(payload())

    assert "*1. Backend Engineer*" in body
    assert "&amp;" not in body


def test_the_reason_is_rendered_when_present_and_absent_otherwise():
    with_reason = render_email_text(payload())
    without = render_email_text(
        payload([TopJobMatch(job=make_job("j1"), match_score=80.0)])
    )

    assert "Why: Strong fit." in with_reason
    assert "Why:" not in without


def test_footer_link_is_omitted_when_no_base_url_is_configured():
    """Better no link than a link to "/app/settings" on nowhere."""
    assert "Manage alerts" not in render_whatsapp_text(payload(), app_base_url="")


# --- HTTP surface -----------------------------------------------------------


def test_preview_404s_for_a_user_with_no_settings(client):
    assert client.get("/notifications/preview/nobody").status_code == 404


def test_send_test_404s_for_a_user_with_no_settings(client):
    assert client.post("/notifications/send-test/nobody").status_code == 404


def test_profile_snapshot_404s_before_settings_exist(client):
    response = client.put(
        "/notifications/settings/nobody/profile", json={"profile": {"skills": ["x"]}}
    )

    assert response.status_code == 404


def test_profile_snapshot_saves_once_settings_exist(client, db):
    save_settings(db, profile={})

    response = client.put(
        "/notifications/settings/default/profile",
        json={"profile": {"skills": ["python"], "title": "Dev"}},
    )

    assert response.status_code == 200
    assert response.json()["profile_fields"] == ["skills", "title"]


def test_providers_endpoint_reports_configuration(client):
    body = client.get("/notifications/providers").json()

    assert {entry["channel"] for entry in body} == {"whatsapp", "email"}


def test_scheduler_endpoint_reports_disabled_by_default(client):
    body = client.get("/notifications/scheduler").json()

    assert body["running"] is False


def test_logs_endpoint_returns_newest_first(client, db):
    for index in range(3):
        db.add(
            NotificationLogORM(
                user_id="default",
                channel="email",
                provider="smtp",
                status="sent",
                job_ids=json.dumps([f"j{index}"]),
                match_scores="[]",
                sent_on_local_date=f"2026-08-0{index + 1}",
            )
        )
    db.commit()

    body = client.get("/notifications/logs?user_id=default").json()

    assert len(body) == 3
    assert body[0]["id"] > body[-1]["id"]


def test_dispatch_dry_run_reports_a_summary(client, db, monkeypatch):
    save_settings(db)
    monkeypatch.setattr(
        "backend.features.notifications.dispatcher.select_top_matches",
        lambda *a, **k: matching_bridge.Selection(
            matches=[TopJobMatch(job=make_job("j1"), match_score=80.0)]
        ),
    )

    body = client.post("/notifications/dispatch?dry_run=true").json()

    assert body["users_considered"] == 1
    assert body["users_notified"] == 1
