"""Deterministic Unicode script classification for source/target span separation.

This is the *first* stage of the Tier-2 pipeline (script-check -> LID -> merge).
It resolves every token it can by script alone (distinct source scripts, IPA
diacritics, distinct-script targets like Han) and leaves only the genuinely
ambiguous tokens -- those sitting in the *same* script as a target -- as
``RESIDUAL`` for a language identifier to disambiguate.

No third-party dependencies: pure ``unicodedata`` + codepoint ranges.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Set


class TokenCategory(str, Enum):
    SOURCE = "source"            # resolved to the source language by script
    DISTINCT_TARGET = "target"   # a target with its own script (e.g. Chinese/Han)
    RESIDUAL = "residual"        # same script as a target -> needs LID
    PUNCT = "punct"              # punctuation / digits / symbols only


# --- codepoint ranges -------------------------------------------------------

def _in(ch: str, lo: int, hi: int) -> bool:
    return lo <= ord(ch) <= hi


def _is_ipa(ch: str) -> bool:
    """IPA extensions, modifier/tone letters, and combining marks."""
    o = ord(ch)
    return (
        0x0250 <= o <= 0x02AF    # IPA Extensions (ɔ ɛ ŋ ɟ ɨ ʔ ...)
        or 0x02B0 <= o <= 0x02FF  # Spacing Modifier Letters (ʷ ʰ ˥ ˧ ˩ ...)
        or 0x0300 <= o <= 0x036F  # Combining Diacritical Marks (nasalization, tone)
        or 0x1DC0 <= o <= 0x1DFF  # Combining Diacritical Marks Supplement
        or 0xA700 <= o <= 0xA71F  # Modifier Tone Letters
        or ch == "ŋ"             # U+014B, common in the Latin-orthography sources
    )


# Russian alphabet (so we can flag *extended* Cyrillic as source).
_RUSSIAN = set("абвгдежзийклмнопрстуфхцчшщъыьэюяёАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯЁ")


def _base_script(ch: str) -> str:
    """Coarse script bucket for a single character."""
    o = ord(ch)
    if ch.isspace():
        return "space"
    if _is_ipa(ch):
        return "ipa"
    cat = unicodedata.category(ch)
    if cat[0] in ("P", "S"):
        return "punct"
    if cat[0] == "N":
        return "digit"
    if _in(ch, 0x0400, 0x04FF) or _in(ch, 0x0500, 0x052F):  # Cyrillic (+ supplement)
        return "cyrillic_ext" if ch not in _RUSSIAN else "cyrillic"
    if _in(ch, 0x4E00, 0x9FFF) or _in(ch, 0x3400, 0x4DBF):  # CJK Han
        return "han"
    if _in(ch, 0x3040, 0x309F):
        return "hiragana"
    if _in(ch, 0x30A0, 0x30FF):
        return "katakana"
    if _in(ch, 0x0370, 0x03FF) or _in(ch, 0x1F00, 0x1FFF):  # Greek (+ extended)
        return "greek"
    if _in(ch, 0x0900, 0x097F):
        return "devanagari"
    if _in(ch, 0x0980, 0x09FF):
        return "bengali"
    if _in(ch, 0x0A00, 0x0A7F):
        return "gurmukhi"
    if _in(ch, 0x0A80, 0x0AFF):
        return "gujarati"
    if _in(ch, 0x0C00, 0x0C7F):
        return "telugu"
    if _in(ch, 0x0E00, 0x0E7F):
        return "thai"
    if _in(ch, 0x1780, 0x17FF):
        return "khmer"
    if _in(ch, 0x10A0, 0x10FF):
        return "georgian"
    if _in(ch, 0x0590, 0x05FF):
        return "hebrew"
    if _in(ch, 0x0600, 0x06FF) or _in(ch, 0x0750, 0x077F):
        return "arabic"
    if _in(ch, 0x0700, 0x074F):
        return "syriac"
    if _in(ch, 0x12000, 0x123FF) or _in(ch, 0x12400, 0x1247F):
        return "cuneiform"
    if _in(ch, 0x0041, 0x024F):  # Basic Latin .. Latin Extended-B (incl. diacritics)
        return "latin"
    return "other"


@dataclass(frozen=True)
class ScriptConfig:
    """Per-dictionary script layout for classification."""

    target_scripts: Set[str]              # scripts a target language is written in
    source_is_ipa: bool = False           # source uses IPA/Latin-with-IPA (Canala, Na)
    source_is_cyrillic_ext: bool = False  # source is extended Cyrillic (Chukchi)
    distinct_targets: Dict[str, str] = None  # script -> target language (han->Chinese)

    def targets(self) -> Dict[str, str]:
        return self.distinct_targets or {}


@dataclass(frozen=True)
class TokenLabel:
    token: str
    category: TokenCategory
    detail: str  # script bucket or distinct-target language


def classify_token(token: str, cfg: ScriptConfig) -> TokenLabel:
    scripts = [_base_script(ch) for ch in token if not ch.isspace()]
    letters = [s for s in scripts if s not in ("punct", "digit")]
    if not letters:
        return TokenLabel(token, TokenCategory.PUNCT, "punct")

    sset = set(letters)

    # 1. Source resolved by distinctive script signal.
    if cfg.source_is_ipa and "ipa" in sset:
        return TokenLabel(token, TokenCategory.SOURCE, "ipa")
    if cfg.source_is_cyrillic_ext and "cyrillic_ext" in sset:
        return TokenLabel(token, TokenCategory.SOURCE, "cyrillic_ext")

    # 2. Distinct-script target (e.g. Han -> Chinese in the Na dictionary).
    for script, lang in cfg.targets().items():
        if script in sset:
            return TokenLabel(token, TokenCategory.DISTINCT_TARGET, lang)

    # 3. Entirely within a target script -> ambiguous, needs LID.
    non_target = sset - cfg.target_scripts
    if not non_target:
        return TokenLabel(token, TokenCategory.RESIDUAL, next(iter(cfg.target_scripts)))

    # 4. Carries a non-target, non-Latin script -> source by distinct script.
    exotic = non_target - {"latin", "cyrillic"}
    if exotic:
        return TokenLabel(token, TokenCategory.SOURCE, sorted(exotic)[0])

    # 5. Mixed target-script + plain Latin/Cyrillic -> residual.
    return TokenLabel(token, TokenCategory.RESIDUAL, next(iter(cfg.target_scripts)))
