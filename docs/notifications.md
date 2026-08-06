# Daily job match notifications

Sends each user their top 3 job matches automatically, once a day, without them
running a search. WhatsApp (via Postpeer) is the primary channel; email is the
fallback.

Covers PRD 6.4 (notification flow), 7.8 (notifications), 7.9 (don't re-notify
about jobs already seen), and 10.2.4 (automation & notification service).

Where contact details are *stored* is a separate document:
[notification-parameters.md](notification-parameters.md). This one is about
what happens after that.

---

## 1. How it fits together

```
                    hourly tick
  scheduler.py  ─────────────────►  dispatcher.run_daily_dispatch()
  (APScheduler)                            │
                                           │ for each reachable user
                                           ▼
                              matching_bridge.get_top_matches()
                                           │  ← run_match_pipeline(), or the
                                           │    scorer if Qdrant is down
                                           ▼
                                  renderer.py (Jinja templates)
                                           │
                                           ▼
                        providers/  postpeer ──fails/unset──► smtp
                                           │
                                           ▼
                                  notification_logs
```

| File | Responsibility |
|---|---|
| `backend/features/notifications/scheduler.py` | APScheduler trigger |
| `backend/features/notifications/dispatcher.py` | Per-user orchestration, idempotency |
| `backend/features/notifications/matching_bridge.py` | Top-N selection via the existing pipeline |
| `backend/features/notifications/renderer.py` + `templates/` | Message bodies |
| `backend/features/notifications/providers/` | Delivery adapters |
| `backend/features/notifications/settings_service.py` | Settings row → sending decisions |
| `backend/features/notifications/routes.py` | HTTP surface for dispatch and diagnostics |
| `backend/routes/notifications.py` | Contract 6 settings storage (unchanged) |
| `frontend/src/pages/SettingsPage.tsx` | The settings tab |

---

## 2. Setup

```bash
pip install -r requirements.txt
cp .env.example .env

# Terminal 1 — API
uvicorn backend.main:app --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open <http://localhost:5173/app/settings>, save contact details, then use
**Preview digest** and **Send now**.

**With no `EMAIL_HOST` set, digests print to the API console instead of
sending** (`EMAIL_CONSOLE_FALLBACK=true`). That is enough to demo the whole
pipeline without any credentials, and the banner makes it obvious nothing
really left the machine.

### Turning the schedule on

```env
NOTIFICATIONS_SCHEDULER_ENABLED=true
```

**Off by default**, so local dev and CI never send real messages to real
people. Nothing sends on its own until you change this.

---

## 3. What the digest is built from

Two paths, and only ever one of them per run:

1. **The pipeline** — `services/matching_pipeline.run_match_pipeline`: Qdrant
   retrieval, LLM re-ranking, then the Match Explanation Agent. This is the
   same call `POST /matching/pipeline` makes, so the digest cannot disagree
   with what the app shows. It is also the only path that can fill in the
   `reason` line under each job (the agent's `overall_alignment_summary`).

2. **The scorer** — `features/matching/scorer.calculate_match_score`: cosine
   similarity over the 200 most recent postings in SQLite. Used only when the
   pipeline raises or returns nothing, which is what happens when Qdrant is
   down, locked by another process, or empty. `POST /matching/rank-jobs`
   degrades the same way.

They are never mixed inside one digest. Both produce 0-100 numbers, but not by
the same method, and a message whose three rows were scored two different ways
is a message whose ranking means nothing.

Selection order: score → drop jobs sent in the last 7 days → drop anything
below the user's threshold → sort → take 3.

### The profile problem, and how it is solved

The CV profile lives in browser session state. A 9am cron job has no browser,
so it has nothing to match against.

So the settings row carries a `profile_snapshot` column — the same free-form
profile dict the UI posts to `/matching/pipeline`, stored as JSON. The frontend
writes it via `PUT /notifications/settings/{user_id}/profile` whenever settings
are saved and a profile is loaded.

**A user with no stored profile gets no digest**, and the preview says so
rather than showing an arbitrary three jobs.

---

## 4. Why the scheduler ticks hourly

Each user picks their own `send_hour_local` in their own `timezone`. A single
daily fire would deliver at the same instant worldwide, which is the wrong local
time for everyone outside the server's zone.

So the trigger runs every hour, and only users whose local hour matches right
now are sent to. Twenty-four ticks do not produce twenty-four digests, because
the dispatcher enforces one digest per user per **local calendar day** — the key
is `sent_on_local_date`, not a UTC timestamp. A user in UTC+3 at 23:00 local is
already on tomorrow's UTC date; keying on UTC would give them a second digest a
few hours later.

Only a *successful* send consumes the day's slot. One SMTP blip should not cost
the user their digest.

Running the API with multiple uvicorn workers gives each worker its own
scheduler. The idempotency check makes that safe rather than catastrophic, but
the correct setup is a single scheduler process:

```bash
python scripts/run_scheduler.py
```

---

## 5. Channel fallback

`build_provider_chain()` returns `[Postpeer(whatsapp), Smtp(email)]`. The
dispatcher walks it and **stops at the first success** — a user gets one
message, not two. It moves to the next channel when:

* the user did not select that channel, or has no usable address for it, or
* the provider is not configured (no credentials in `.env`), or
* the send returns a failure, or raises.

Every *attempt* is written to `notification_logs`, successes and failures both.
A provider that was never tried (unselected or unconfigured) writes nothing —
there is no attempt to record.

Phone numbers are normalized to E.164 (`+201001234567`) when read, because
WhatsApp providers reject other formats and on some plans reject them
*silently*. A number that cannot be normalized costs that user their WhatsApp
channel; it does not fail their digest or the run.

---

## 6. API

Settings storage (unchanged, see notification-parameters.md):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/notifications/settings` | Save contact details and preferences |
| `GET` | `/notifications/settings/{user_id}` | Read them back |

Delivery:

| Method | Path | Purpose |
|---|---|---|
| `PUT` | `/notifications/settings/{id}/profile` | Store the profile the digest scores against |
| `GET` | `/notifications/preview/{id}` | Top 3 without sending |
| `POST` | `/notifications/send-test/{id}` | Send now, ignoring the daily guard |
| `POST` | `/notifications/dispatch` | Run the whole digest on demand |
| `GET` | `/notifications/providers` | Which channels are configured |
| `GET` | `/notifications/scheduler` | Scheduler state and next run |
| `GET` | `/notifications/logs` | Recent delivery attempts |

```bash
# What would be sent, without sending it
curl http://localhost:8000/notifications/preview/default

# Send it
curl -X POST http://localhost:8000/notifications/send-test/default

# Why didn't it arrive?
curl http://localhost:8000/notifications/providers
curl http://localhost:8000/notifications/logs
```

---

## 7. Settings, and what each one does

Stored on `notification_settings`, written by the settings tab.

| Field | Default | Effect |
|---|---|---|
| `notification_channels` | `["email"]` | Which providers may be tried. Empty means the user is unreachable and is skipped. |
| `relevance_threshold` | `0.75` | **Stored 0-1, compared against a 0-100 match score** — 0.75 means "at least 75". |
| `frequency` | `daily` | `daily` or `weekly`. `weekly` means seven days between digests, not seven chances to get one. |
| `send_hour_local` | `8` | Local hour of delivery, 0-23. |
| `timezone` | `Africa/Cairo` | IANA name. Validated on write — an unknown zone is a 422, not a stored value that silently delivers at the wrong hour. |
| `full_name` | — | How the digest greets the user. Blank renders as "there". |
| `profile_snapshot` | — | The matching input. No profile, no digest. |

`send_hour_local`, `timezone`, `full_name` and `profile_snapshot` were added
when delivery landed. They are **additive**: a client that omits them keeps
what is stored, and a client that ignores them on read is unaffected. Existing
SQLite files get the columns via the additive migration in
`backend/services/database.py`.

---

## 8. Open items

### Postpeer contract — needs confirming

`backend/features/notifications/providers/postpeer.py`

Postpeer's API shape is not documented anywhere in this repo, so every
vendor-specific detail is an environment variable with a conservative default.
Four answers are needed from the Postpeer dashboard: base URL and send path,
auth scheme, the JSON field names for recipient/body/sender, and where the
message id sits in the response. Set them in `.env` and the provider works with
no code change; if the real contract does not fit, `_build_request()` is the
only method to rewrite.

**Raise early:** on the official WhatsApp Business Platform, a
business-initiated message outside the 24-hour service window must use a
**pre-approved template**; free-form text is rejected. A daily unprompted
digest is business-initiated by definition. Unless Postpeer resells a number
under its own approved template, a template must be submitted and approved
before WhatsApp can deliver anything. That approval lead time is the most
likely reason this channel turns out "not feasible" — which is why the email
fallback is a real implementation and not a stub. Set
`POSTPEER_TEMPLATE_NAME` once approved.

### Before any public deploy

* **`POST /notifications/dispatch` is unauthenticated** and sends real messages
  to every user. Every route in this app is unauthenticated today, but this is
  the one that costs money and reputation. Gate it.
* **`user_id` is always `"default"`.** There is no auth and no session concept,
  so every browser writes the same row. When auth lands, this is the seam.
* **No unsubscribe token.** The footer links to the settings page, which is
  fine while there is no auth; a real one-click unsubscribe needs a signed
  token.

### Known gaps

* **No retry.** A failed send is logged, not retried; the user gets the next
  day's digest. Retry belongs with a task queue, not this scheduler.
* **Scoring cost on the fallback path.** `calculate_match_score()` re-encodes
  the profile on every call, so a fallback run is O(users × jobs) encodes. The
  pool is capped at 200 recent postings to bound it. A batch entry point in
  `scorer.py` would fix it properly; that file belongs to the matching lane.
* **De-duplication can starve a small pool.** With few postings and a 7-day
  window, a user can legitimately run out of new jobs and get nothing. That is
  the correct behaviour — a digest with nothing new in it is worse than no
  digest — but it looks like a bug if you do not know it is happening. The
  preview endpoint takes `include_recent=true` to see past it.

---

## 9. Testing

```bash
pytest backend/tests/test_notification_delivery.py -q   # 60 tests
pytest backend/tests/test_notifications.py -q           # settings contract
```

The pipeline and the scorer are stubbed throughout. Both build a
SentenceTransformer at import, and one of them also talks to Qdrant and an LLM
gateway; what needs testing here is the logic around a score, not the embedding
maths or someone else's network.

Covered: phone normalization, threshold scaling, malformed stored JSON and
malformed stored job rows, reachability, top-N selection, explanation
pass-through, score clamping, de-duplication, pipeline→scorer fallback,
WhatsApp→email fallback, provider failure isolation, once-per-day idempotency,
weekly spacing, timezone-correct local dates, send-hour gating, run-level
failure isolation, rendering for all three templates, and the HTTP surface.
