# Notifications Feature

Delivers each user's top 3 job matches once a day, unprompted.

## Design

- **Trigger:** APScheduler, ticking hourly. Each user has their own
  `send_hour_local` + `timezone`, so an hourly tick is what lets a user in
  Cairo and a user in London both get theirs at 8am *local*.
- **Selection:** reuses `features/matching/scorer.calculate_match_score` —
  the digest must never disagree with what `/matching/rank-jobs` shows.
  Selection order: recency cap (200 newest) → drop jobs sent in the last 7
  days → score → drop below the user's `min_match_score` → take top 3.
- **Payload schema:** the canonical `backend/models/job.py` `JobPosting`, not
  `backend/models/job_posting.py`. See `schema.py` for why, and for the item
  to confirm with Mohamed Farag.
- **Delivery:** provider chain, WhatsApp (Postpeer) then email (SMTP). Stops
  at the first success — fallback, not fan-out.
- **Idempotency:** one digest per user per local calendar day, keyed on
  `(user_id, channel, sent_on_local_date)`. A UTC timestamp alone would let a
  user in UTC+2 get two digests on the same local day.

## Defaults

| Setting | Default | Why |
|---|---|---|
| `min_match_score` | 40.0 | Below the matching lane's 50% "potential candidate" bar, because a digest is a suggestion, not a shortlist. User-adjustable. |
| Top N | 3 | Per the task brief. |
| De-dupe window | 7 days | PRD 7.9 (S) — don't re-notify about jobs already seen. |
| Candidate pool | 200 newest | Bounds a nightly run; a *daily* digest is about fresh postings anyway. |
| Scheduler | **off** | So local dev and CI never send real messages. |

Full setup, API reference, and open coordination items: `docs/notifications.md`.
