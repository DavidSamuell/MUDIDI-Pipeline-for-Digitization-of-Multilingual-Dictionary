from mudidi.evaluation.stage2.mdf_lexical_repair import (
    RepairConfig,
    repair_mdf_text,
)


def test_repair_reverts_lexical_chars_but_preserves_stage2_separators() -> None:
    stage1_text = (
        "CENTECTLAPIXQUE s plur Commissaires chargés de surveiller "
        "et de prévenir les magistrats"
    )
    mdf_text = "\\gn Commisaires chargés de surveiller et de prévenir les magistrats.\n"

    result = repair_mdf_text(mdf_text, stage1_text)

    assert (
        result.text
        == "\\gn Commissaires chargés de surveiller et de prévenir les magistrats.\n"
    )
    assert result.changed_lines == 1
    assert result.decisions[0].match_status == "approximate-token"


def test_repair_keeps_mdf_marker_and_punctuation() -> None:
    stage1_text = "centetia in toyollo nous nous aimons nos cœurs sont unis"
    mdf_text = "\\xv centetia-in-toyollo,\n"

    result = repair_mdf_text(mdf_text, stage1_text)

    assert result.text == "\\xv centetia-in-toyollo,\n"
    assert result.decisions[0].status == "unchanged"


def test_repair_skips_when_lexical_run_count_mismatches() -> None:
    stage1_text = "magisx trats suite longue"
    mdf_text = "\\gn magistrats suite longue\n"

    result = repair_mdf_text(
        mdf_text,
        stage1_text,
        config=RepairConfig(min_value_lexical_chars=3, min_anchor_coverage=0.5),
    )

    assert result.text == mdf_text
    assert result.changed_lines == 0
    assert result.decisions[0].reason == "lexical_run_count_mismatch"


def test_repair_skips_short_values_by_default() -> None:
    stage1_text = "s"
    mdf_text = "\\ps z\n"

    result = repair_mdf_text(mdf_text, stage1_text)

    assert result.text == mdf_text
    assert result.decisions[0].reason == "too_few_lexical_chars"


def test_repair_skips_ambiguous_approximate_source_spans() -> None:
    stage1_text = (
        "Commissaires chargés de surveiller et de prévenir les magistrats. "
        "Commissaires chargés de surveiller et de prévenir les magistrats."
    )
    mdf_text = "\\gn Commisaires chargés de surveiller et de prévenir les magistrats.\n"

    result = repair_mdf_text(mdf_text, stage1_text)

    assert result.text == mdf_text
    assert result.changed_lines == 0
    assert result.decisions[0].reason == "ambiguous_source_span"


def test_repair_does_not_search_before_cursor_for_later_mdf_lines() -> None:
    stage1_text = (
        "Commissaires chargés de surveiller les magistrats. "
        "Autre entrée complètement différente."
    )
    mdf_text = (
        "\\lx Autre entrée complètement différente\n"
        "\\gn Commisaires chargés de surveiller les magistrats.\n"
    )

    result = repair_mdf_text(mdf_text, stage1_text)

    assert result.text == mdf_text
    assert result.changed_lines == 0
    assert result.decisions[1].reason == "no_safe_source_span"


def test_repair_skips_low_similarity_token_substitution() -> None:
    stage1_text = "They give a charge concerning it"
    mdf_text = "\\ge To give a charge concerning it\n"

    result = repair_mdf_text(mdf_text, stage1_text)

    assert result.text == mdf_text
    assert result.changed_lines == 0
    assert result.decisions[0].reason == "low_similarity_lexical_replacement"
