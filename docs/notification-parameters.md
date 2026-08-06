# Where email and phone are captured and persisted

**For:** Fady Adel, notifications lane
**From:** Omar Zahran, pipeline / UI orchestration
**Status:** current as of the delivery integration

> **Update:** delivery is now built. Sections 1-4 below still describe how
> contact details are captured and stored and are unchanged; section 5 has been
> rewritten, because everything it said was missing now exists. The sending side
> is documented in [notifications.md](notifications.md).

This is the integration contract for the two user parameters the notification
features depend on. Nothing here needs the UI running: the values are in SQLite
and readable over HTTP.

---

## The short version

| | |
|---|---|
| Captured in | `frontend/src/pages/SettingsPage.tsx`, the Notification settings form |
| Written by | `POST /notifications/settings` |
| Read by you | `GET /notifications/settings/{user_id}` |
| Stored in | SQLite, table `notification_settings` |
| Key | `user_id`, a string primary key. The UI currently always sends `"default"` |

There is exactly one writer and one reader. No other screen persists contact
details.

---

## 1. Where the user types them

`frontend/src/pages/SettingsPage.tsx`, the "Notification settings" card:

- **Email** is a `type="email"` field, labelled "Where the daily digest goes."
- **Phone (WhatsApp)** is a free-text field, placeholder `+20…`

Submitting calls `saveNotificationSettings` in
`frontend/src/services/api.ts`, which is the only function in the app that
writes contact details.

### One thing to be careful about

The CV profile form on `/app/upload` **also** shows email and phone, parsed out
of the uploaded CV. **Those are not persisted anywhere.** They live in browser
session state, feed the matching pipeline, and are discarded when the tab
closes. The field there is labelled to say so.

If you read a contact address, read it from `notification_settings`. A value
parsed off a CV has not been confirmed by anyone and may well be a former
employer's address.

---

## 2. The API shape

### Writing

`POST /notifications/settings`

```json
{
  "user_id": "default",
  "contact": {
    "email": "someone@example.com",
    "phone_whatsapp": "+201234567890"
  },
  "notification_channels": ["email", "whatsapp"],
  "frequency": "daily",
  "relevance_threshold": 0.75
}
```

Contact is **nested** under `contact`. A flat `{"email": ..., "phone": ...}`
body is still accepted for backwards compatibility, and the route resolves
whichever is present via `resolved_email()` / `resolved_phone()`.

The write is an upsert on `user_id`. An **omitted** preference keeps whatever is
already stored rather than blanking it, so a contact-only save cannot silently
reset the channel list.

### Reading, which is what you want

`GET /notifications/settings/{user_id}` returns `NotificationSettingsOut`:

```json
{
  "user_id": "default",
  "contact": {
    "email": "someone@example.com",
    "phone_whatsapp": "+201234567890"
  },
  "notification_channels": ["email"],
  "frequency": "daily",
  "relevance_threshold": 0.75
}
```

**404 means nothing has been saved yet.** That is a normal first-run state, not
an error. The frontend treats it as "no settings" and shows an empty form; a
scheduler should treat it as "no one to notify for this user" and move on.

Both fields are nullable. Someone can save a threshold without ever entering an
email, so check before sending rather than assuming presence.

---

## 3. The storage layer

`backend/models/db_models.py`, class `NotificationSettings`,
table `notification_settings`:

| Column | Type | Notes |
|---|---|---|
| `user_id` | String | Primary key |
| `email` | String, nullable | |
| `phone` | String, nullable | **The contract calls this `phone_whatsapp`; the column is `phone`.** The shorter name was kept so existing rows were unaffected |
| `notification_channels` | Text, nullable | **JSON-encoded list**, e.g. `'["email"]'`. SQLite has no array type |
| `frequency` | String, nullable | `daily` or `weekly` |
| `relevance_threshold` | Float, nullable | 0.0 to 1.0. **Compared against a 0-100 match score**, so 0.75 means "at least 75" |
| `full_name` | String, nullable | How the digest greets the user |
| `send_hour_local` | Integer, nullable | 0-23, local delivery hour |
| `timezone` | String, nullable | IANA name; validated on write |
| `profile_snapshot` | Text, nullable | **JSON-encoded profile dict.** The matching input, since a scheduled send has no browser session to read one from |
| `updated_at` | DateTime | Server default now, updated on write |

Two traps if you query the table directly rather than going through the API:

1. **`notification_channels` is a JSON string, not a list.** `json.loads` it.
   The route does this in `_to_contract` and falls back to `[]` on a decode
   error rather than raising.
2. **The column is `phone`, the API field is `phone_whatsapp`.** The nesting and
   the rename are applied at the route boundary, not in the schema.

Going through the API avoids both. I would read over HTTP unless you have a
reason not to.

---

## 4. Defaults

Applied on write when a field has never been set
(`backend/routes/notifications.py`):

- `notification_channels` → `["email"]`
- `frequency` → `daily`
- `relevance_threshold` → `0.75`

Note the channel default is email only. The PRD specifies email for v1;
WhatsApp is storable because the UI offers it, but whether it is honoured is
your lane's decision, not something the UI enforces.

---

## 5. What is built now

This section used to say "no scheduler, nothing is ever sent". Both are done.

- **There is a scheduler.** APScheduler, ticking hourly, delivering to each user
  at their own local `send_hour_local`. It is **off by default** —
  `NOTIFICATIONS_SCHEDULER_ENABLED=true` turns it on.
- **Messages are sent.** WhatsApp via Postpeer, falling back to email over SMTP,
  in `backend/features/notifications/providers/`. With no SMTP host configured
  the digest prints to the API console, so the whole path is demoable without
  credentials.
- **`frequency` is honoured.** `weekly` means seven days between digests.
- **`relevance_threshold` is honoured.** Note the unit: it is stored 0-1 and
  compared against a 0-100 match score, so `0.75` means "at least 75".
- **Three fields were added to this contract** — `full_name`, `send_hour_local`,
  `timezone` — because a scheduled send has no browser session to ask who the
  user is or when their morning is. They are additive: omit them on write and
  what is stored is kept; ignore them on read and nothing changes for you.

Still true:

- **`user_id` is always `"default"`.** There is no auth and no session concept
  yet, so every browser writes the same row. When auth arrives this is the seam
  it plugs into.
- **`POST /notifications/dispatch` is unauthenticated** and sends real messages
  to every user. Gate it before any public deploy.

---

## 6. The digest payload

This used to be client-side, which meant a scheduler could not reach it. It is
now a backend endpoint:

```
GET /notifications/preview/{user_id}
```

returns exactly what the next digest would contain — the same selection code
the real send uses, so the preview and the message cannot drift. Each entry is
`{job, match_score, reason}` where `job` is the canonical `JobPosting`.

Three entries, because a digest is a nudge, not a job board.

The selection itself is `matching_bridge.get_top_matches`, which calls
`run_match_pipeline` and falls back to the scorer when Qdrant is unavailable.
See [notifications.md §3](notifications.md).

---

## Questions

Anything unclear or missing, message me rather than working around it. If you
need a field the contract does not carry, that is a change to
`NotificationSettingsIn` / `Out` and I would rather make it once than have both
lanes guessing.
