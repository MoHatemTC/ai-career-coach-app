# Notifications feature

Delivers each user's top 3 job matches once a day, unprompted.

This package is the *sending* half. The *storing* half — `POST/GET
/notifications/settings`, Contract 6 — stays in `backend/routes/notifications.py`
because another lane reads it and the frontend already writes it. Both routers
mount at `/notifications`; their paths do not overlap.

## Design

- **Trigger:** APScheduler, ticking hourly. Each user has their own
  `send_hour_local` + `timezone`, so an hourly tick is what lets a user in
  Cairo and one in London both get theirs at 8am *local*.
- **Selection:** `services/matching_pipeline.run_match_pipeline` — the same
  call `POST /matching/pipeline` makes, so the digest never disagrees with what
  the app shows. Falls back to `features/matching/scorer` when Qdrant is
  unavailable, exactly as `/matching/rank-jobs` does. Never both in one digest.
- **Profile:** read from `notification_settings.profile_snapshot`. A scheduled
  send has no browser session, so the profile has to be persisted; no snapshot
  means no digest rather than an arbitrary three jobs.
- **Delivery:** provider chain, WhatsApp (Postpeer) then email (SMTP). Stops at
  the first success — fallback, not fan-out.
- **Idempotency:** one digest per user per local calendar day, keyed on
  `sent_on_local_date`. A UTC timestamp alone would let a user in UTC+3 get two
  on the same local day.

## Defaults

| Setting | Default | Why |
|---|---|---|
| Top N | 3 | A digest is a nudge, not a job board. |
| De-dupe window | 7 days | PRD 7.9 — don't re-notify about jobs already seen. |
| Fallback candidate pool | 200 newest | Bounds a run when the scorer path is in use; a *daily* digest is about fresh postings anyway. |
| Scheduler | **off** | So local dev and CI never send real messages. |
| Email host | unset → console | The whole path is demoable without credentials. |

Full setup, API reference, and open coordination items: `docs/notifications.md`.
