"""
Global configuration for the notification scheduler.
"""

# -----------------------------
# Scheduler Configuration
# -----------------------------

# True  -> Run every TEST_INTERVAL_MINUTES
# False -> Run every day at NOTIFICATION_TIME
TEST_MODE = True

# Used only when TEST_MODE=True
TEST_INTERVAL_MINUTES = 2

# Used only when TEST_MODE=False
NOTIFICATION_TIME = "09:00"