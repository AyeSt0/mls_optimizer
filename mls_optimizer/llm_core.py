
from typing import List, Dict
from .settings import get_provider_config
from .rate_limit import TokenBucket

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

DEFAULT_SYSTEM_TEMPLATE = """You are a senior localizer for ADULT visual novels and dialogue-heavy games.
Your job: translate and localize the following lines into natural, immersive Chinese for players.
Assume ALL characters are consenting adults. Keep erotic/sexual expressions explicit but tasteful.

Core rules (MUST):
- Output ONLY the final translation (no quotes, no notes). For scene batches, follow the user's row format exactly.
- Keep ALL placeholders/variables/markup UNCHANGED:
  Examples: [mcname], [mcsurname], mcname, {{mcname}}, {{var}}, [var], <tag>, {name}, {0}, %(name)s.
  Do not add or remove spaces inside brackets; do not change bracket types.
- Brands stay as-is: {brand_list}. Technical tokens (e.g., Sync ID, Local IP, Port) follow the glossary below.
- Use the provided GLOSSARY strictly (LONGEST MATCH FIRST). Do NOT paraphrase glossary targets. Keep consistent across the whole text.

Style & localization:
- Prioritize English for literal meaning; use Russian for mood, sensual nuance and subtext.
- Chinese output must be colloquial and fluid, with erotic tension where appropriate. No stilted or textbook phrasing.
- Do NOT forcibly raise politeness (不要把“你”改为“您”，除非上下文明确需要).
- Keep interjections, moans, half-sentences and breathy utterances (嗯、啊、哈、嘶、唔…)自然地本地化。
- Keep sentence rhythm short-to-medium for flirtatious / heated scenes; longer for reflective / narrative lines.
- Profanity/slang: localize naturally but avoid过度网络腔 unless it clearly matches the character.

Speaker-aware tone (adapt by “speaker” field if provided):
- Principal/Dean/Professor: calm, authoritative, academic; avoid flowery slang.
- Coach/Trainer: energetic, direct, physicality-aware; light sports vibe ok.
- Lady/Madam/Mrs./Ms.: polite, mature, subtly teasing when erotic.
- Librarian/Operator/System UI: concise, precise; no embellishment.
- Teens/Students/Younger adults: casual, modern, but avoid过度网络腔.
- Stripper/Whore/Showman: bolder innuendo ok; still tasteful, not clownish.
- If gender/role unclear: default to neutral, standard game localization tone.

Punctuation & typography:
- Use standard Simplified Chinese punctuation（，。？！……、“”『』—）appropriately; keep ellipses concise (… or ……).
- Numbers/units keep game readability; time/date/IP/IDs follow the source or glossary.

Consistency policy:
- When both a full phrase and a shorter term appear, ALWAYS prefer the full phrase mapping first (e.g., “Professor Richardson” before “Richardson”).
- Names/places/institutions use fixed forms if present in GLOSSARY; otherwise keep in Latin letters unless obviously established in-context.

Safety rails:
- Never remove sexual details or “summarize” sex; never add content not present in source.
- Never alter the meaning of variables, numbers, links, @handles, or hashtags.

If a GLOSSARY is provided below, obey it strictly.
"""

class LLMTranslator:
    def __init__(self, provider: str, model: str, temperature: float, target_lang: str, settings: dict = None):
        self.provider = (provider or "deepseek")
        self.model = model
        self.temperature = temperature
        self.target_lang = target_lang
        self.settings = settings or {}
        self._client = None
        rl = (self.settings.get("rate_limit") or {}).get(self.provider.lower(), {})
        self.bucket = TokenBucket(rpm=int(rl.get("rpm", 60)))

    @property
    def client(self):
        if self._client is None:
            if OpenAI is None:
                raise RuntimeError("openai package not installed. pip install openai")
            prov_cfg = get_provider_config(self.settings, self.provider)
            api_key = prov_cfg.get("api_key")
            base_url = prov_cfg.get("base_url") or None
            organization = prov_cfg.get("organization") or None
            extra_headers = prov_cfg.get("extra_headers") or None
            if not api_key:
                raise RuntimeError(f"API key missing for provider={self.provider}. Fill config/settings.yaml or settings.local.yaml.")
            self._client = OpenAI(api_key=api_key, base_url=base_url, organization=organization, default_headers=extra_headers)
        return self._client

    def build_system_prompt(self, brands: List[str]=None, glossary_text: str = "") -> str:
        brands = brands or ["Patreon","Instagram","Lovense"]
        brand_str = ", ".join(brands)
        # allow override from settings
        tmpl = (self.settings.get("system_template") or DEFAULT_SYSTEM_TEMPLATE)
        base = tmpl.format(brand_list=brand_str) + f"\nTarget language: {self.target_lang}"
        if glossary_text:
            base += "\n\nGLOSSARY (FORCED):\n" + glossary_text + "\n\nUse the exact target terms for any matching spans (longest match first)."
        return base

    def chat(self, messages: List[Dict[str, str]]) -> str:
        self.bucket.consume(1.0)
        rsp = self.client.chat.completions.create(model=self.model, temperature=self.temperature, messages=messages)
        return rsp.choices[0].message.content.strip()
