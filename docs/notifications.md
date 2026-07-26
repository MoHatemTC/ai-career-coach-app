# Daily Top Job Match Notifications

Sends each user their top 3 job matches automatically, once a day, without
them running a search. WhatsApp (via Postpeer) is the primary channel; email
is the fallback.

Covers PRD 6.4 (notification flow), 7.8 (notifications), 7.9 (S) (don't
re-notify about jobs already seen), and 10.2.4 (automation & notification
service).

---

## 1. How it fits together

```
                    hourly tick
  scheduler.py  ─────────────────►  dispatcher.run_daily_dispatch()
  (APScheduler)                            │
                                           │ for each notifiable user
                                           ▼
                              matching_bridge.get_top_matches()
                                           │  ← calls the EXISTING
                                           │    features/matching/scorer.py
                                           ▼
                                  renderer.py (Jinja templates)
                                           │
                                           ▼
                        providers/  postpeer ──fails/unset──► smtp
                                           │
                                           ▼
                                  NotificationLogORM
```

| File | Responsibility |
|---|---|
| `backend/features/notifications/scheduler.py` | APScheduler trigger |
| `backend/features/notifications/dispatcher.py` | Per-user orchestration, idempotency |
| `backend/features/notifications/matching_bridge.py` | Top-N selection via the existing scorer |
| `backend/features/notifications/renderer.py` + `templates/` | Message bodies |
| `backend/features/notifications/providers/` | Delivery adapters |
| `backend/features/notifications/settings_service.py` | Contact-settings CRUD |
| `backend/features/notifications/routes.py` | HTTP surface (`/notifications`) |
| `frontend/src/pages/1_Notification_Settings.py` | The settings tab |

---

## 2. Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in the values below

# Terminal 1 — API
uvicorn backend.main:app --reload

# Terminal 2 — settings UI
streamlit run frontend/src/streamlit_app.py
```

Open <http://localhost:8501>, go to **Notification Settings**, create a user,
save an email and phone, then use **Preview matches** and **Send test digest**.

With no `EMAIL_HOST` set, digests print to the API console instead of sending
(`EMAIL_CONSOLE_FALLBACK=true`). That is enough to demo the whole pipeline
without any credentials.

### Turning the schedule on

```env
NOTIFICATIONS_SCHEDULER_ENABLED=true
```

It is **off by default** so that local dev and CI never send real messages.

---

## 3. Why the scheduler ticks hourly

Each user picks their own `send_hour_local` in their own `timezone`. A single
daily fire would deliver at the same instant worldwide, which is the wrong
local time for everyone outside the server's zone.

So the trigger runs every hour, and only users whose local hour matches right
now are sent to. Twenty-four ticks do not produce twenty-four digests because
the dispatcher enforces one digest per user per **local calendar day** — the
key is `(user_id, channel, sent_on_local_date)`, not a UTC timestamp.

Running the API with multiple uvicorn workers gives each worker its own
scheduler. The idempotency check makes that safe rather than catastrophic, but
the correct setup is a single scheduler process:

```bash
python scripts/run_scheduler.py
```

---

## 4. Channel fallback

`build_provider_chain()` returns `[Postpeer(whatsapp), Smtp(email)]`. The
dispatcher walks it and **stops at the first success** — a user gets one
message, not two. It moves to the next channel when:

* the provider is not configured (no credentials in `.env`), or
* the user disabled that channel or has no address for it, or
* the send returns a failure or raises.

Every attempt, successful or not, is written to `notification_logs`.

---

## 5. API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/notifications/users` | Create or replace a user |
| `GET` | `/notifications/users` | List users |
| `GET` | `/notifications/users/{id}` | Fetch one user |
| `PATCH` | `/notifications/users/{id}/settings` | Partial settings update (what the form sends) |
| `PUT` | `/notifications/users/{id}/profile` | Refresh matching inputs |
| `DELETE` | `/notifications/users/{id}` | Delete a user (PRD 9 user control) |
| `GET` | `/notifications/users/{id}/preview` | Top 3 without sending |
| `POST` | `/notifications/users/{id}/send-test` | Send now, ignoring the daily guard |
| `POST` | `/notifications/dispatch` | Run the whole digest on demand |
| `GET` | `/notifications/providers` | Which channels are configured |
| `GET` | `/notifications/scheduler` | Scheduler state and next run |
| `GET` | `/notifications/logs` | Recent delivery attempts |

Example — save contact settings:

```bash
curl -X PATCH http://localhost:8000/notifications/users/menna/settings \
  -H 'Content-Type: application/json' \
  -d '{"email":"menna@example.com","phone":"+20 100 123 4567","min_match_score":50}'
```

Phone numbers are normalized to E.164 on write (`+201001234567`), because
WhatsApp providers reject other formats — sometimes silently.

---

## 6. Open coordination items

These are the parts that need another person's confirmation. Each one is
marked in code at the place it matters.

### 6.1 Mohamed Farag — confirm the pipeline output schema

`backend/features/notifications/schema.py`

The repo currently has **two** `JobPosting` models:

| Model | Fields | Used by |
|---|---|---|
| `backend/models/job.py` | `skills`, `work_mode`, `source`, `url`, `date` | ingestion |
| `backend/models/job_posting.py` | `required_skills`, `min_experience`, `work_type`, `salary: int` | matching |

`job.py` calls itself "THE shared job schema" and warns that duplicates "have
already caused field-name drift between lanes once". The digest is built
against **`job.py`**, and `matching_bridge.py` translates so the matching lane
did not have to change.

If Mohamed confirms a different final shape, `matching_bridge.py` is the only
file to change.

### 6.2 Eng. Sara — confirm the Postpeer contract

`backend/features/notifications/providers/postpeer.py`

There was no notification code anywhere in the repo or its history when this
lane started, so there was nothing to build on and no vendor contract to copy.
Every Postpeer-specific value is therefore an environment variable. Needed:

1. Base URL + send path
2. Auth scheme (bearer / custom header / query param)
3. JSON field names for recipient, body, sender
4. Where the message id sits in the response

**Raise early:** on the official WhatsApp Business Platform, a business-initiated
message outside the 24-hour service window must use a **pre-approved template**;
free-form text is rejected. A daily unprompted digest is business-initiated. So
unless Postpeer resells a number under its own approved template, a template
must be submitted and approved before WhatsApp can deliver anything. That
approval lead time is the most likely reason this channel is "not feasible" —
which is why the email fallback is a real implementation, not a stub.

Set `POSTPEER_TEMPLATE_NAME` once approved.

### 6.3 Omar Zahran — backend/UI integration

* **Auth.** There is none yet, so the settings page picks the user from a
  dropdown. When auth lands, replace `_select_user()` in
  `frontend/src/pages/1_Notification_Settings.py` — nothing else changes.
* **`POST /notifications/dispatch` is unauthenticated** and sends real
  messages to every user. Gate it before any public deploy.
* **CORS is `allow_origins=["*"]`** in `backend/main.py` for local Streamlit.
  Restrict it before deploying.
* **Profile source.** The matching snapshot currently lives on the `users`
  table. If a dedicated profile table lands, repoint `UserRead.to_profile()`
  in `backend/models/user.py` — it is the only seam.
* **CV upload.** `/upload` parses a CV but stores nothing. Calling
  `settings_service.update_profile_snapshot()` after parsing would make the
  digest score against the user's newest CV automatically.

---

## 7. Testing

```bash
pytest backend/tests/test_notifications.py -q
```

36 tests covering contact-settings validation, top-3 selection, threshold
filtering, canonical-schema output, de-duplication, WhatsApp→email fallback,
provider failure isolation, once-per-day idempotency, timezone-correct local
dates, and rendering.

The scorer is stubbed in tests — it builds a SentenceTransformer at import and
downloads ~90MB of weights. What needs testing here is the logic around the
score, not the embedding maths.

---

## 8. Known gaps

* **Scoring cost.** `calculate_match_score()` re-encodes the profile text on
  every call, so a run is O(users × jobs) encodes. The candidate pool is
  capped at 200 recent postings to bound it. A batch entry point in
  `scorer.py` would fix it properly — that file belongs to the matching lane.
* **`reason` is always `None`.** The templates render a fit explanation when
  present; `feat/match-explanation-agent` looks like it will supply it.
* **No unsubscribe token.** The footer links to the settings page, which is
  fine while there is no auth, but a real one-click unsubscribe needs a signed
  token.
* **No retry.** A failed send is logged, not retried; the user gets the next
  day's digest. Retry belongs with a task queue, not this scheduler.
