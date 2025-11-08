
import os, json, time
from typing import Set, Optional

class Checkpointer:
    """
    JSONL-based simple checkpointer for per-row progress.
    Each line: {"row": int, "ts": float, "info": {...}}
    """
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._processed: Set[int] = set()
        self._last_row = -1
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln: continue
                        try:
                            obj = json.loads(ln)
                        except Exception:
                            continue
                        r = obj.get("row")
                        if isinstance(r, int):
                            self._processed.add(r)
                            if r > self._last_row:
                                self._last_row = r
            except Exception:
                pass

    @property
    def processed(self) -> Set[int]:
        return self._processed

    @property
    def last_row(self) -> int:
        return self._last_row

    def mark(self, row: int, info: Optional[dict]=None):
        self._processed.add(row)
        self._last_row = max(self._last_row, row)
        payload = {"row": int(row), "ts": time.time()}
        if info: payload["info"] = info
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
