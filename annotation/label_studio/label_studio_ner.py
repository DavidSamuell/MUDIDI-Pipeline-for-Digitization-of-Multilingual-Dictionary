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


def normalize_ls_task_dict(task: dict) -> dict:
    """Return a copy of *task* safe for :class:`NerTask` validation.

    Label Studio's export API may serialize ``predictions`` (and occasionally
    ``annotations``) as bare integer IDs rather than full objects. Drop any
    non-dict entries so validation and import can proceed.
    """
    normalized = dict(task)
    for key in ("predictions", "annotations"):
        items = normalized.get(key)
        if isinstance(items, list):
            normalized[key] = [item for item in items if isinstance(item, dict)]
    return normalized


def has_submitted_human_annotation(task: dict) -> bool:
    """True when *task* includes at least one full human annotation object.

    Label Studio exports may list bare integer IDs under ``annotations`` when only
    predictions exist; those stubs are stripped by :func:`normalize_ls_task_dict`.
    """
    normalized = normalize_ls_task_dict(task)
    return bool(normalized.get("annotations"))


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
    if isinstance(task, NerTask):
        parsed = task
    else:
        parsed = NerTask.model_validate(normalize_ls_task_dict(task))
    spans: List[LanguageSpan] = []
    for result in _latest_results(parsed):
        if result.type != LABELS_TYPE or not result.value.labels:
            continue
        value = result.value
        raw_slice = raw_text[value.start : value.end]
        if raw_slice != value.text and not _region_text_reconciles(raw_slice, value.text):
            raise SpanMapError(
                f"Label Studio region text {value.text!r} does not match "
                f"gold[{value.start}:{value.end}]={raw_slice!r}"
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


def _region_text_reconciles(raw_slice: str, region_text: str) -> bool:
    """True when a region's text differs from the gold slice only by a boundary-whitespace
    quirk of Label Studio's export.

    Label Studio sometimes prepends/appends the boundary newline of a multi-line
    selection to ``value.text`` — and serializes it as the *literal* escape ``\\n``
    (two characters) rather than a real newline. The region's ``start``/``end`` offsets
    stay correct, so we treat them as authoritative and only confirm the core content
    matches after unescaping and trimming surrounding whitespace. A genuinely different
    slice still fails (its trimmed content won't match).
    """
    unescaped = (
        region_text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
    )
    return unescaped.strip() == raw_slice.strip()


def _latest_results(task: NerTask) -> List[NerResult]:
    """Return the result regions to trust: latest annotation, else latest prediction."""
    source = task.annotations or task.predictions
    return source[-1].result if source else []


def _fill_gaps(spans: List[LanguageSpan], length: int) -> List[LanguageSpan]:
    """Insert ``SPACE`` spans so *spans* contiguously cover ``[0, length)``."""
    filled: List[LanguageSpan] = []
    cursor = 0
    prev: LanguageSpan | None = None
    for span in spans:
        if span.start < cursor:
            culprit = (
                f"[{prev.start}:{prev.end}]={prev.language!r}" if prev else f"ending at {cursor}"
            )
            raise SpanMapError(
                f"overlapping Label Studio regions: [{span.start}:{span.end}]="
                f"{span.language!r} overlaps the previous region {culprit}. "
                "Delete or trim one of the two overlapping spans in Label Studio and "
                "re-sync (a character cannot belong to two languages)."
            )
        if span.start > cursor:
            filled.append(LanguageSpan(start=cursor, end=span.start, language=SPACE))
        filled.append(span)
        cursor = span.end
        prev = span
    if cursor < length:
        filled.append(LanguageSpan(start=cursor, end=length, language=SPACE))
    return filled


# -- labelling config / label set --------------------------------------------------

# Distinct, high-contrast label colours so adjacent languages never share a hue
# (Label Studio's auto-assignment collides — e.g. Canala and META both rendering pink).
# Languages are coloured in order from this palette; META is always a neutral grey so it
# reads as "not a language". 14 hues cover the largest dictionary (max ~9 languages).
_LABEL_PALETTE = (
    "#4363D8",  # blue
    "#3CB44B",  # green
    "#F58231",  # orange
    "#911EB4",  # purple
    "#E6194B",  # red
    "#469990",  # teal
    "#F032E6",  # magenta
    "#9A6324",  # brown
    "#808000",  # olive
    "#000075",  # navy
    "#42D4F4",  # cyan
    "#BFEF45",  # lime
    "#FABED4",  # pink
    "#A9A9A9",  # slate
)
_META_COLOR = "#7A7A7A"  # neutral grey — META is an editorial marker, not a language


def _label_color(name: str, index: int) -> str:
    """Return a stable, distinct background colour for a label."""
    if name == META:
        return _META_COLOR
    return _LABEL_PALETTE[index % len(_LABEL_PALETTE)]


def build_labels_config(languages: List[str], *, image: bool = False) -> str:
    """Return the Label Studio labelling-interface XML for an NER project.

    The label set is the dictionary's languages plus ``META`` (markers). ``SPACE`` is
    never a UI label -- it is the implicit, unlabelled background. Each label is given a
    distinct ``background`` colour from ``_LABEL_PALETTE`` so no two share a hue.

    When ``image`` is True, the original dictionary page render is shown side-by-side
    as a read-only reference, bound to the task's ``$image_url`` field. Tasks built
    without an ``image_url`` should use ``image=False`` to avoid a broken image panel.
    """
    label_set = list(dict.fromkeys([*languages, META]))
    labels_xml = "\n".join(
        f'      <Label value="{name}" background="{_label_color(name, i)}"/>'
        for i, name in enumerate(label_set)
    )
    labels_block = (
        f'    <Labels name="{FROM_NAME}" toName="{TO_NAME}">\n'
        f"{labels_xml}\n"
        "    </Labels>\n"
        f'    <Text name="{TO_NAME}" value="$text"/>\n'
    )
    if not image:
        return f"<View>\n{labels_block}</View>\n"
    # Two-panel layout: original page render (left) | NER text + labels (right).
    return (
        "<View>\n"
        '  <View style="display: flex; gap: 1em;">\n'
        '    <View style="flex: 1; max-width: 45%;">\n'
        '      <Header value="Original dictionary page"/>\n'
        '      <Image name="page" value="$image_url" '
        'zoomControl="true" rotateControl="true"/>\n'
        "    </View>\n"
        '    <View style="flex: 1;">\n'
        f"{labels_block}"
        "    </View>\n"
        "  </View>\n"
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
