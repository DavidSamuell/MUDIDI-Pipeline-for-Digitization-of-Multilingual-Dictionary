from pathlib import Path

from mudidi.evaluation.stage1.stage1_task_discovery import discover_dataset_tasks


def test_discover_dataset_tasks_uses_mudidi_dataset_layout(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset" / "MUDIDI" / "dictionaries"
    pred_root = tmp_path / "outputs" / "benchmark" / "stage-1"
    language = "Evenki-Russian"
    experiment = "gemini31pro_flat_alpha"
    page = "page_1"

    gold = (
        dataset
        / language
        / "Stage 1 Gold OCR"
        / page
        / f"{page}_stage1_GOLD_flat.txt"
    )
    pred = (
        pred_root
        / language
        / "stage-1"
        / experiment
        / page
        / f"{page}_stage1_flat.txt"
    )
    gold.parent.mkdir(parents=True)
    pred.parent.mkdir(parents=True)
    gold.write_text("gold line\n", encoding="utf-8")
    pred.write_text("pred line\n", encoding="utf-8")

    tasks = discover_dataset_tasks(
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


def test_discover_dataset_tasks_stage1_ocr_subdir(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset" / "MUDIDI" / "dictionaries"
    pred_root = tmp_path / "outputs" / "benchmark" / "stage-1"
    language = "Chukchi-Russian"
    experiment = "gemini31pro_flat_alpha_ocr"
    page = "page_12"

    gold = (
        dataset
        / language
        / "Stage 1 Gold OCR"
        / page
        / f"{page}_stage1_GOLD_flat.txt"
    )
    pred = (
        pred_root
        / language
        / "stage-1-ocr"
        / experiment
        / page
        / f"{page}_stage1_flat.txt"
    )
    gold.parent.mkdir(parents=True)
    pred.parent.mkdir(parents=True)
    gold.write_text("gold\n", encoding="utf-8")
    pred.write_text("pred\n", encoding="utf-8")

    tasks = discover_dataset_tasks(
        dataset,
        pred_root,
        experiments=[experiment],
        languages=[language],
        stage1_output_subdir="stage-1-ocr",
    )

    assert len(tasks) == 1
    assert tasks[0].pred_path == pred
