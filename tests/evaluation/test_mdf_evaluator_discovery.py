from pathlib import Path

from mudidi.evaluation.stage2.mdf_evaluator import MdfEvaluator


def test_discover_dataset_tasks_uses_mudidi_dataset_layout(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset" / "MUDIDI" / "dictionaries"
    pred_root = tmp_path / "outputs" / "benchmark" / "stage-2-no-typography"
    language = "Evenki-Russian"
    experiment = "gemini31pro_high_mdf_intro_toolbox_gold_notypography"
    page = "page_1"

    gold = dataset / language / "Stage 2 MDF file" / page / f"{page}.mdf.txt"
    pred = pred_root / language / "stage-2" / experiment / page / f"{page}.mdf.txt"
    gold.parent.mkdir(parents=True)
    pred.parent.mkdir(parents=True)
    gold.write_text("\\lx gold\n", encoding="utf-8")
    pred.write_text("\\lx pred\n", encoding="utf-8")

    tasks = MdfEvaluator.discover_dataset_tasks(
        dataset,
        pred_root,
        experiments=[experiment],
        languages=[language],
    )

    assert len(tasks) == 1
    assert tasks[0].experiment == experiment
    assert tasks[0].page_id == f"{language}/{page}"
    assert tasks[0].gold_path == gold
    assert tasks[0].pred_path == pred
