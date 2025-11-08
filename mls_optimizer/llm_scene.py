
import asyncio, time
from typing import Dict, List, Callable, Optional
from tqdm import tqdm
from .adaptive import AutoTuner

async def _run_sem(sem, coro):
    async with sem:
        return await coro

async def _call_with_retry(fn, *, is_scene: bool, tuner: AutoTuner, quiet: bool):
    # fn must be an async function that returns the translation (string for line mode, list[str] for scene mode)
    tries = 0
    while True:
        tries += 1
        try:
            return await fn()
        except Exception as e:
            msg = str(e).lower()
            # crude detection of rate/timeout from SDKs/gateways
            is_rate = ("rate" in msg and "limit" in msg) or "429" in msg or "too many requests" in msg
            is_timeout = "timeout" in msg or "timed out" in msg
            if is_rate or is_timeout:
                if not quiet:
                    print(f"[autotune] batch error ({'rate' if is_rate else 'timeout'}): {e}")
                tuner.on_error_batch()
                await tuner.backoff_sleep()
                if tries < 6:
                    continue
            # non-retryable or too many retries
            if not quiet:
                print(f"[warn] giving up after {tries} tries: {e}")
            raise

async def translate_lines_adaptive(items: List[Dict], translator, *, start_workers=6, min_workers=2, max_workers=12, rpm_hint=60, quiet=False) -> List[str]:
    """
    Runs in batches with dynamic concurrency. Shows a tqdm progress bar.
    """
    tuner = AutoTuner(min_workers=min_workers, max_workers=max_workers, start_workers=start_workers, rpm_hint=rpm_hint)
    total = len(items)
    outs = [None] * total
    done = 0
    bar = tqdm(total=total, desc="Translating lines", disable=quiet)

    i = 0
    while i < total:
        batch_size = min(tuner.workers, total - i)
        sem = asyncio.Semaphore(batch_size)

        async def one(idx, payload):
            def build():
                sys_prompt = payload.get("system_prompt","")
                user = []
                if payload.get("window_context"):
                    user.append("CONTEXT (nearby lines):\n"+payload["window_context"])
                user.append(f"SPEAKER: {payload.get('speaker','')}")
                user.append(f"RU: {payload.get('ru','')}")
                user.append(f"EN: {payload.get('en','')}")
                user.append("Translate to the target language.")
                content = "\n\n".join(user)
                # offload sync client to thread
                return translator.chat([{"role":"system","content":sys_prompt},{"role":"user","content":content}])

            async def call():
                return await asyncio.to_thread(build)

            out = await _call_with_retry(call, is_scene=False, tuner=tuner, quiet=quiet)
            outs[idx] = out
            bar.update(1)

        tasks = [asyncio.create_task(_run_sem(sem, one(k, items[i+k]))) for k in range(batch_size)]
        try:
            await asyncio.gather(*tasks)
            tuner.on_success_batch()
        except Exception:
            tuner.on_error_batch()
        i += batch_size

        if not quiet:
            snap = tuner.snapshot()
            bar.set_postfix_str(f"workers={snap['workers']} err={snap['consec_errors']} ok={snap['consec_success']}")
    bar.close()
    return outs

async def translate_scenes_adaptive(scene_payloads: List[Dict], translator, *, start_workers=6, min_workers=2, max_workers=8, rpm_hint=60, quiet=False) -> List[List[str]]:
    """
    Adaptive scene translation with tqdm progress (counts lines produced).
    """
    tuner = AutoTuner(min_workers=min_workers, max_workers=max_workers, start_workers=start_workers, rpm_hint=rpm_hint)
    total_lines = sum(len(s.get("rows",[])) for s in scene_payloads)
    bar = tqdm(total=total_lines, desc="Translating scenes", disable=quiet)

    outs: List[List[str]] = []
    i = 0
    total = len(scene_payloads)

    while i < total:
        batch_size = min(tuner.workers, total - i)
        sem = asyncio.Semaphore(batch_size)
        batch_outs: List[List[str]] = [[] for _ in range(batch_size)]

        async def one(pos, scene):
            def build():
                sys_prompt = scene.get("system_prompt","")
                rows = scene.get("rows", [])
                lines = []
                for pack in rows:
                    lines.append(f"[{pack['row']}] speaker={pack.get('speaker','')}\nRU: {pack.get('ru','')}\nEN: {pack.get('en','')}")
                content = (
                    "Translate each unit to target language. Return one line per row, "
                    "prefixed by [ROW <index>] then a space then the translation. Do not add extra lines.\n\n"
                    + "\n\n".join(lines)
                )
                return translator.chat([{"role":"system","content":sys_prompt},{"role":"user","content":content}])

            async def call():
                return await asyncio.to_thread(build)

            text = await _call_with_retry(call, is_scene=True, tuner=tuner, quiet=quiet)
            lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
            batch_outs[pos] = lines
            # optimistic progress: update by expected rows; if model returns fewer lines, still advance
            bar.update(len(scene.get("rows", [])))

        tasks = [asyncio.create_task(_run_sem(sem, one(k, scene_payloads[i+k]))) for k in range(batch_size)]
        try:
            await asyncio.gather(*tasks)
            tuner.on_success_batch()
        except Exception:
            tuner.on_error_batch()

        outs.extend(batch_outs)
        i += batch_size
        if not quiet:
            snap = tuner.snapshot()
            bar.set_postfix_str(f"workers={snap['workers']} err={snap['consec_errors']} ok={snap['consec_success']}")
    bar.close()
    return outs
