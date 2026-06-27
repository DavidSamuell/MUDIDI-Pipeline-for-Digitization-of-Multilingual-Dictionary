"""Offline converters between :class:`PageLanguageMap` and Label Studio NER tasks.

This is a pure format adapter -- no network, no Label Studio API. (The live sync
client is a later milestone; it reuses the existing ``LabelStudioClient`` in
``scripts/export_label_studio_gold.py``.)

A Label Studio NER task looks like::

    {"data": {"text": "<raw gold>", ...},
     "predictions": [{"model_version": "heuristic",
                      "result": [{"from_name": "label", "to_name": "text",
                                  "type": "labels",
                                  "value": {"start": 0, "end": 7,
                                            "text": "akɔɔtee", "labels": ["Canala"]}}]}]}

``start``/``end`` are codepoint offsets into ``data.text``; ``value.text`` must equal
``data.text[start:end]``. We emit only meaningful spans (skipping ``SPACE``); on import
the inter-span gaps are deterministically refilled with ``SPACE`` so coverage is total.
Round-trips are therefore lossless up to :meth:`PageLanguageMap.canonical`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from span_schema import (  # noqa: E402  (flat sibling import, see lid_spike.py)
    META,
    SPACE,
    LabeledVia,
    LanguageSpan,
    PageLanguageMap,
    SpanMapError,
    sha256_of,
)

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a project dependency
    yaml = None  # type: ignore[assignment]

# Must match build_labels_config(): the control names Label Studio binds spans to.
FROM_NAME = "label"
TO_NAME = "text"
LABELS_TYPE = "labels"


# -- minimal Label Studio NER models -----------------------------------------------


class LabelValue(BaseModel):
    """The ``value`` payload of a Label Studio ``labels`` result."""

    model_config = ConfigDict(extra="ignore")

    start: int
    end: int
    text: str
    labels: List[str] = Field(default_factory=list)


class NerResult(BaseModel):
    """A single Label Studio NER result region."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    from_name: str = FROM_NAME
    to_name: str = TO_NAME
    type: str = LABELS_TYPE
    value: LabelValue


class NerPrediction(BaseModel):
    """A prediction (or annotation) bucket holding NER result regions."""

    # ``protected_namespaces=()`` lets us keep Label Studio's ``model_version`` key.
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_version: str = ""
    result: List[NerResult] = Field(default_factory=list)


class NerTask(BaseModel):
    """A Label Studio task with optional predictions and submitted annotations."""

    model_config = ConfigDict(extra="ignore")

    data: dict = Field(default_factory=dict)
    predictions: List[NerPrediction] = Field(default_factory=list)
    annotations: List[NerPrediction] = Field(default_factory=list)


# -- converters --------------------------------------------------------------------


def page_map_to_ls_task(
    page_map: PageLanguageMap,
    raw_text: str,
    *,
    include_fill: bool = False,
) -> dict:
    """Convert a span map into a Label Studio NER task dict (with predictions).

    Args:
        page_map: the language span map (must bind to ``raw_text``).
        raw_text: the immutable raw gold text (becomes the task ``text``).
        include_fill: if True, also emit ``SPACE`` spans (default: skip them for a
            cleaner annotation UI; they are reconstructed on import).

    Raises:
        SpanMapError: if ``page_map`` does not bind to / fully cover ``raw_text``.
    """
    page_map.validate_against(raw_text)
    results: List[NerResult] = []
    for index, span in enumerate(page_map.spans):
        if span.language == SPACE and not include_fill:
            continue
        results.append(
            NerResult(
                id=f"r{index}",
                value=LabelValue(
                    start=span.start,
                    end=span.end,
                    text=raw_text[span.start : span.end],
                    labels=[span.language],
                ),
            )
        )
    task = NerTask(
        data={
            "text": raw_text,
            "page_name": f"page_{page_map.page}",
            "language": page_map.dictionary,
            "rule_set": page_map.rule_set,
        },
        predictions=[NerPrediction(model_version=page_map.labeled_via, result=results)],
    )
    return task.model_dump()


def ls_task_to_page_map(
    task: dict | NerTask,
    raw_text: str,
    *,
    dictionary: str,
    page: int,
    labeled_via: LabeledVia = "label-studio",
    rule_set: str = "",
) -> PageLanguageMap:
    """Reconstruct a full-coverage span map from a Label Studio NER task.

    Submitted ``annotations`` win over ``predictions`` (human correction is final).
    Gaps between labelled regions are refilled with ``SPACE``.

    Raises:
        SpanMapError: if a region's ``value.text`` does not match the gold slice, or
            if regions overlap, or the rebuilt map fails its invariants.
    """
    parsed = task if isinstance(task, NerTask) else NerTask.model_validate(task)
    spans: List[LanguageSpan] = []
    for result in _latest_results(parsed):
        if result.type != LABELS_TYPE or not result.value.labels:
            continue
        value = result.value
        if raw_text[value.start : value.end] != value.text:
            raise SpanMapError(
                f"Label Studio region text {value.text!r} does not match "
                f"gold[{value.start}:{value.end}]={raw_text[value.start:value.end]!r}"
            )
        spans.append(
            LanguageSpan(start=value.start, end=value.end, language=value.labels[0])
        )
    spans.sort(key=lambda span: span.start)
    page_map = PageLanguageMap(
        dictionary=dictionary,
        page=page,
        source_text_sha=sha256_of(raw_text),
        rule_set=rule_set,
        labeled_via=labeled_via,
        spans=_fill_gaps(spans, len(raw_text)),
    ).canonical()
    page_map.validate_against(raw_text)
    return page_map


def _latest_results(task: NerTask) -> List[NerResult]:
    """Return the result regions to trust: latest annotation, else latest prediction."""
    source = task.annotations or task.predictions
    return source[-1].result if source else []


def _fill_gaps(spans: List[LanguageSpan], length: int) -> List[LanguageSpan]:
    """Insert ``SPACE`` spans so *spans* contiguously cover ``[0, length)``."""
    filled: List[LanguageSpan] = []
    cursor = 0
    for span in spans:
        if span.start < cursor:
            raise SpanMapError(
                f"overlapping Label Studio regions near offset {span.start}"
            )
        if span.start > cursor:
            filled.append(LanguageSpan(start=cursor, end=span.start, language=SPACE))
        filled.append(span)
        cursor = span.end
    if cursor < length:
        filled.append(LanguageSpan(start=cursor, end=length, language=SPACE))
    return filled


# -- labelling config / label set --------------------------------------------------


def build_labels_config(languages: List[str]) -> str:
    """Return the Label Studio labelling-interface XML for an NER project.

    The label set is the dictionary's languages plus ``META`` (markers). ``SPACE`` is
    never a UI label -- it is the implicit, unlabelled background.
    """
    label_set = list(dict.fromkeys([*languages, META]))
    labels_xml = "\n".join(f'    <Label value="{name}"/>' for name in label_set)
    return (
        "<View>\n"
        f'  <Labels name="{FROM_NAME}" toName="{TO_NAME}">\n'
        f"{labels_xml}\n"
        "  </Labels>\n"
        f'  <Text name="{TO_NAME}" value="$text"/>\n'
        "</View>\n"
    )


def load_label_set(dictionary_dir: str | Path) -> List[str]:
    """Read source + target language names from a dictionary's ``dictionary_languages.yaml``."""
    path = Path(dictionary_dir) / "dictionary_languages.yaml"
    if yaml is None or not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    languages: List[str] = []
    source = data.get("source")
    if isinstance(source, dict) and source.get("language"):
        languages.append(str(source["language"]))
    for target in data.get("targets") or []:
        if isinstance(target, dict) and target.get("language"):
            languages.append(str(target["language"]))
    return list(dict.fromkeys(languages))
