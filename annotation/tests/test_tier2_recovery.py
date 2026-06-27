"""Unit tests for Tier-2 tag-injection recovery + labeler helpers (no live LLM)."""

from __future__ import annotations

import pytest

import tier2_labeler  # noqa: E402  (module handle for monkeypatching the LLM)
from label_studio_ner import page_map_to_ls_task, ls_task_to_page_map  # noqa: E402
from tier2_labeler import (  # noqa: E402
    _strip_code_fence,
    build_prompt,
    label_dictionary,
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


def _make_dictionary(root, pages):
    """Build a minimal Canala-English gold dictionary; ``pages`` is {page_no: text}."""
    dictionary_dir = root / "Canala-English"
    dictionary_dir.mkdir()
    (dictionary_dir / "dictionary_languages.yaml").write_text(
        "source:\n  language: Canala\ntargets:\n- language: English\n", encoding="utf-8"
    )
    for page, text in pages.items():
        gold_dir = dictionary_dir / "Stage 1 Gold OCR" / f"sub{page}"
        gold_dir.mkdir(parents=True)
        (gold_dir / f"page_{page}_stage1_GOLD_flat.txt").write_text(
            text, encoding="utf-8"
        )
    return dictionary_dir


def test_label_dictionary_continues_past_failed_page(tmp_path, monkeypatch):
    # Page 1's LLM output round-trips cleanly; page 2 drifts past the gate. The
    # drifted page must be recorded as failed WITHOUT aborting the whole batch.
    dictionary_dir = _make_dictionary(
        tmp_path, {1: "akɔɔtee small\n", 2: "amãrɛ crab\n"}
    )

    def fake_llm(*, model, messages, reasoning_effort, max_tokens):
        prompt = messages[0]["content"]
        if "akɔɔtee" in prompt:
            return "<Canala>akɔɔtee</Canala> <English>small</English>\n", {}
        return "<English>completely unrelated replacement sentence</English>\n", {}

    monkeypatch.setattr(tier2_labeler, "complete_with_usage", fake_llm)
    results = label_dictionary(dictionary_dir, output_root=tmp_path / "outputs")
    by_page = {r.page: r for r in results}
    assert by_page[1].status == "ok"
    assert by_page[2].status == "failed"
    assert "Tier2DriftError" in (by_page[2].error or "")


def test_label_dictionary_writes_under_output_root_subdir(tmp_path, monkeypatch):
    dictionary_dir = _make_dictionary(tmp_path, {1: "akɔɔtee small\n"})
    out_root = tmp_path / "outputs"

    monkeypatch.setattr(
        tier2_labeler,
        "complete_with_usage",
        lambda **kwargs: ("<Canala>akɔɔtee</Canala> <English>small</English>\n", {}),
    )
    results = label_dictionary(dictionary_dir, output_root=out_root)
    # Path layout is <output_root>/<dictionary>/page_<N>_lang.json (not inside dataset).
    assert results[0].out_path == out_root / "Canala-English" / "page_1_lang.json"


def test_label_dictionary_skip_existing_avoids_llm(tmp_path, monkeypatch):
    dictionary_dir = _make_dictionary(tmp_path, {1: "akɔɔtee small\n"})
    out_root = tmp_path / "outputs"
    gold = next(dictionary_dir.glob("Stage 1 Gold OCR/*/*_stage1_GOLD_flat.txt"))
    existing = tier2_labeler._lang_map_path(gold, out_root)
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("{}", encoding="utf-8")

    calls = []

    def fake_llm(**kwargs):
        calls.append(1)
        return "<Canala>akɔɔtee</Canala> <English>small</English>\n", {}

    monkeypatch.setattr(tier2_labeler, "complete_with_usage", fake_llm)
    results = label_dictionary(dictionary_dir, skip_existing=True, output_root=out_root)
    assert results[0].status == "skipped"
    assert results[0].out_path == existing
    assert calls == []  # existing map -> no LLM call


def test_parse_llm_output_splits_legend_and_tagged():
    out = (
        "LANGUAGES:\n"
        "ike = Iñupiatun Eskimo\n"
        "eng = English\n"
        "\n"
        "TAGGED:\n"
        "<ike>Qiñu</ike> <eng>ice</eng>\n"
    )
    legend, tagged = tier2_labeler.parse_llm_output(out)
    assert legend == {"ike": "Iñupiatun Eskimo", "eng": "English"}
    assert tagged == "<ike>Qiñu</ike> <eng>ice</eng>\n"


def test_parse_llm_output_without_markers_is_all_tagged():
    legend, tagged = tier2_labeler.parse_llm_output("<eng>hi</eng>")
    assert legend == {}
    assert tagged == "<eng>hi</eng>"


def test_recover_page_map_translates_iso_codes_to_names():
    # The multi-word name 'Iñupiatun Eskimo' could never be a tag; via an ISO code it
    # round-trips cleanly and is restored from the legend.
    raw = "Qiñu ice\n"
    tagged = "<ike>Qiñu</ike> <eng>ice</eng>\n"
    legend = {"ike": "Iñupiatun Eskimo", "eng": "English"}
    pm, used, drift = recover_page_map(
        raw, tagged, dictionary="Iñupiatun Eskimo-English", page=42,
        code_to_language=legend,
    )
    assert drift == 0.0
    pm.validate_against(raw)
    assert _lang_at(pm, raw, "Qiñu") == "Iñupiatun Eskimo"
    assert _lang_at(pm, raw, "ice") == "English"
    assert set(used) == {"Iñupiatun Eskimo", "English"}


def test_label_page_maps_iso_codes_end_to_end(monkeypatch):
    raw = "Qiñu ice\n"

    def fake_llm(**kwargs):
        return (
            "LANGUAGES:\nike = Iñupiatun Eskimo\neng = English\n"
            "TAGGED:\n<ike>Qiñu</ike> <eng>ice</eng>\n"
        ), {}

    monkeypatch.setattr(tier2_labeler, "complete_with_usage", fake_llm)
    pm, used, drift, _usage = tier2_labeler.label_page(
        raw,
        dictionary="Iñupiatun Eskimo-English",
        page=42,
        seed_languages=["Iñupiatun Eskimo", "English"],
    )
    assert drift == 0.0
    assert _lang_at(pm, raw, "Qiñu") == "Iñupiatun Eskimo"
