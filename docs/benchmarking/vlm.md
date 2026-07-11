# Advanced VLM backends

MinerU 2.5 Pro, PaddleOCR-VL 1.5, and GLM-OCR remain supported for Stage 1 benchmark extraction. Configure them through `pipeline.strategy: vlm_ocr` and the `vlm` YAML section.

These backends use separate environments and may start local inference servers. See `docs/uv.md` for environment setup. They are intentionally excluded from the production quickstart.

