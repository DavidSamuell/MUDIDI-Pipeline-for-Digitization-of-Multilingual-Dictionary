"""Compatibility shim: the span-label gold contract now lives in the package.

The :class:`PageLanguageMap` contract moved to
:mod:`mudidi.schemas.language_span` so the **evaluation** package can consume it
(see ``src/mudidi/evaluation/stage1/per_language_quality.py``). The annotation
workspace -- which *produces* span maps and uses flat sibling imports -- keeps
importing ``span_schema`` through this re-export.
"""

from mudidi.schemas.language_span import (  # noqa: F401  (re-export)
    META,
    SPACE,
    LabeledVia,
    LanguageSpan,
    PageLanguageMap,
    SpanMapError,
    sha256_of,
)

__all__ = [
    "META",
    "SPACE",
    "LabeledVia",
    "LanguageSpan",
    "PageLanguageMap",
    "SpanMapError",
    "sha256_of",
]
