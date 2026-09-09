"""Cooperative cooling at inference batch boundaries; no discarded progress."""
import json
import os
from pathlib import Path
import time


class GpuController:
    def __init__(self):
        self.paused = False

    def update(self, reading):
        if reading is None:
            self.paused = True
        elif self.paused:
            # Hysteresis prevents rapidly alternating pause/resume at 78 C.
            self.paused = not (reading["temperature_c"] <= 74 and reading["power_w"] <= 65)
        else:
            self.paused = reading["temperature_c"] >= 78 or reading["power_w"] >= 80
        warm = reading is not None and (reading["temperature_c"] >= 75 or reading["power_w"] >= 70)
        return {"paused": self.paused, "extra_delay": 0.06 if warm else 0.0,
                "updated_at": time.time()}


def write_control(path, state):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    # Windows may briefly deny replacement while the worker has the file open.
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)


def wait_for_gpu(path):
    """Block between batches until fresh telemetry permits more work."""
    while True:
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
            fresh = time.time() - state["updated_at"] <= 10
            if fresh and not state["paused"]:
                time.sleep(state.get("extra_delay", 0))
                return
        except (OSError, ValueError, KeyError):
            pass  # Missing/stale telemetry pauses inference instead of running blind.
        time.sleep(0.1)
