"""Tests for prompt cache and media reference configuration."""

from __future__ import annotations

import argparse

from mudidi.config.run_config import RunConfig


def test_run_config_carries_prompt_cache_options() -> None:
    args = argparse.Namespace(
        benchmark=False,
        pages="pages",
        input_image=None,
        output_dir="out",
        output=None,
        stage="all",
        stage1_source=None,
        experiment_name="default",
        stage2_experiment_name=None,
        stage1_output_subdir="stage-1",
        samples_dir=None,
        languages=None,
        intro=None,
        alphabet=None,
        ocr_text=None,
        parse_rules_page=None,
        cheatsheet_page=None,
        prompt_cache="off",
        media_reference="inline",
        prompt_cache_key="custom-key",
    )

    config = RunConfig.from_namespace(args)

    assert config.prompt_cache == "off"
    assert config.media_reference == "inline"
    assert config.prompt_cache_key == "custom-key"


def test_run_config_apply_to_namespace_sets_prompt_cache_options() -> None:
    config = RunConfig(
        pages_dir="pages",
        output_dir="out",
        prompt_cache="auto",
        media_reference="file-uri",
        prompt_cache_key="dictionary-cache",
    )
    args = argparse.Namespace()

    config.apply_to_namespace(args)

    assert args.prompt_cache == "auto"
    assert args.media_reference == "file-uri"
    assert args.prompt_cache_key == "dictionary-cache"
