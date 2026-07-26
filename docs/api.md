# API Documentation

API endpoints should be documented here as they are created.

For each endpoint, include:

- Method and path.
- Purpose.
- Request body example.
- Response example.
- Error cases.

## Example Format

```txt
POST /cvs/upload

Purpose:
Upload a CV file for parsing.

Request:
multipart/form-data with a file field named cv.

Response:
JSON profile draft.
```

---

## Notifications

Full reference, setup, and open coordination items: [`notifications.md`](notifications.md).

### Settings

```txt
PATCH /notifications/users/{user_id}/settings

Purpose:
Update a user's contact details and delivery preferences. Partial update —
fields that are omitted are left unchanged; fields sent as null are cleared.
This is what the settings tab submits.

Request:
{
  "email": "menna@example.com",
  "phone": "+20 100 123 4567",
  "notifications_enabled": true,
  "notify_via_whatsapp": true,
  "notify_via_email": true,
  "min_match_score": 50.0,
  "send_hour_local": 8,
  "timezone": "Africa/Cairo"
}

Response:
The full user record. `phone` comes back normalized to E.164
("+201001234567") because WhatsApp providers reject other formats.

Errors:
404 — unknown user_id.
422 — malformed email, unusable phone number, unknown IANA timezone, or
      min_match_score outside 0-100.
```

### Preview

```txt
GET /notifications/users/{user_id}/preview?top_n=3&include_recent=false

Purpose:
Return exactly what the next digest would contain, without sending anything.

Response:
[
  {
    "job": { ...canonical JobPosting from backend/models/job.py... },
    "match_score": 87.4,
    "reason": null
  }
]

Notes:
`include_recent=false` (the default) hides jobs already sent in the last
7 days. `reason` is reserved for the match-explanation lane.

Errors:
404 — unknown user_id.
```

### Dispatch

```txt
POST /notifications/dispatch?dry_run=false&force=false&respect_send_hour=false

Purpose:
Run the digest across all notifiable users on demand. The scheduler calls the
same code path with respect_send_hour=true.

Response:
{
  "run_started_at": "...", "run_finished_at": "...",
  "users_considered": 12, "users_notified": 9,
  "users_skipped_no_contact": 1, "users_skipped_already_sent": 2,
  "users_skipped_no_matches": 0,
  "deliveries": [...], "errors": []
}

Warning:
Unauthenticated, and it sends real messages to every user. Must be gated
before any public deployment.
```

### Diagnostics

```txt
GET /notifications/providers   — which channels are configured right now
GET /notifications/scheduler   — scheduler state and next run time
GET /notifications/logs        — recent delivery attempts, filterable by user_id
```

Check `/notifications/providers` first when a digest does not arrive.
