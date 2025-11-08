
import re, pandas as pd

PLACEHOLDER_PATTERNS = [r"\[[^\]]+\]", r"\{[^}]+\}", r"\<[^>]+\>", r"%\w", r"\$\{[^}]+\}"]
URL_PATTERN = r"https?://\S+"
AT_PATTERN = r"(?<!\w)@\w+"
HASH_PATTERN = r"(?<!\w)#\w+"
NUMBER_PATTERN = r"[-+]?\d+(?:\.\d+)?"

def _findall(patterns, text):
    s = set()
    for p in patterns:
        s |= set(re.findall(p, text or ""))
    return s

def check_placeholders(en, out):
    a = _findall(PLACEHOLDER_PATTERNS, en or "")
    b = _findall(PLACEHOLDER_PATTERNS, out or "")
    return (a == b), f"placeholders {a} -> {b}"

def check_urls_mentions(en, out):
    ue = set(re.findall(URL_PATTERN, en or "")) | set(re.findall(AT_PATTERN, en or "")) | set(re.findall(HASH_PATTERN, en or ""))
    uo = set(re.findall(URL_PATTERN, out or "")) | set(re.findall(AT_PATTERN, out or "")) | set(re.findall(HASH_PATTERN, out or ""))
    return (ue == uo), f"links/mentions {ue} -> {uo}"

def check_numbers(en, out):
    ne = set(re.findall(NUMBER_PATTERN, en or ""))
    no = set(re.findall(NUMBER_PATTERN, out or ""))
    return (ne == no), f"numbers {ne} -> {no}"

def length_ratio(en, out, lo=0.3, hi=3.0):
    le = len(en or "")
    lo_ = len(out or "")
    if le == 0 and lo_ == 0: return True, "empty both"
    if le == 0: return False, "EN empty but OUT non-empty"
    r = lo_ / le
    return ((r >= lo) and (r <= hi)), f"len_ratio={r:.2f}"

def run_qa(df: pd.DataFrame, col_en: int, col_out: int) -> pd.DataFrame:
    rows = []
    for i, row in df.iterrows():
        en = "" if pd.isna(row.iloc[col_en]) else str(row.iloc[col_en])
        out = "" if pd.isna(row.iloc[col_out]) else str(row.iloc[col_out])
        issues = []
        for fn in (check_placeholders, check_urls_mentions, check_numbers):
            ok, msg = fn(en, out)
            if not ok: issues.append(msg)
        ok_len, msg_len = length_ratio(en, out)
        if not ok_len: issues.append(msg_len)
        rows.append({"row_index": i, "en": en, "out": out, "issues": " | ".join(issues), "has_issue": bool(issues)})
    return pd.DataFrame(rows)
