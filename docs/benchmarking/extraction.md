# Benchmark extraction

Stage 1 benchmark:

```bash
uv run mudidi benchmark run --config examples/configs/benchmark/stage1-benchmark.yaml
```

End-to-end Stage 2 benchmark:

```bash
uv run mudidi benchmark run --config examples/configs/benchmark/stage2-e2e-benchmark.yaml
```

Dataset-root sweeps and single-entry benchmark runs are both supported. Shell scripts remain useful for experiment matrices and copying fixed Stage 1 prediction trees.

