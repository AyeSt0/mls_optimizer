
import time
from threading import Lock

class TokenBucket:
    def __init__(self, rpm: int = 60):
        self.capacity = max(1, rpm)
        self.tokens = self.capacity
        self.fill_rate = self.capacity / 60.0
        self.timestamp = time.time()
        self.lock = Lock()

    def consume(self, cost: float = 1.0):
        with self.lock:
            now = time.time()
            elapsed = now - self.timestamp
            self.timestamp = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            if self.tokens < cost:
                need = cost - self.tokens
                delay = need / self.fill_rate
                time.sleep(delay)
                self.tokens = 0
            else:
                self.tokens -= cost
