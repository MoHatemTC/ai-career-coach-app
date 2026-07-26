"""Run the notification scheduler as its own process.

Use this instead of the in-app scheduler when the API runs with more than one
uvicorn worker — otherwise every worker starts its own scheduler and the job
fires once per worker (see the scaling note in
backend/features/notifications/scheduler.py).

    python scripts/run_scheduler.py

Honours the same environment variables as the API, including
NOTIFICATIONS_SCHEDULER_ENABLED, which must be "true" for this to do anything.
"""

import logging
import signal
import sys
import time
from pathlib import Path

# Allow `python scripts/run_scheduler.py` from the repo root without an
# editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.features.notifications.scheduler import (  # noqa: E402
    scheduler_enabled,
    shutdown_scheduler,
    start_scheduler,
)
from backend.services.database import init_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler-process")


def main() -> int:
    if not scheduler_enabled():
        logger.error(
            "NOTIFICATIONS_SCHEDULER_ENABLED is not 'true' — refusing to start. "
            "Set it in .env to run the daily digest."
        )
        return 1

    init_db()
    scheduler = start_scheduler()
    if scheduler is None:
        logger.error("Scheduler failed to start")
        return 1

    stopping = False

    def _handle_signal(signum, _frame):
        nonlocal stopping
        logger.info("Received signal %s — shutting down", signum)
        stopping = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Scheduler process running. Ctrl-C to stop.")
    try:
        while not stopping:
            time.sleep(1)
    finally:
        shutdown_scheduler()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
