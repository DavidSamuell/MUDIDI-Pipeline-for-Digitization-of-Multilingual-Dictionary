"""Project raw-gold language labels onto the cleaned/casefolded metric strings.

The span map (:mod:`mudidi.schemas.language_span`) labels every *raw* gold
codepoint. The Stage 1 character metric, however, works on the *cleaned, casefolded,
grapheme-clustered* gold (tags stripped, NFC, whitespace collapsed, case folded).
These transforms move offsets, so labels are projected -- never sliced -- via a
character alignment (``Levenshtein.opcodes``).

Outputs index the metric's own units:
- :func:`project_clean_languages` -> one language per codepoint of the cleaned/
  casefolded gold;
- :func:`grapheme_languages` -> one language per grapheme cluster (indexes the
  metric's grapheme list);
- :func:`word_languages` -> one language per whitespace word (PRD D-2: majority
  grapheme, ties -> source).
"""

from __future__ import annotations

from collections import Counter
from typing import List, Sequence, Tuple

import grapheme
import Levenshtein

from mudidi.schemas.language_span import SPACE


def _casefold_with_languages(
    raw_text: str, raw_char_lang: Sequence[str]
) -> Tuple[str, List[str]]:
    """Casefold *raw_text* per ``casefold_letters_for_eval`` while carrying languages.

    Done char-by-char so a casefold expansion (e.g. ``ß`` -> ``ss``) duplicates the
    source character's language across the expanded codepoints, keeping the language
    array aligned 1:1 with the casefolded string.
    """
    cased_chars: List[str] = []
    cased_langs: List[str] = []
    for char, language in zip(raw_text, raw_char_lang):
        folded = char.casefold() if char.isalpha() else char
        for folded_char in folded:
            cased_chars.append(folded_char)
            cased_langs.append(language)
    return "".join(cased_chars), cased_langs


def project_clean_languages(
    raw_text: str,
    raw_char_lang: Sequence[str],
    clean_cased: str,
) -> List[str]:
    """Return one language per codepoint of *clean_cased*.

    Aligns the casefolded raw gold to *clean_cased* and carries the source language
    across ``equal``/``replace`` blocks; ``insert`` codepoints inherit the preceding
    raw character's language; ``delete`` blocks drop.
    """
    raw_cased, raw_cased_lang = _casefold_with_languages(raw_text, raw_char_lang)
    clean_lang = [SPACE] * len(clean_cased)
    n = len(raw_cased_lang)
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(raw_cased, clean_cased):
        if tag in ("equal", "replace"):
            for k in range(j2 - j1):
                src = min(i1 + k, i2 - 1) if i2 > i1 else i1
                if n:
                    clean_lang[j1 + k] = raw_cased_lang[min(src, n - 1)]
        elif tag == "insert":
            if i1 > 0 and n:
                language = raw_cased_lang[min(i1 - 1, n - 1)]
            else:
                language = raw_cased_lang[0] if n else SPACE
            for k in range(j1, j2):
                clean_lang[k] = language
    return clean_lang


def grapheme_languages(clean_cased: str, clean_char_lang: Sequence[str]) -> List[str]:
    """Return one language per grapheme cluster of *clean_cased* (first codepoint wins)."""
    languages: List[str] = []
    index = 0
    for cluster in grapheme.graphemes(clean_cased):
        languages.append(
            clean_char_lang[index] if index < len(clean_char_lang) else SPACE
        )
        index += len(cluster)
    return languages


def _majority_language(languages: Sequence[str], source_language: str) -> str:
    """Most common language; ties break to *source_language* (D-2), else sorted-first."""
    if not languages:
        return source_language
    counts = Counter(languages)
    top = max(counts.values())
    winners = sorted(name for name, count in counts.items() if count == top)
    if len(winners) == 1:
        return winners[0]
    return source_language if source_language in winners else winners[0]


def word_languages(
    clean_cased: str,
    clean_char_lang: Sequence[str],
    *,
    source_language: str,
) -> List[Tuple[str, str]]:
    """Split *clean_cased* on whitespace and label each word by its majority language."""
    words: List[Tuple[str, str]] = []
    index = 0
    length = len(clean_cased)
    while index < length:
        if clean_cased[index].isspace():
            index += 1
            continue
        start = index
        while index < length and not clean_cased[index].isspace():
            index += 1
        word = clean_cased[start:index]
        languages = [
            clean_char_lang[k] for k in range(start, index) if clean_char_lang[k] != SPACE
        ]
        words.append((word, _majority_language(languages, source_language)))
    return words
