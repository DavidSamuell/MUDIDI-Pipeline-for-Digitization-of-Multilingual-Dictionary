"""Per-page language span artifact: the gold contract for per-language Stage 1 eval.

A :class:`PageLanguageMap` assigns every character of a page's *raw* gold text a
language. Spans are contiguous, non-overlapping, and cover the whole text; the map
is bound to the exact gold bytes by a SHA-256 guard so it can never silently attach
to stale text.

This is the shared contract between two halves of the system:
- the **annotation** workspace (``annotation/``) *produces* the span map (script-check
  or LLM draft, then human-verified in Label Studio);
- the **evaluation** package (:mod:`mudidi.evaluation.stage1.per_language_quality`)
  *consumes* it to attribute per-language Stage 1 OCR error.

Coordinate system (single source of truth everywhere downstream):
- offsets are **Python ``str`` indices (Unicode codepoints)** into the decoded
  UTF-8 raw gold string -- not bytes, not grapheme clusters;
- ``source_text_sha`` is ``sha256`` of that same decoded string;
- the Label Studio task text and NER offsets reuse the identical string.

Structural invariants (span bounds, contiguity) are enforced at construction and
surface as ``pydantic.ValidationError`` (pydantic wraps the :class:`SpanMapError`
raised in ``model_post_init``; its message is preserved). The gold-binding +
full-coverage checks need the text and raise :class:`SpanMapError` directly from
:meth:`PageLanguageMap.validate_against`.

No third-party dependencies beyond ``pydantic`` (already a project dependency).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Non-language fill labels. ``SPACE`` covers inter-token whitespace; ``META`` covers
# editorial markers that are not a language (e.g. "[NK]", "[C]").
SPACE = "space"
META = "meta"

LabeledVia = Literal["heuristic", "llm", "label-studio"]


class SpanMapError(ValueError):
    """Raised when a span map violates its invariants or its gold binding."""


def sha256_of(text: str) -> str:
    """Return the SHA-256 hex digest of *text* encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LanguageSpan(BaseModel):
    """A half-open ``[start, end)`` codepoint range labelled with one language."""

    model_config = ConfigDict(extra="ignore")

    start: int = Field(ge=0)
    end: int
    language: str
    role: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        # Raised here (not in a validator) so the domain error propagates directly
        # instead of being wrapped in pydantic's ValidationError.
        if self.end <= self.start:
            raise SpanMapError(
                f"span end ({self.end}) must be greater than start ({self.start})"
            )


class PageLanguageMap(BaseModel):
    """Contiguous, full-coverage language labelling of one page's raw gold text."""

    model_config = ConfigDict(extra="ignore")

    dictionary: str
    page: int
    source_text_sha: str
    rule_set: str = ""
    labeled_via: LabeledVia
    spans: List[LanguageSpan] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        for index in range(1, len(self.spans)):
            prev, cur = self.spans[index - 1], self.spans[index]
            if cur.start != prev.end:
                raise SpanMapError(
                    "spans must be contiguous and non-overlapping: "
                    f"span[{index - 1}].end={prev.end} != span[{index}].start={cur.start}"
                )

    # -- gold binding / coverage (needs the text) ---------------------------------

    def validate_against(self, text: str) -> None:
        """Raise :class:`SpanMapError` unless this map binds and fully covers *text*."""
        if self.source_text_sha != sha256_of(text):
            raise SpanMapError("source_text_sha does not match the provided gold text")
        if not text:
            if self.spans:
                raise SpanMapError("empty text must have no spans")
            return
        if not self.spans:
            raise SpanMapError("non-empty text must be fully covered by spans")
        if self.spans[0].start != 0:
            raise SpanMapError(f"first span must start at 0, got {self.spans[0].start}")
        if self.spans[-1].end != len(text):
            raise SpanMapError(
                f"last span must end at len(text)={len(text)}, got {self.spans[-1].end}"
            )

    def language_char_map(self, text: str) -> List[str]:
        """Return a per-codepoint language label array of length ``len(text)``."""
        self.validate_against(text)
        labels = [SPACE] * len(text)
        for span in self.spans:
            for index in range(span.start, span.end):
                labels[index] = span.language
        return labels

    def canonical(self) -> "PageLanguageMap":
        """Return a copy with adjacent same-language, same-role spans merged.

        This is the equality normal form used by Label Studio round-trip tests.
        """
        merged: List[LanguageSpan] = []
        for span in self.spans:
            last = merged[-1] if merged else None
            if (
                last is not None
                and last.language == span.language
                and last.role == span.role
                and last.end == span.start
            ):
                merged[-1] = LanguageSpan(
                    start=last.start,
                    end=span.end,
                    language=last.language,
                    role=last.role,
                )
            else:
                merged.append(span.model_copy())
        return self.model_copy(update={"spans": merged})

    # -- IO -----------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "PageLanguageMap":
        """Load a span map from ``*_lang.json``."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        """Write this span map to ``*_lang.json`` (pretty-printed)."""
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
