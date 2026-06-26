"""Unit tests for Tier-2 tag-injection recovery + labeler helpers (no live LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from label_studio_ner import page_map_to_ls_task, ls_task_to_page_map  # noqa: E402
from tier2_labeler import (  # noqa: E402
    _strip_code_fence,
    build_prompt,
    read_language_seed,
)
from tier2_recovery import Tier2DriftError, parse_tagged, recover_page_map  # noqa: E402

from mudidi.schemas.language_span import SPACE  # noqa: E402


def _lang_at(page_map, raw, needle):
    start = raw.index(needle)
    cm = page_map.language_char_map(raw)
    # Whitespace is SPACE by design; check the language of the non-space codepoints.
    langs = {cm[i] for i in range(start, start + len(needle)) if not raw[i].isspace()}
    assert len(langs) == 1, f"{needle!r} spans multiple languages: {langs}"
    return next(iter(langs))


def test_exact_round_trip_partitions_languages():
    raw = "akɔɔtee small crab\n"
    tagged = "<Canala>akɔɔtee</Canala> <English>small crab</English>\n"
    pm, used, drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=1)
    assert drift == 0.0
    pm.validate_against(raw)
    assert _lang_at(pm, raw, "akɔɔtee") == "Canala"
    assert _lang_at(pm, raw, "small crab") == "English"
    assert set(used) == {"Canala", "English"}


def test_markup_preserved_as_content():
    raw = "<b>akɔɔtee</b> small\n"
    tagged = "<Canala><b>akɔɔtee</b></Canala> <English>small</English>\n"
    pm, _used, drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=1)
    assert drift == 0.0
    # The <b>...</b> markup is content inside the Canala span, not a language tag.
    assert _lang_at(pm, raw, "<b>akɔɔtee</b>") == "Canala"


def test_open_vocabulary_discovery():
    raw = "amãrɛ the remains; tourterelle verte\n"
    tagged = (
        "<Canala>amãrɛ</Canala> <English>the remains;</English> "
        "<French>tourterelle verte</French>\n"
    )
    pm, used, drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=2)
    assert drift == 0.0
    assert "French" in used  # not in the seed, still recovered
    assert _lang_at(pm, raw, "tourterelle verte") == "French"


def test_whitespace_forced_to_space():
    raw = "akɔɔtee small\n"
    # Even if the model tucks the space inside a tag, whitespace becomes SPACE.
    tagged = "<Canala>akɔɔtee </Canala><English>small</English>\n"
    pm, _used, _drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=1)
    cm = pm.language_char_map(raw)
    assert cm[raw.index(" ")] == SPACE
    assert cm[raw.index("\n")] == SPACE


def test_untagged_content_is_space():
    raw = "akɔɔtee small\n"
    tagged = "<Canala>akɔɔtee</Canala> small\n"  # 'small' left untagged
    pm, _used, _drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=1)
    assert _lang_at(pm, raw, "small") == SPACE


def test_minor_drift_recovers_within_tolerance():
    raw = "akɔɔtee small crab\n"
    tagged = "<Canala>akɔɔtee</Canala> <English>small crb</English>\n"  # dropped 'a'
    pm, _used, drift = recover_page_map(
        raw, tagged, dictionary="Canala-English", page=1, max_drift=0.5
    )
    assert drift > 0.0
    pm.validate_against(raw)
    assert _lang_at(pm, raw, "akɔɔtee") == "Canala"


def test_excess_drift_rejected():
    raw = "akɔɔtee small crab\n"
    tagged = "<Canala>akɔɔtee</Canala> <English>entirely different text</English>\n"
    with pytest.raises(Tier2DriftError):
        recover_page_map(raw, tagged, dictionary="Canala-English", page=1)


def test_ner_round_trip_is_lossless():
    raw = "<b>amãrɛ</b> the remains; tourterelle verte\n"
    tagged = (
        "<Canala><b>amãrɛ</b></Canala> <English>the remains;</English> "
        "<French>tourterelle verte</French>\n"
    )
    pm, _used, _drift = recover_page_map(raw, tagged, dictionary="Canala-English", page=2)
    task = page_map_to_ls_task(pm, raw)
    rebuilt = ls_task_to_page_map(
        task, raw, dictionary="Canala-English", page=2, labeled_via="llm"
    )
    assert rebuilt.canonical().spans == pm.canonical().spans


def test_parse_tagged_stray_close_ignored():
    text, langs, used = parse_tagged("<English>hi</English></French>!")
    assert text == "hi!"
    assert used == {"English"}
    assert langs[0] == "English" and langs[-1] == SPACE  # '!' after close -> SPACE


def test_strip_code_fence():
    fenced = "```\n<English>hi</English>\n```"
    assert _strip_code_fence(fenced) == "<English>hi</English>"
    plain = "<English>hi</English>"
    assert _strip_code_fence(plain) == plain


def test_build_prompt_lists_seed_and_text():
    prompt = build_prompt("akɔɔtee small\n", ["Canala", "English", "French"])
    assert "Canala, English, French" in prompt
    assert "akɔɔtee small" in prompt
    assert "Do NOT add, delete" in prompt


def test_read_language_seed_merges_rules(tmp_path):
    (tmp_path / "dictionary_languages.yaml").write_text(
        "source:\n  language: Canala\ntargets:\n- language: English\n",
        encoding="utf-8",
    )
    (tmp_path / "language_rules.yaml").write_text(
        "languages:\n- French\n", encoding="utf-8"
    )
    assert read_language_seed(tmp_path) == ["Canala", "English", "French"]
