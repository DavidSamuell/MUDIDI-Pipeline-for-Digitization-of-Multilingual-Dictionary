from __future__ import annotations

import argparse
from pathlib import Path

from mudidi.cli import extract


def _batch_args(dataset: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        samples_dir=str(dataset),
        languages=None,
        output=str(output),
        no_intro=False,
        no_alphabet=False,
    )


def test_dataset_batch_discovers_dictionary_layout_and_preserves_output_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dictionaries"
    entry = dataset / "Evenki-Russian"
    pages = entry / "Dictionary pages"
    pages.mkdir(parents=True)
    alphabet = entry / "Alphabet list" / "alphabet.txt"
    alphabet.parent.mkdir()
    alphabet.write_text("abc", encoding="utf-8")
    languages = entry / "dictionary_languages.yaml"
    languages.write_text("layout: parallel", encoding="utf-8")
    output = tmp_path / "benchmark-output"
    observed = []

    def fake_run_single(args, _parser):
        observed.append(
            (
                args.input_image,
                args.output,
                args.alphabet,
                args.dictionary_languages,
            )
        )
        return 0

    monkeypatch.setattr(extract, "_run_single_entry", fake_run_single)

    result = extract._run_samples_dir(
        _batch_args(dataset, output),
        argparse.ArgumentParser(),
    )

    assert result == 0
    assert observed == [
        (
            str(pages),
            str(output / "Evenki-Russian"),
            str(alphabet),
            str(languages),
        )
    ]


def test_dataset_batch_fails_when_no_entry_has_supported_pages(tmp_path: Path) -> None:
    dataset = tmp_path / "dictionaries"
    (dataset / "Empty-Entry").mkdir(parents=True)

    result = extract._run_samples_dir(
        _batch_args(dataset, tmp_path / "output"),
        argparse.ArgumentParser(),
    )

    assert result == 1
