"""
Two-stage extraction strategy.

Pipeline
--------
Stage 1 — Transcription  (low/minimal reasoning, structured output)
  Inputs : image + alphabet (text or image) + optional OCR hint (txt/md/docx)
  Task   : Faithfully reproduce every character visible on the page (no interpretation).
  Output : TranscriptionResponse → list of lines → joined into plain text

Stage 2 — Direct MDF  (two-pass within Stage 2)
  Pass 1 : Discover MDF marker cheat sheet from intro + sample page.
  Pass 2 : Transcribe page into Toolbox MDF text using the field map.
  Output : MDF text on ``DictionaryPage.mdf_text``.

Reasoning budget rationale
--------------------------
Stage 1 is a copying/transcription task — creativity and inference are harmful.
  → reasoning_effort="low"  (maps to thinking_level: low on Gemini 3)

Stage 2 requires understanding multi-column layouts, abbreviations, cross-references,
and mapping text spans to MDF marker fields.
  → reasoning_effort="low" by default; bump only when needed for your model + pages.

Structured output rationale
---------------------------
Stage 1 uses response_format with a Pydantic schema enforced by the API:
  - TranscriptionResponse / FlatTranscriptionResponse
      Forces line-by-line enumeration; structurally prevents preamble/postamble.
Stage 2 emits free-form MDF text (Pass 2) after marker discovery (Pass 1).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Type
import json

from pydantic import BaseModel

from mudidi.evaluation.stage1.flatten import flat_transcription_to_text
from mudidi.extraction.base import ExtractionStrategy
from mudidi.llm.pass_1 import (
    find_parse_rules_path,
    load_gold_parse_rules,
    load_or_discover_parse_rules,
    load_parse_rules_file,
)
from mudidi.paths import PARSE_RULES_FILENAME
from mudidi.llm.pass_2 import extract_direct_mdf
from mudidi.schemas.field_cheatsheet import DictionaryMarkerCheatsheet
from mudidi.schemas.field_map import FieldMapPrompt
from mudidi.utils.stage1_input import read_stage1_transcript_text
from mudidi.schemas.dictionary_languages import DictionaryLanguagesConfig
from mudidi.schemas.entry import (
    DictionaryEntry,
    DictionaryPage,
    FlatTranscriptionResponse,
    FlatTranscriptionResponsePlain,
    TranscriptionResponse,
    TranscriptionResponsePlain,
)
from mudidi.schemas.ocr_result import OCRPageResult
from mudidi.llm import client as llm
from mudidi.config.run_config import PromptMode
from mudidi.llm.prompts import (
    stage_1_flat_system_prompt,
    stage_1_neighbor_image_urls,
    stage_1_system_prompt,
    stage_1_user,
    format_stage1_page_context_preamble,
)
from mudidi.utils.image import image_data_url, mime_type_for_path
from mudidi.utils.io import read_docx_text
from mudidi.utils.page_context import PageContext


def _stage1_response_schema(*, flat: bool, typography: bool) -> Type[BaseModel]:
    """Return the structured-output schema for Stage 1 transcription."""
    if flat:
        return FlatTranscriptionResponse if typography else FlatTranscriptionResponsePlain
    return TranscriptionResponse if typography else TranscriptionResponsePlain


def _sum_costs(c1, c2) -> Optional[float]:
    """Sum two nullable cost values."""
    if c1 is None and c2 is None:
        return None
    return round((c1 or 0.0) + (c2 or 0.0), 8)


def _print_usage_summary(s1: dict, s2: dict, total: Optional[float]) -> None:
    print("\n  ── Usage ──────────────────────────────────────────")
    for label, u in [("Stage 1", s1), ("Stage 2", s2)]:
        img = f"  img={u.get('image_tokens')}" if u.get("image_tokens") else ""
        cost = f"  ${u.get('cost_usd'):.6f}" if u.get("cost_usd") is not None else ""
        print(f"  {label}: {u.get('total_tokens')} tokens{img}{cost}")
    if total is not None:
        print(f"  Page total: ${total:.6f}")
    print()


def _sanitize_messages(messages: list) -> list:
    """
    Return a JSON-safe copy of the LLM messages with base64 image data replaced
    by a compact placeholder.  Keeps the full prompt text intact for debugging.
    """
    import copy, re
    sanitized = copy.deepcopy(messages)
    b64_pattern = re.compile(r"(data:[^;]+;base64,)(.+)")
    for msg in sanitized:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                m = b64_pattern.match(url)
                if m:
                    b64_len = len(m.group(2))
                    part["image_url"]["url"] = (
                        f"{m.group(1)}<{b64_len} chars omitted>"
                    )
            elif part.get("type") == "file":
                file_data = part.get("file", {}).get("file_data", "")
                m = b64_pattern.match(file_data)
                if m:
                    b64_len = len(m.group(2))
                    part["file"]["file_data"] = (
                        f"{m.group(1)}<{b64_len} chars omitted>"
                    )
    return sanitized


def _transcription_to_tsv(result: TranscriptionResponse) -> str:
    """
    Flatten a TranscriptionResponse into a TSV string.

    Format: column_id \\t line_number \\t text

    Header rows: column_id="header", line_number empty, one row per header line.
    Body rows:   column_id in {"left","center","right","single"}, line_number 1..N
                 within each column.
    Footer rows: column_id="footer", line_number empty, one row per footer line.

    Header/footer are page-level metadata (running title, page number, chapter
    abbreviation, etc.); Stage 2 ignores them, and Stage 1 evaluation excludes
    them from character/markup/read-order metrics.

    Example output for a two-column page with a header and a footer:
        column_id\\tline_number\\ttext
        header\\t\\tCHUKCHI-RUSSIAN DICTIONARY    A
        left\\t1\\tac-úkwʌn (сущ.) кремень
        left\\t2\\tбукв. жирный камень
        right\\t1\\tac-ékwəŋ (гл.) дробить
        right\\t2\\tсм. ac/æc
        footer\\t\\t— 12 —
    """
    rows = ["column_id\tline_number\ttext"]
    for line in result.header or []:
        rows.append(f"header\t\t{line}")
    for col in result.columns:
        for i, line in enumerate(col.lines, start=1):
            rows.append(f"{col.column_id}\t{i}\t{line}")
    for line in result.footer or []:
        rows.append(f"footer\t\t{line}")
    return "\n".join(rows)


class TwoStageLLMExtraction(ExtractionStrategy):
    """
    Two-stage strategy: Stage 1 transcribes faithfully, Stage 2 emits direct MDF.

    Args:
        transcribe_model:   Model used for Stage 1 (transcription).
        stage2_pass1_model: Model used for Stage 2 Pass 1 (parse-rules discovery).
        stage2_pass2_model: Model used for Stage 2 Pass 2 (per-page MDF).
        alphabet_path:      Path to the alphabet file (.txt / .png / .jpg).
                            If an image, it is sent as a vision input to Stage 1.
                            If text, it is embedded in the prompt.
        intro_text:         Introduction/preface plain text (reserved; not sent to Pass 2).
        intro_image_paths:  Intro page images for Stage 2 Pass 1 only (field discovery).
                            Loaded once, shared across the dictionary run.
    """

    def __init__(
        self,
        transcribe_model: str = "gemini/gemini-3-flash-preview",
        stage2_pass1_model: Optional[str] = None,
        stage2_pass2_model: Optional[str] = None,
        alphabet_path: Optional[str] = None,
        intro_text: str = "",
        intro_image_paths: Optional[List[str]] = None,
        stage1_reasoning_effort: str = "low",
        stage2_reasoning_effort: str = "low",
        temperature: float = 0.1,
        stage1_guides: str = "",
        stage2_guides: str = "",
        stage1_mode: str = "column",
        dictionary_languages: Optional[DictionaryLanguagesConfig] = None,
        entry_dir: Optional[str] = None,
        stage2_experiment_dir: Optional[str] = None,
        overwrite: bool = False,
        stage2_toolbox_pdf: Optional[str] = None,
        parse_rules_gold: bool = False,
        parse_rules_file: Optional[str] = None,
        parse_rules_samples: Optional[List[tuple[str, str, str]]] = None,
        prompt_mode: PromptMode = "benchmark",
        prompt_cache: str = "auto",
        media_reference: str = "auto",
        prompt_cache_key: Optional[str] = None,
        stage1_typography: bool = True,
    ):
        if stage1_mode not in ("column", "flat"):
            raise ValueError(f"stage1_mode must be 'column' or 'flat', got {stage1_mode!r}")
        self.transcribe_model = transcribe_model
        self.stage2_pass1_model = stage2_pass1_model or transcribe_model
        self.stage2_pass2_model = stage2_pass2_model or transcribe_model
        self.alphabet_path = alphabet_path
        self.intro_text = intro_text
        self.intro_image_paths = intro_image_paths or []
        self.stage1_reasoning_effort = stage1_reasoning_effort
        self.stage2_reasoning_effort = stage2_reasoning_effort
        self.temperature = temperature
        self.stage1_guides = stage1_guides
        self.stage2_guides = stage2_guides
        self.stage1_mode = stage1_mode
        self.dictionary_languages = dictionary_languages
        self.entry_dir = Path(entry_dir) if entry_dir else None
        self.stage2_experiment_dir = (
            Path(stage2_experiment_dir) if stage2_experiment_dir else None
        )
        self.overwrite = overwrite
        self.stage2_toolbox_pdf = (
            Path(stage2_toolbox_pdf) if stage2_toolbox_pdf else None
        )
        self.parse_rules_gold = parse_rules_gold
        self.parse_rules_file = Path(parse_rules_file) if parse_rules_file else None
        self.parse_rules_samples = parse_rules_samples or []
        self.prompt_mode: PromptMode = prompt_mode
        self.prompt_cache = prompt_cache
        self.media_reference = media_reference
        self.prompt_cache_key = prompt_cache_key
        self.stage1_typography = stage1_typography
        self._field_map: Optional[FieldMapPrompt] = None

    @property
    def name(self) -> str:
        return "llm_two_stage"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(
        self,
        ocr_result: OCRPageResult,
        image_path: str,
        page_number: int = 1,
        stage1_output_path: Optional[str] = None,
        stage2_output_path: Optional[str] = None,
        run_stage: str = "both",
        page_context: PageContext | None = None,
        **kwargs,
    ) -> DictionaryPage:
        """
        Run the two-stage pipeline.

        Args:
            ocr_result:          OCR output from any backend. The plain text is passed
                                 to Stage 1 as an optional character-shape reference.
            image_path:          Path to the dictionary page image.
            page_number:         Page number for provenance.
            stage1_output_path:  Path for the Stage 1 transcription TSV (e.g.
                                 ``<...>/stage-1/<page>/<page>_stage1.tsv``). The Stage 1
                                 raw/input JSONs are written next to it.
                                 Stage-2-only reads the transcription from this path.
            stage2_output_path:  Path for the final Stage 2 artifact base (e.g.
                                 ``<...>/stage-2/<page>/<page>.tsv``). The Stage 2
                                 raw/input/usage JSONs are derived from this path's
                                 stem. If omitted, Stage 2 artifacts fall back to
                                 living next to ``stage1_output_path`` (legacy layout).
            run_stage:           "1" = stage 1 only, "2" = stage 2 (Pass 1 + Pass 2),
                                 "both" = full pipeline, "2-pass-1" = Pass 1 only,
                                 "2-pass-2" = Pass 2 only (requires cached parse rules).
                                 Stage-2-only reads transcription from stage1_output_path.
        """
        stage1_usage: Dict[str, Any] = {}
        stage2_usage: Dict[str, Any] = {}
        entries: List[DictionaryEntry] = []
        mdf_text = ""
        discovery_usage: Dict[str, Any] = {}

        # ── Stage 1: transcription ─────────────────────────────────────────────
        if run_stage in ("1", "both"):
            print("=" * 60)
            print("Stage 1: Transcribing page image …")
            transcribed_text, stage1_raw, stage1_usage, stage1_msgs = (
                self._stage1_transcribe(ocr_result, image_path, page_context=page_context)
            )
            print(
                f"Transcription ({len(transcribed_text)} chars):\n{transcribed_text[:500]}…\n"
            )

            if stage1_output_path:
                base = Path(stage1_output_path)
                base.parent.mkdir(parents=True, exist_ok=True)
                base.write_text(transcribed_text, encoding="utf-8")
                stem_base = base.stem.replace("_stage1_flat", "").replace("_stage1", "")
                raw1_path = base.parent / f"{stem_base}_stage1_raw.json"
                input1_path = base.parent / f"{stem_base}_stage1_input.json"
                input1_path.write_text(
                    json.dumps(stage1_msgs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"Stage 1 saved → {base.name}  |  raw → {raw1_path.name}  |  input → {input1_path.name}")
        elif run_stage in ("2", "2-pass-2"):
            if not stage1_output_path or not Path(stage1_output_path).exists():
                raise FileNotFoundError(
                    f"Stage-2-only requires existing stage 1 transcript: {stage1_output_path}"
                )
            transcribed_text = read_stage1_transcript_text(Path(stage1_output_path))
            print("=" * 60)
            print(
                f"Stage 2 only: loaded existing transcription from {stage1_output_path} "
                f"({len(transcribed_text)} chars)"
            )

        # ── Stage 2: direct MDF ────────────────────────────────────────────────
        stage2_base: Optional[Path] = None
        if run_stage in ("2", "both", "2-pass-2"):
            # Resolve where Stage 2 artifacts live:
            #   - explicit stage2_output_path → use it (its stem becomes the artifact prefix).
            #   - else fall back to stage1 dir with the "_stage1" suffix stripped (legacy).
            if stage2_output_path:
                stage2_base = Path(stage2_output_path)
            elif stage1_output_path:
                s1 = Path(stage1_output_path)
                stage2_base = s1.with_name(
                    s1.stem.replace("_stage1_flat", "").replace("_stage1", "")
                    + s1.suffix
                )

            print("Stage 2: Direct MDF extraction …")
            field_map = self._ensure_field_map(
                transcribed_text, image_path, run_stage=run_stage
            )
            mdf_text, stage2_raw, stage2_usage, stage2_msgs = self._stage2_direct_mdf(
                transcribed_text,
                image_path,
                field_map,
                page_context=page_context,
            )
            print(f"Direct MDF ({len(mdf_text)} chars).")

            if stage2_base:
                stage2_base.parent.mkdir(parents=True, exist_ok=True)
                raw2_path = stage2_base.with_name(stage2_base.stem + "_stage2_raw.txt")
                raw2_path.write_text(stage2_raw, encoding="utf-8")
                input2_path = stage2_base.with_name(stage2_base.stem + "_stage2_input.json")
                input2_path.write_text(
                    json.dumps(stage2_msgs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"Stage 2 raw saved → {raw2_path.name}  |  input → {input2_path.name}")

        # ── Per-page usage summary ────────────────────────────────────────────
        usage_path: Optional[Path] = None
        if run_stage in ("2", "both", "2-pass-2") and stage2_base:
            usage_path = stage2_base.with_name(stage2_base.stem + "_usage.json")
        elif run_stage == "1" and stage1_output_path:
            s1 = Path(stage1_output_path)
            stem_base = s1.stem.replace("_stage1_flat", "").replace("_stage1", "")
            usage_path = s1.parent / f"{stem_base}_usage.json"

        if usage_path and (stage1_usage or stage2_usage or discovery_usage):
            total_cost = _sum_costs(
                _sum_costs(stage1_usage.get("cost_usd"), stage2_usage.get("cost_usd")),
                discovery_usage.get("cost_usd"),
            )
            page_usage = {
                "stage1": stage1_usage or None,
                "field_discovery": discovery_usage or None,
                "stage2": stage2_usage or None,
                "total_cost_usd": total_cost,
            }
            usage_path.parent.mkdir(parents=True, exist_ok=True)
            usage_path.write_text(
                json.dumps(page_usage, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if stage1_usage and stage2_usage:
                _print_usage_summary(stage1_usage, stage2_usage, total_cost)

        return DictionaryPage(
            entries=entries,
            page_number=page_number,
            source_file=image_path,
            mdf_text=mdf_text,
        )

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _stage1_transcribe(
        self,
        ocr_result: OCRPageResult,
        image_path: str,
        *,
        page_context: PageContext | None = None,
    ) -> tuple[str, str, dict, list]:
        """
        Call the transcription LLM (Stage 1) with structured output.
        Returns (transcribed_text, raw_json_str, usage_dict, sanitized_messages).
        """
        mime = mime_type_for_path(image_path)
        page_data_url = image_data_url(image_path, mime)

        alphabet_text, alphabet_image_url = self._load_alphabet()
        ocr_hint = ocr_result.raw_text if ocr_result else ""

        user_text = stage_1_user(
            alphabet_text=alphabet_text,
            ocr_hint=ocr_hint,
            guides=self.stage1_guides,
        )
        if self.prompt_mode == "inference" and page_context is not None:
            preamble = format_stage1_page_context_preamble(page_context)
            user_text = f"{preamble}\n\n{user_text}"

        content: list = [{"type": "text", "text": user_text}]
        if self.prompt_mode == "inference" and page_context is not None:
            for url in stage_1_neighbor_image_urls(page_context):
                content.append({"type": "image_url", "image_url": {"url": url}})
        if alphabet_image_url:
            content.append(
                {"type": "image_url", "image_url": {"url": alphabet_image_url}}
            )
        content.append({"type": "image_url", "image_url": {"url": page_data_url}})

        if self.stage1_mode == "flat":
            response_schema = _stage1_response_schema(
                flat=True,
                typography=self.stage1_typography,
            )
            messages = [
                {
                    "role": "system",
                    "content": stage_1_flat_system_prompt(
                        mode=self.prompt_mode,
                        page_context=page_context,
                        typography=self.stage1_typography,
                    ),
                },
                {"role": "user", "content": content},
            ]
            result, raw, usage = llm.complete_structured(
                model=self.transcribe_model,
                messages=messages,
                response_schema=response_schema,
                temperature=self.temperature,
                reasoning_effort=self.stage1_reasoning_effort,
            )
            flat_text = flat_transcription_to_text(
                result.header, result.lines, result.footer
            )
            return flat_text, raw, usage, _sanitize_messages(messages)

        response_schema = _stage1_response_schema(
            flat=False,
            typography=self.stage1_typography,
        )
        messages = [
            {
                "role": "system",
                "content": stage_1_system_prompt(
                    mode=self.prompt_mode,
                    typography=self.stage1_typography,
                ),
            },
            {"role": "user", "content": content},
        ]

        result, raw, usage = llm.complete_structured(
            model=self.transcribe_model,
            messages=messages,
            response_schema=response_schema,
            temperature=self.temperature,
            reasoning_effort=self.stage1_reasoning_effort,
        )
        return _transcription_to_tsv(result), raw, usage, _sanitize_messages(messages)

    def discover_parse_rules(self) -> FieldMapPrompt:
        """Run Stage 2 Pass 1 only and write ``parse-rules.json``."""
        return self._ensure_field_map("", "", run_stage="2-pass-1")

    def _ensure_field_map(
        self,
        transcribed_text: str,
        image_path: str,
        *,
        run_stage: str = "2",
    ) -> FieldMapPrompt:
        """Pass 1: load or discover field map once per dictionary."""
        del transcribed_text, image_path  # discovery uses configured sample page(s)
        if self._field_map is not None:
            return self._field_map

        if not self.stage2_experiment_dir:
            raise ValueError(
                "Stage 2 requires stage2_experiment_dir for field map cache."
            )

        cache_path = self.stage2_experiment_dir / PARSE_RULES_FILENAME
        if self.parse_rules_gold:
            if self.entry_dir is None:
                raise ValueError(
                    "parse_rules_gold requires entry_dir to locate outputs/stage-2-gold/"
                )
            print(
                "Pass 1: using gold parse rules "
                f"(outputs/stage-2-gold/{PARSE_RULES_FILENAME}) …"
            )
            self._field_map = load_gold_parse_rules(self.entry_dir)
            if self.overwrite or not cache_path.is_file():
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(self._field_map.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        elif self.parse_rules_file:
            print(f"Pass 1: loading parse rules file → {self.parse_rules_file}")
            self._field_map = load_parse_rules_file(self.parse_rules_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(self._field_map.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        elif run_stage == "2-pass-2":
            read_path = find_parse_rules_path(cache_path.parent)
            if not read_path.is_file():
                raise FileNotFoundError(
                    f"Stage 2 Pass 2 requires existing parse rules at {cache_path}. "
                    "Run with --stage 2-pass-1 first, or pass --parse-rules-file."
                )
            print(f"Pass 1: using cached parse rules → {read_path}")
            self._field_map = DictionaryMarkerCheatsheet.model_validate_json(
                read_path.read_text(encoding="utf-8")
            )
        else:
            intro_paths = [Path(p) for p in self.intro_image_paths]
            dictionary_name = self.entry_dir.name if self.entry_dir else ""
            if not self.parse_rules_samples:
                raise ValueError(
                    "Pass 1 parse-rules discovery requires configured sample page(s)."
                )

            if len(self.parse_rules_samples) == 1:
                stem, sample_text, sample_image = self.parse_rules_samples[0]
                discover_kwargs = dict(
                    transcription=sample_text,
                    sample_image=Path(sample_image),
                    intro_images=intro_paths,
                    model=self.stage2_pass1_model,
                    reasoning_effort=self.stage2_reasoning_effort,
                    temperature=self.temperature,
                    languages_config=self.dictionary_languages,
                    dictionary_name=dictionary_name,
                )
                multi_samples = None
                print(
                    f"Pass 1: parse rules discovery from sample {stem} (cache → {cache_path}) …"
                )
            else:
                discover_kwargs = dict(
                    intro_images=intro_paths,
                    model=self.stage2_pass1_model,
                    reasoning_effort=self.stage2_reasoning_effort,
                    temperature=self.temperature,
                    languages_config=self.dictionary_languages,
                    dictionary_name=dictionary_name,
                )
                multi_samples = [
                    (stem, sample_text, Path(sample_image))
                    for stem, sample_text, sample_image in self.parse_rules_samples
                ]
                sample_list = ", ".join(stem for stem, _, _ in multi_samples)
                print(
                    "Pass 1: multi-sample parse rules discovery "
                    f"from [{sample_list}] (cache → {cache_path}) …"
                )

            self._field_map = load_or_discover_parse_rules(
                cache_path,
                force_refresh=self.overwrite,
                parse_rules_file=None,
                multi_samples=multi_samples,
                **discover_kwargs,
            )

        print(self._field_map.format_prompt_block())
        return self._field_map

    def _stage2_direct_mdf(
        self,
        transcribed_text: str,
        image_path: str,
        field_map: FieldMapPrompt,
        page_context: PageContext | None = None,
    ) -> tuple[str, str, dict, list]:
        """Pass 2: direct MDF extraction using a field map."""
        mdf_text, raw, usage, messages = extract_direct_mdf(
            transcription=transcribed_text,
            image_path=image_path,
            field_map=field_map,
            model=self.stage2_pass2_model,
            reasoning_effort=self.stage2_reasoning_effort,
            temperature=self.temperature,
            guides=self.stage2_guides,
            toolbox_pdf=self.stage2_toolbox_pdf,
            mode=self.prompt_mode,
            page_context=page_context,
            prompt_cache=self.prompt_cache,
            media_reference=self.media_reference,
            prompt_cache_key=self.prompt_cache_key,
        )
        return mdf_text, raw, usage, _sanitize_messages(messages)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_alphabet(self) -> tuple[str, Optional[str]]:
        """
        Load the alphabet hint.  Returns (alphabet_text, alphabet_image_data_url).
        Exactly one of the two will be non-empty; the other will be ""/None.
        """
        if not self.alphabet_path:
            return "", None

        p = Path(self.alphabet_path)
        suffix = p.suffix.lower()

        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            mime = mime_type_for_path(str(p))
            return "", image_data_url(str(p), mime)

        if suffix == ".docx":
            return read_docx_text(str(p)), None

        # .txt / .md / anything else — read as plain text
        return p.read_text(encoding="utf-8"), None
