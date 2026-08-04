# Where email and phone are captured and persisted

**For:** Fady Adel, notifications lane
**From:** Omar Zahran, pipeline / UI orchestration
**Status:** current as of the React frontend migration

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
| `relevance_threshold` | Float, nullable | 0.0 to 1.0 |
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

## 5. What is not built

So you are not waiting on something that does not exist:

- **No scheduler.** Nothing runs daily. The frequency field is stored and
  honoured by nobody. The pipeline plan puts a 9am daily job in your lane.
- **Nothing is ever sent.** "Trigger now" on the settings page builds the digest
  and renders it in the browser. There is no email or WhatsApp call anywhere in
  this codebase.
- **`user_id` is always `"default"`.** There is no auth and no session concept
  yet, so every browser writes the same row. When auth arrives this is the seam
  it plugs into.

---

## 6. The digest payload

If you want the same content the UI shows, rather than building your own:

`buildRecommendations` in `frontend/src/services/api.ts`, mirrored from
`streamlit_app/digest.py::build_notification_recommendations`. It takes the
matching pipeline's output and returns at most **three** entries:

```json
[{ "job_title": "Backend Engineer", "company": "Acme", "url": "https://…" }]
```

Three because a digest is a nudge, not a job board.

**This logic is currently client-side in both frontends**, which means a
scheduler cannot reach it. PR 1 of `docs/frontend-migration-plan.md` promotes it
to a backend router, and that is the piece you will want. Worth telling me if
you need it sooner than that, because it is a small change and I would rather
do it than have you reimplement it and have the two drift.

Until then, the source of truth for what a notification should contain is
`POST /matching/pipeline`, take the first three of `ranked`.

---

## Questions

Anything unclear or missing, message me rather than working around it. If you
need a field the contract does not carry, that is a change to
`NotificationSettingsIn` / `Out` and I would rather make it once than have both
lanes guessing.
