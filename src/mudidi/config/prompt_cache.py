"""Prompt caching and media-reference configuration types."""

from __future__ import annotations

from typing import Literal

PromptCacheMode = Literal["auto", "off"]
MediaReferenceMode = Literal["auto", "inline", "file-uri"]

PROMPT_CACHE_CHOICES: tuple[str, ...] = ("auto", "off")
MEDIA_REFERENCE_CHOICES: tuple[str, ...] = ("auto", "inline", "file-uri")
