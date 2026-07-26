"""Daily top-3 job-match notifications.

Module map:
    schema.py           wire types (TopJobMatch, DigestPayload, ...)
    settings_service.py user + contact settings CRUD
    matching_bridge.py  calls the existing matching pipeline, returns top N
    renderer.py         payload -> email / WhatsApp bodies
    providers/          delivery adapters (Postpeer WhatsApp, SMTP email)
    dispatcher.py       per-user orchestration, idempotency, logging
    scheduler.py        APScheduler hourly trigger
    routes.py           HTTP surface, mounted at /notifications

See docs/notifications.md for setup and the outstanding coordination items.
"""
