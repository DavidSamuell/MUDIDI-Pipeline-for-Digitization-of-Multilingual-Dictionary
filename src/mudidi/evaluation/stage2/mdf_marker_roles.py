"""Map MDF markers to dictionary language roles for per-language evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from mudidi.schemas.dictionary_languages import DictionaryLanguagesConfig
from mudidi.utils.dictionary_languages import (
    _is_english_language,
    language_key,
    load_dictionary_languages_file,
)

SOURCE_LEXEME_MARKERS = frozenset({"lx", "lc", "va", "se", "pl", "ph", "ps"})
GLOSS_MARKERS = frozenset({"gn", "ge", "gr", "de", "ue", "un", "xn", "xr", "xe"})
STRUCTURAL_MARKERS = frozenset({"sn", "hm", "np", "nt", "cf", "dc"})

HEADWORD_MARKERS = frozenset({"lx", "lc"})


def _language_name_key(name: str) -> str:
    return language_key(name).replace("_", "")


def build_marker_language_map(config: DictionaryLanguagesConfig) -> Dict[str, str]:
    """Return marker code → human-readable language name for this dictionary."""
    mapping: Dict[str, str] = {}
    source = config.source.language
    for marker in SOURCE_LEXEME_MARKERS:
        mapping[marker] = source

    targets = list(config.targets)
    english_targets = [t for t in targets if _is_english_language(t.language)]
    french_targets = [
        t for t in targets if "french" in t.language.lower()
    ]
    chinese_targets = [
        t for t in targets if "chinese" in t.language.lower()
    ]
    russian_targets = [
        t for t in targets if "russian" in t.language.lower()
    ]
    turkish_targets = [
        t for t in targets if "turkish" in t.language.lower()
    ]
    hindi_targets = [t for t in targets if "hindi" in t.language.lower()]

    if english_targets:
        for marker in ("ge", "de", "ue", "xe"):
            mapping.setdefault(marker, english_targets[0].language)
    if french_targets:
        for marker in ("gr", "xr"):
            mapping.setdefault(marker, french_targets[0].language)
    if chinese_targets:
        for marker in ("gn", "xn"):
            mapping.setdefault(marker, chinese_targets[0].language)
    elif russian_targets:
        for marker in ("gn", "un"):
            mapping.setdefault(marker, russian_targets[0].language)
    elif turkish_targets:
        mapping.setdefault("gn", turkish_targets[0].language)
    elif hindi_targets and len(targets) > 1:
        mapping.setdefault("gn", hindi_targets[0].language)

    if len(targets) == 1:
        sole = targets[0].language
        for marker in GLOSS_MARKERS:
            mapping.setdefault(marker, sole)

    return mapping


def source_language_name(language_map: Dict[str, str]) -> Optional[str]:
    """Resolve the dictionary source language from a marker map."""
    for head_marker in ("lx", "lc"):
        lang = language_map.get(head_marker)
        if lang:
            return lang
    return None


def marker_role_bucket(marker: str, language_map: Dict[str, str]) -> Optional[str]:
    """Return a stable bucket key for aggregation (``source`` or ``target:<key>``)."""
    if marker in STRUCTURAL_MARKERS:
        return None
    if marker in HEADWORD_MARKERS or marker in SOURCE_LEXEME_MARKERS:
        lang = language_map.get(marker)
        if lang:
            return f"source:{_language_name_key(lang)}"
        return "source"
    if marker in GLOSS_MARKERS:
        lang = language_map.get(marker)
        if lang:
            return f"target:{_language_name_key(lang)}"
        return "target"
    lang = language_map.get(marker)
    if not lang:
        return None
    source_lang = source_language_name(language_map)
    if source_lang and lang == source_lang:
        return f"source:{_language_name_key(lang)}"
    return f"target:{_language_name_key(lang)}"


def load_language_map_for_page(
    pred_path: Path,
    *,
    dictionary_languages_path: Path | None = None,
    dataset_dir: Path | None = None,
) -> Dict[str, str]:
    """Resolve marker→language map from explicit YAML or dictionary folder layout."""
    if dictionary_languages_path and dictionary_languages_path.is_file():
        return build_marker_language_map(load_dictionary_languages_file(dictionary_languages_path))

    parts = pred_path.parts
    language_dir_name: Optional[str] = None
    try:
        stage2_idx = parts.index("stage-2")
        language_dir_name = parts[stage2_idx - 1]
    except ValueError:
        language_dir_name = None

    for candidate in pred_path.parents:
        yaml_path = candidate / "dictionary_languages.yaml"
        if yaml_path.is_file():
            return build_marker_language_map(load_dictionary_languages_file(yaml_path))

    if language_dir_name:
        for root in (
            dataset_dir,
            Path.cwd() / "dataset" / "MUDIDI" / "dictionaries",
            Path.cwd() / "dataset" / "mudidi" / "dictionaries",
        ):
            if root is None:
                continue
            yaml_path = Path(root) / language_dir_name / "dictionary_languages.yaml"
            if yaml_path.is_file():
                return build_marker_language_map(load_dictionary_languages_file(yaml_path))
    return {}
