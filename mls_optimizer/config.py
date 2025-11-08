
from dataclasses import dataclass, field
from typing import List

@dataclass
class OptimConfig:
    # Column indices (0-based)
    col_ru: int = 0
    col_speaker: int = 1
    col_en: int = 2
    col_cn: int = 3           # existing zh (kept; not overwritten)
    col_out: int = 4          # output column

    # Defaults
    default_provider: str = "deepseek"
    default_model: str = "deepseek-chat"
    target_lang: str = "zh-CN"

    # Brands to keep literal
    brands_keep: List[str] = field(default_factory=lambda: ["Patreon","Instagram","Lovense"])
