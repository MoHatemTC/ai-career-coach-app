"""Run the notification scheduler as its own process.

Use this instead of the in-app scheduler when the API runs with more than one
worker. `uvicorn --workers N` starts N independent processes, each of which
would start its own `BackgroundScheduler` and fire its own tick. The
dispatcher's per-user per-local-day idempotency check makes that safe rather
than catastrophic — the second worker finds a "sent" row and skips — but it is
N times the work and it depends on a race being lost gracefully. One scheduler
process and `NOTIFICATIONS_SCHEDULER_ENABLED=false` on the API is the setup that
does not rely on that.

    python scripts/run_scheduler.py

Reads the same .env as the API, and honours NOTIFICATIONS_SCHEDULER_ENABLED —
so this script refuses to run rather than surprising anyone who has the feature
deliberately switched off.

Ctrl-C shuts down cleanly; an in-flight digest is not waited on.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Running this file directly puts scripts/ on sys.path, not the repo root, so
# `import backend...` fails. Added before any backend import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from backend.features.notifications.scheduler import (  # noqa: E402
    scheduler_enabled,
    shutdown_scheduler,
    start_scheduler,
)
from backend.services.database import init_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("run_scheduler")


def main() -> int:
    if not scheduler_enabled():
        logger.error(
            "NOTIFICATIONS_SCHEDULER_ENABLED is not true — refusing to start. "
            "Set it in .env if you actually want digests delivered."
        )
        return 1

    init_db()
    scheduler = start_scheduler()
    if scheduler is None:
        logger.error("Scheduler failed to start.")
        return 1

    logger.info(
        "Scheduler running. Digests deliver at each user's local send hour "
        "(tick: minute %s of every hour, UTC). Ctrl-C to stop.",
        os.getenv("NOTIFICATIONS_TICK_MINUTE", "0"),
    )
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping.")
    finally:
        shutdown_scheduler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
