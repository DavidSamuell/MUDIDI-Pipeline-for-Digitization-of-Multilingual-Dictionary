"""
Pass 2: direct page transcription → Toolbox MDF text using a field profile.

Used by ``TwoStageLLMExtraction`` for Stage 2 MDF output.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from mudidi.config.run_config import PromptMode
from mudidi.llm import client as llm
from mudidi.llm.prompt_mode import prompt_id_for_mode
from mudidi.llm.prompt_store import get_prompt_store
from mudidi.schemas.field_map import FieldMapPrompt
from mudidi.utils.image import image_data_url, mime_type_for_path
from mudidi.utils.mdf_export import normalize_mdf_text
from mudidi.llm.prompts import (
    format_current_page_block,
    format_stage1_page_context_preamble,
    page_boundary_rules_prompt,
)
from mudidi.utils.page_context import (
    PageContext,
    format_neighbor_text_block,
    format_page_image_order_note,
)
from mudidi.utils.pdf_render import needs_pdf_rasterization

logger = logging.getLogger(__name__)


def direct_mdf_system_prompt(
    mode: PromptMode = "benchmark",
    page_context: PageContext | None = None,
) -> str:
    """Pass 2 direct MDF system prompt."""
    store = get_prompt_store()
    prompt_id = prompt_id_for_mode("stage_2_direct_mdf_system", mode)
    if mode == "inference":
        return store.format(
            prompt_id,
            page_boundary_rules=page_boundary_rules_prompt(),
        )
    return store.get(prompt_id)


def strip_markdown_fences(text: str) -> str:
    """Remove optional markdown code fences from model output."""
    text = text.strip()
    fence = re.search(r"```(?:mdf|text)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


def _toolbox_content_parts(
    toolbox_pdf: Path,
    *,
    model: str,
) -> tuple[str, list[dict]]:
    """Build prompt section and optional vision parts for the Toolbox MDF manual."""
    store = get_prompt_store()
    if needs_pdf_rasterization(model):
        logger.info(
            "Toolbox PDF %s attached as text reference for model %s",
            toolbox_pdf.name,
            model,
        )
        section = store.format(
            "stage_2_toolbox_text_section",
            mdf_marker_reference=store.get("mdf_marker_reference"),
        )
        return section, []

    section = store.get("stage_2_toolbox_pdf_section")
    return section, [
        {
            "type": "image_url",
            "image_url": {
                "url": image_data_url(str(toolbox_pdf), "application/pdf"),
            },
        }
    ]


def _neighbor_format_kwargs(
    mode: PromptMode,
    page_context: PageContext | None,
) -> dict[str, str]:
    if mode != "inference" or page_context is None:
        return {
            "page_boundary_rules": "",
            "current_page_context": "",
            "previous_page_context": "",
            "next_page_context": "",
            "page_image_order": "",
        }
    return {
        "page_boundary_rules": page_boundary_rules_prompt(),
        "current_page_context": format_current_page_block(page_context),
        "previous_page_context": format_neighbor_text_block(
            page_context.previous, label="previous_page"
        ),
        "next_page_context": format_neighbor_text_block(
            page_context.next, label="next_page"
        ),
        "page_image_order": format_page_image_order_note(page_context),
    }


def build_direct_mdf_messages(
    *,
    transcription: str,
    image_path: str,
    field_map: FieldMapPrompt,
    model: str,
    guides: str = "",
    toolbox_pdf: Optional[Path] = None,
    mode: PromptMode = "benchmark",
    page_context: PageContext | None = None,
) -> list[dict]:
    """Build LLM messages for Pass 2 direct MDF extraction."""
    guides_block = f"\n\nUSER DEFINED GUIDELINES\n{guides}" if guides.strip() else ""
    toolbox_section = ""
    toolbox_parts: list[dict] = []
    if toolbox_pdf and toolbox_pdf.is_file():
        toolbox_section, toolbox_parts = _toolbox_content_parts(
            toolbox_pdf,
            model=model,
        )
    user_prompt_id = prompt_id_for_mode("stage_2_direct_mdf_user", mode)
    user_text = get_prompt_store().format(
        user_prompt_id,
        transcription=transcription.strip(),
        field_block=field_map.format_prompt_block(),
        guides_block=guides_block,
        toolbox_section=toolbox_section,
        **_neighbor_format_kwargs(mode, page_context),
    )
    mime = mime_type_for_path(image_path)
    content: list[dict] = [{"type": "text", "text": user_text}]
    if mode == "inference" and page_context is not None:
        for neighbor in (page_context.previous, page_context.next):
            if neighbor is None:
                continue
            n_mime = mime_type_for_path(str(neighbor.image_path))
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url(str(neighbor.image_path), n_mime),
                    },
                }
            )
    content.append(
        {
            "type": "image_url",
            "image_url": {"url": image_data_url(image_path, mime)},
        }
    )
    content.extend(toolbox_parts)
    return [
        {
            "role": "system",
            "content": direct_mdf_system_prompt(mode=mode, page_context=page_context),
        },
        {"role": "user", "content": content},
    ]


def extract_direct_mdf(
    *,
    transcription: str,
    image_path: str,
    field_map: FieldMapPrompt,
    model: str,
    reasoning_effort: str,
    guides: str = "",
    toolbox_pdf: Optional[Path] = None,
    mode: PromptMode = "benchmark",
    page_context: PageContext | None = None,
) -> tuple[str, str, dict, list]:
    """
    Run Pass 2 direct MDF extraction.

    Returns:
        (mdf_text, raw_response, usage_dict, sanitized_messages)
    """
    messages = build_direct_mdf_messages(
        transcription=transcription,
        image_path=image_path,
        field_map=field_map,
        model=model,
        guides=guides,
        toolbox_pdf=toolbox_pdf,
        mode=mode,
        page_context=page_context,
    )
    raw, usage = llm.complete_with_usage(
        model=model,
        messages=messages,
        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
    )
    mdf_text = normalize_mdf_text(strip_markdown_fences(raw))
    return mdf_text, raw, usage, messages
