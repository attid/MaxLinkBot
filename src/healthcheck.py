"""Container healthcheck entrypoint."""

from __future__ import annotations

import os
import sys

from src.application.health.service import RuntimeHealthTracker


def main() -> int:
    tracker = RuntimeHealthTracker(
        marker_path=os.environ.get("RUNTIME_UNHEALTHY_MARKER_PATH", "/tmp/maxlinkbot.unhealthy"),
        heartbeat_path=os.environ.get("RUNTIME_HEARTBEAT_PATH", "/tmp/maxlinkbot.heartbeat"),
        heartbeat_stale_after_seconds=float(
            os.environ.get("RUNTIME_HEARTBEAT_STALE_AFTER_SECONDS", "180")
        ),
    )
    return 0 if tracker.is_healthy() else 1


if __name__ == "__main__":
    raise SystemExit(main())
