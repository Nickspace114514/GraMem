"""Pacing for background polling. Kept free of Hermes host imports so it is testable alone."""

import random

FAILURE_LOG_INTERVAL = 60.0
POLL_INTERVAL = 1.0
MAX_POLL_DELAY = 30.0


def poll_delay(failures, rand=random.random):
    """Seconds to wait before the next background poll.

    Jitter spreads pollers that start together; consecutive failures back off
    exponentially so a stuck database is not hammered by every provider at once.
    """
    base = min(MAX_POLL_DELAY, POLL_INTERVAL * 2 ** min(max(failures, 0), 6))
    return base * (1 + 0.5 * rand())
