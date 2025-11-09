# -*- coding: utf-8 -*-
"""
glossary_utils.py
-----------------
术语表加载 / 提示词注入短摘 / 输出侧强制替换（最长匹配优先 + 占位符/URL 保护）。
Glossary loader + prompt excerpt builder + post-LLM hard enforcement.

用法（在 12_llm_translate.py 中）：
    from scripts.glossary_utils import Glossary
    gloss = Glossary.load("data/name_map.json", target_lang="zh-CN")
    excerpt = gloss.build_prompt_excerpt(max_items=300, max_chars=4000)
    # 将 excerpt 拼到你的 system prompt 里作为“软约束”
    out_text = gloss.enforce(out_text)  # 写入第 5 列前“硬替换”兜底

支持的 name_map 形态：
1) 简单字典：{ "Professor Richardson": "理查森教授", "Patreon": "__KEEP__" }
2) 富结构：{ "Becky": {"zh-CN":"贝姬","aliases":["Rebecca","becky"]}, "Instagram":{"keep":"latin"} }
3) 列表：[{ "src":"Doctor’s Office", "dst":"医务室", "aliases":["Doctor's Office"] }, ...]

规则要点：
- 最长匹配优先（避免短词提前覆盖长词）。
- ASCII 键大小写不敏感；非 ASCII 严格匹配。
- 占位符/URL/标签会被遮罩，避免误替换：  [mcname]、{var}、{{var}}、<tag>、http(s)://…
- keep=latin / "__KEEP__"：表示保持拉丁原文（我们不会主动替换为中文）。
- 为避免“替换产物再被替换”的连锁反应，使用两段式“哨兵→回填”。
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json, re
from typing import Any, Dict, List, Optional, Tuple

# ---------- 保护与哨兵 ----------

VAR_RE  = re.compile(r"(?:\[[^\]]+\]|{[^}]+}|{{[^}]+}}|<[^>]+>)")
URL_RE  = re.compile(r"https?://\S+")
EMAIL_RE= re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MASK_RE = re.compile(r"|".join((VAR_RE.pattern, URL_RE.pattern, EMAIL_RE.pattern)))

def _mask(s: str) -> Tuple[str, List[str]]:
    """将占位符/URL/邮件遮罩为私有哨兵，返回(遮罩后文本, 还原栈)。"""
    slots: List[str] = []
    out: List[str] = []
    idx = 0
    for m in MASK_RE.finditer(s):
        out.append(s[idx:m.start()])
        token = f"\uE000{len(slots):04d}\uE001"
        out.append(token)
        slots.append(m.group(0))
        idx = m.end()
    out.append(s[idx:])
    return "".join(out), slots

def _unmask(s: str, slots: List[str]) -> str:
    for i, val in enumerate(slots):
        s = s.replace(f"\uE000{i:04d}\uE001", val)
    return s

# ---------- 术语条目 ----------

@dataclass
class Term:
    src: str                    # 源词条（键）
    dst: Optional[str] = None   # 目标译文（None 表示 keep）
    keep: bool = False          # 显式保持拉丁
    is_ascii: bool = True       # 源是否为纯 ASCII（决定是否 IGNORECASE）
    wordish: bool = False       # 是否“类单词”→ 用词边界（减少误命中）

    def compile(self) -> re.Pattern:
        pat = re.escape(self.src)
        if self.is_ascii and self.wordish:
            # 单词类（如 Chemistry / Becky）：加上词边界，避免 'car' 命中 'carry'
            pat = r"(?<!\w)" + pat + r"(?!\w)"
            return re.compile(pat, re.IGNORECASE)
        if self.is_ascii:
            return re.compile(pat, re.IGNORECASE)
        return re.compile(pat)

# ---------- 术语表 ----------

class Glossary:
    def __init__(self, terms: List[Term], target_lang: str = "zh-CN"):
        # 长 → 短 排序，避免短词先替换
        self.terms: List[Term] = sorted(terms, key=lambda t: len(t.src), reverse=True)
        self.target_lang = target_lang

    # ---- 加载 ----
    @classmethod
    def load(cls, path: str | Path, target_lang: str = "zh-CN") -> "Glossary":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entries: Dict[str, Dict[str, Any]] = {}

        def ingest(src: str, val: Any):
            if not src or not isinstance(src, str): return
            src_norm = src
            item: Dict[str, Any] = entries.get(src_norm, {"aliases": set()})
            if isinstance(val, str):
                if val.strip().lower() in ("__keep__", "keep", "latin", "__latin__"):
                    item["keep"] = True
                    item["dst"] = None
                else:
                    item["dst"] = val
            elif isinstance(val, dict):
                # 允许多语言 / dst / value / keep / aliases
                if "keep" in val and str(val["keep"]).lower() in ("true","1","latin"):
                    item["keep"] = True
                    item["dst"] = None
                # 优先取目标语言，然后尝试常见字段
                item["dst"] = val.get(target_lang) or val.get("dst") or val.get("value") or item.get("dst")
                if "aliases" in val and isinstance(val["aliases"], list):
                    for a in val["aliases"]:
                        if isinstance(a, str):
                            item["aliases"].add(a)
            entries[src_norm] = item

        if isinstance(data, dict):
            for k, v in data.items(): ingest(k, v)
        elif isinstance(data, list):
            for it in data:
                if isinstance(it, dict):
                    src = it.get("src") or it.get("key") or it.get("from")
                    if not src: continue
                    # 列表项目可直接带目标
                    val = it.get(target_lang) or it.get("dst") or it.get("value") or it
                    ingest(src, val)
                    # 别名
                    als = it.get("aliases") or []
                    if isinstance(als, list):
                        for a in als:
                            if isinstance(a, str):
                                ingest(a, val)
        else:
            raise ValueError("Unsupported name_map format. Use dict or list.")

        terms: List[Term] = []
        for src, meta in entries.items():
            dst = meta.get("dst")
            keep = bool(meta.get("keep"))
            is_ascii = all(ord(c) < 128 for c in src)
            wordish = is_ascii and re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]*[A-Za-z]", src) is not None and (" " not in src and "-" not in src and "’" not in src and "'" not in src)
            terms.append(Term(src=src, dst=dst, keep=keep, is_ascii=is_ascii, wordish=wordish))
            # 将别名也注册为独立 term（指向同一 dst/keep）
            for a in meta.get("aliases", []):
                is_ascii_a = all(ord(c) < 128 for c in a)
                wordish_a = is_ascii_a and re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]*[A-Za-z]", a) is not None and (" " not in a and "-" not in a and "’" not in a and "'" not in a)
                terms.append(Term(src=a, dst=dst, keep=keep, is_ascii=is_ascii_a, wordish=wordish_a))

        return cls(terms=terms, target_lang=target_lang)

    # ---- 提示词短摘 ----
    def build_prompt_excerpt(self, max_items: int = 300, max_chars: int = 4000, include_keep: bool = False) -> str:
        """
        生成用于贴入 system prompt 的术语“短摘”，形如：
          - Professor Richardson → 理查森教授
          - Sunville → 阳光镇
        include_keep=True 时会包含 keep 项（右侧显示 KEEP）。
        """
        lines: List[str] = []
        total = 0
        used = 0
        for t in self.terms:
            if t.keep and not include_keep:
                continue
            right = ("KEEP" if t.keep or t.dst is None else t.dst or "")
            # 去重：同一 src 可能重复（别名合并时），只保留首次
            line = f"- {t.src} → {right}"
            if any(l.startswith(f"- {t.src} →") for l in lines):
                continue
            if used >= max_items:
                break
            # char 限制
            if total + len(line) + 1 > max_chars:
                break
            lines.append(line)
            total += len(line) + 1
            used += 1
        return "\n".join(lines)

    # ---- 强制替换 ----
    def enforce(self, text: str) -> str:
        """
        对 LLM 输出做硬替换（最长优先），并保护占位/URL。
        采用两段式“哨兵→回填”，避免替换后的文本再被其它项命中。
        """
        if not text:
            return text
        masked, slots = _mask(text)

        # 先将命中的 src 替换成临时哨兵，记录 (sentinel -> dst/keep)
        sent_map: List[Tuple[str, Optional[str]]] = []
        temp = masked
        for idx, t in enumerate(self.terms):
            if t.keep or (t.dst is None):
                # keep: 不做主动替换（保持拉丁），仅跳过
                continue
            pat = t.compile()
            # 使用唯一哨兵，待全部扫描完再统一回填，避免连锁
            sentinel = f"\uE100{idx:04d}\uE101"
            def _mark(m: re.Match) -> str:
                sent_map.append((sentinel, t.dst))
                return sentinel
            temp = pat.sub(_mark, temp)

        # 回填所有哨兵为目标译文
        for sentinel, dst in sent_map:
            temp = temp.replace(sentinel, dst if dst is not None else "")

        # 还原占位/URL
        return _unmask(temp, slots)

    # ---- 辅助输出 ----
    @property
    def pairs(self) -> List[Tuple[str, str]]:
        """返回去重后的 (src, right) 展示对。"""
        seen = set()
        out: List[Tuple[str, str]] = []
        for t in self.terms:
            right = "KEEP" if t.keep or t.dst is None else (t.dst or "")
            if t.src in seen: 
                continue
            seen.add(t.src)
            out.append((t.src, right))
        return out
