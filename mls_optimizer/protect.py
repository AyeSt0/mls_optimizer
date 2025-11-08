
import re
from typing import List, Tuple

PLACEHOLDER_RE = re.compile(r"(\[[^\]]+\]|\{[^}]+\}|\$\{[^}]+\}|%[sd]|<[^>]+>)")

def _escape(s: str) -> str:
    return s.replace("\\","\\\\")

def protect_segments(text: str, brands: List[str]) -> (str, List[Tuple[str,str]]):
    """Replace placeholders & brands with tokens to avoid LLM tampering."""
    repl = []
    out = text

    # Protect placeholders
    def ph_sub(m):
        token = f"__PH_{len(repl)}__"
        repl.append((token, m.group(0)))
        return token
    out = PLACEHOLDER_RE.sub(ph_sub, out)

    # Protect brands (case-sensitive exact words)
    for b in brands or []:
        b_esc = re.escape(b)
        out, n = re.subn(rf"\b{b_esc}\b", lambda _: repl.append((t:=f"__BR_{len(repl)}__", b)) or t, out)
    return out, repl

def unprotect_segments(text: str, repl: List[Tuple[str,str]]) -> str:
    out = text
    # restore in reverse
    for token, val in reversed(repl):
        out = out.replace(token, val)
    return out

def _compile_boundary_regex(src: str):
    return re.compile(rf"(?<!\w){re.escape(src)}(?!\w)")
