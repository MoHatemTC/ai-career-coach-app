"""Daily top-3 job-match digest delivery.

This package is the *sending* half of notifications. The *storing* half —
`POST/GET /notifications/settings`, Contract 6 — stays in
`backend/routes/notifications.py`, unchanged, because other lanes already read
it and the frontend already writes it.

Module map:
    schema.py           wire types (TopJobMatch, DigestPayload, ...)
    settings_service.py reads the notification_settings row into a recipient
    matching_bridge.py  calls the existing matching pipeline, returns top N
    renderer.py         payload -> email / WhatsApp bodies
    providers/          delivery adapters (Postpeer WhatsApp, SMTP email)
    dispatcher.py       per-user orchestration, idempotency, logging
    scheduler.py        APScheduler hourly trigger
    routes.py           HTTP surface for dispatch and diagnostics

See docs/notifications.md for setup and the outstanding coordination items.
"""
