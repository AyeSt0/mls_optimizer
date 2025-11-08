
import time, math, asyncio
from typing import Optional

class AutoTuner:
    """
    Simple concurrency auto-tuner.
    - Start with workers; increases on smooth batches; decreases on rate limits/timeouts.
    - Backoff with exponential delay on bursty 429s.
    """
    def __init__(self, min_workers=2, max_workers=8, start_workers=None, rpm_hint: Optional[int]=None):
        self.min_workers = max(1, int(min_workers))
        self.max_workers = max(self.min_workers, int(max_workers))
        self.workers = int(start_workers or self.min_workers)
        self.rpm_hint = rpm_hint or 60
        self.last_error_ts = 0.0
        self.consec_errors = 0
        self.consec_success = 0

    def on_success_batch(self):
        self.consec_success += 1
        self.consec_errors = 0
        # gentle increase every couple batches
        if self.consec_success >= 2 and self.workers < self.max_workers:
            self.workers += 1
            self.consec_success = 0

    def on_error_batch(self):
        self.consec_errors += 1
        self.consec_success = 0
        if self.workers > self.min_workers:
            self.workers = max(self.min_workers, self.workers - 1)
        self.last_error_ts = time.time()

    async def backoff_sleep(self):
        # backoff grows with consecutive errors, but capped by RPM hint
        base = 1.0 if self.rpm_hint >= 60 else 60.0 / max(1, self.rpm_hint)
        delay = min(20.0, base * (2 ** min(4, self.consec_errors-1)))
        await asyncio.sleep(delay)

    def snapshot(self):
        return {"workers": self.workers, "consec_errors": self.consec_errors, "consec_success": self.consec_success}
