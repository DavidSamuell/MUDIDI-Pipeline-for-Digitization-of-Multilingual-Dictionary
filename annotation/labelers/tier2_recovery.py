"""Deterministic tag-injection recovery: tagged LLM text -> PageLanguageMap.

The Tier-2 LLM labeler asks the model to re-emit the *raw* gold wrapped in language
tags (``<Canala>...</Canala>``) without altering a single character, preserving the
gold's own ``<b>``/``<i>`` typography markup as content. This module turns that tagged
string back into a validated :class:`PageLanguageMap` over **raw-gold codepoint
offsets** (D-3) -- the LLM never emits an integer offset.

Recovery is deterministic and never trusts the model blindly:

1. Parse the tagged string into a (char, language) stream. Any tag whose name is in
   the closed markup set (``b``/``i``) is literal content; every other ``<Name>`` is a
   language wrapper (open vocabulary -- a language not in the seed list still recovers).
2. The de-tagged text must equal the raw gold. If it does, offsets map 1:1. If the
   model drifted (fixed a typo, dropped a char), align de-tagged->gold with
   ``Levenshtein.opcodes`` and carry languages across; if drift exceeds ``max_drift``
   the page is rejected (:class:`Tier2DriftError`) for manual labeling rather than
   emitting a corrupt map.
3. Whitespace codepoints are forced to ``SPACE`` for parity with the Tier-1 labeler.

No third-party dependencies beyond ``python-Levenshtein`` and ``mudidi.schemas``.
"""

from __future__ import annotations

import re
from typing import List, Mapping, Optional, Sequence, Set, Tuple

import Levenshtein

from mudidi.schemas.language_span import (
    SPACE,
    LanguageSpan,
    PageLanguageMap,
    sha256_of,
)

# Tags whose name is in this closed set are the gold's own typography markup and are
# treated as literal content; every other ``<Name>`` tag is a language wrapper.
DEFAULT_MARKUP_TAGS = frozenset({"b", "i"})

RULE_SET = "llm-tag-inject-v1"

# An opening or closing tag with a simple ascii name (no attributes); anything that
# does not match (e.g. a stray ``<`` in the text) is left as literal content.
_TAG = re.compile(r"</?([A-Za-z][\w-]*)>")


class Tier2DriftError(ValueError):
    """Raised when de-tagged LLM output drifts from the gold beyond tolerance."""


def parse_tagged(
    tagged: str,
    markup_tags: Set[str] | frozenset = DEFAULT_MARKUP_TAGS,
) -> Tuple[str, List[str], Set[str]]:
    """Parse a tagged string into ``(recovered_text, per_char_languages, used_langs)``.

    Markup tags (``markup_tags``) pass through as literal content carrying the current
    language; every other tag opens/closes a language span. Untagged content is
    labelled ``SPACE`` (it is refilled / re-attributed downstream).
    """
    chars: List[str] = []
    langs: List[str] = []
    used: Set[str] = set()
    stack: List[str] = []
    markup = {name.lower() for name in markup_tags}

    def emit(segment: str) -> None:
        current = stack[-1] if stack else SPACE
        for ch in segment:
            chars.append(ch)
            langs.append(current)

    pos = 0
    for match in _TAG.finditer(tagged):
        emit(tagged[pos:match.start()])
        name = match.group(1)
        is_closing = match.group(0).startswith("</")
        if name.lower() in markup:
            emit(match.group(0))  # gold markup -> literal content
        elif is_closing:
            if name in stack:
                while stack and stack.pop() != name:
                    pass  # close any tags the model left open inside
            # a stray close with no matching open is ignored
        else:
            stack.append(name)
            used.add(name)
        pos = match.end()
    emit(tagged[pos:])
    return "".join(chars), langs, used


def _project_onto(
    src: str, src_langs: Sequence[str], dst: str
) -> Tuple[List[str], float]:
    """Carry ``src_langs`` onto ``dst`` via edit alignment; return (languages, drift)."""
    out = [SPACE] * len(dst)
    n = len(src_langs)
    edits = 0
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(src, dst):
        if tag in ("equal", "replace"):
            for k in range(j2 - j1):
                source_index = min(i1 + k, i2 - 1)
                if n:
                    out[j1 + k] = src_langs[min(source_index, n - 1)]
            if tag == "replace":
                edits += max(i2 - i1, j2 - j1)
        elif tag == "insert":
            if i1 > 0 and n:
                language = src_langs[min(i1 - 1, n - 1)]
            else:
                language = src_langs[0] if n else SPACE
            for k in range(j1, j2):
                out[k] = language
            edits += j2 - j1
        elif tag == "delete":
            edits += i2 - i1
    drift = edits / max(len(dst), 1)
    return out, drift


def _spans_from_char_languages(labels: Sequence[str]) -> List[LanguageSpan]:
    """Group consecutive equal labels into contiguous spans."""
    spans: List[LanguageSpan] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            spans.append(LanguageSpan(start=start, end=index, language=labels[start]))
            start = index
    return spans


def recover_page_map(
    raw_gold: str,
    tagged: str,
    *,
    dictionary: str,
    page: int,
    rule_set: str = RULE_SET,
    markup_tags: Set[str] | frozenset = DEFAULT_MARKUP_TAGS,
    max_drift: float = 0.02,
    code_to_language: Optional[Mapping[str, str]] = None,
) -> Tuple[PageLanguageMap, List[str], float]:
    """Recover a validated :class:`PageLanguageMap` from tagged LLM output.

    Returns ``(page_map, used_languages, drift)`` where ``drift`` is the fraction of
    gold characters the de-tagged text disagreed on (0.0 on an exact match).

    When the model tags runs with ISO 639-3 codes (``<ike>``, ``<eng>``) rather than
    full names, pass ``code_to_language`` (from the model's own legend) to translate
    each tag back to its language name; unknown codes are kept verbatim. With
    ``code_to_language=None`` the tag names are used as the languages directly.

    Raises:
        Tier2DriftError: if the de-tagged text drifts from ``raw_gold`` by more than
            ``max_drift`` (the page should be labelled manually instead).
        SpanMapError: if the rebuilt map fails its gold-binding/coverage invariants.
    """
    recovered, rec_langs, used = parse_tagged(tagged, markup_tags)
    if code_to_language:
        rec_langs = [code_to_language.get(lang, lang) for lang in rec_langs]
        used = {code_to_language.get(name, name) for name in used}
    if recovered == raw_gold:
        char_lang: List[str] = list(rec_langs)
        drift = 0.0
    else:
        char_lang, drift = _project_onto(recovered, rec_langs, raw_gold)
        if drift > max_drift:
            raise Tier2DriftError(
                f"de-tagged LLM output for page {page} drifted from gold by "
                f"{drift:.1%} (> {max_drift:.0%}); flag for manual labeling"
            )
    # Whitespace is SPACE, matching the Tier-1 labeler.
    char_lang = [
        SPACE if ch.isspace() else lang for ch, lang in zip(raw_gold, char_lang)
    ]
    page_map = PageLanguageMap(
        dictionary=dictionary,
        page=page,
        source_text_sha=sha256_of(raw_gold),
        rule_set=rule_set,
        labeled_via="llm",
        spans=_spans_from_char_languages(char_lang),
    ).canonical()
    page_map.validate_against(raw_gold)
    return page_map, sorted(used), drift
