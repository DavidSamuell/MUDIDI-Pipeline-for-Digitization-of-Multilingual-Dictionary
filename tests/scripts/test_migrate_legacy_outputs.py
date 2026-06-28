import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_SCRIPT = _REPO_ROOT / "scripts" / "migrate_legacy_outputs.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "migrate_legacy_outputs", _MIGRATION_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load_migration_module()
run_migration = _migration.run_migration
write_manifest = _migration.write_manifest


def test_run_migration_dry_run_and_copy(tmp_path: Path) -> None:
    legacy_root = tmp_path / "dictionaries"
    dataset_dir = tmp_path / "dataset" / "MUDIDI" / "dictionaries"
    dest_root = tmp_path / "outputs" / "benchmark"
    language = "Evenki-Russian"
    experiment = "gemini31pro_flat_alpha"
    page = "page_1"

    dataset_dir.mkdir(parents=True)
    (dataset_dir / language).mkdir()

    legacy_stage1 = (
        legacy_root
        / language
        / "outputs"
        / "stage-1"
        / experiment
        / page
        / f"{page}_stage1_flat.txt"
    )
    legacy_stage1.parent.mkdir(parents=True)
    legacy_stage1.write_text("pred\n", encoding="utf-8")

    dry = run_migration(
        legacy_root=legacy_root,
        dataset_dir=dataset_dir,
        dest_root=dest_root,
        dry_run=True,
        languages=[language],
    )
    assert len(dry.copied) == 1
    assert not (dest_root / "stage-1" / language).exists()

    manifest = run_migration(
        legacy_root=legacy_root,
        dataset_dir=dataset_dir,
        dest_root=dest_root,
        dry_run=False,
        languages=[language],
    )
    dest_file = (
        dest_root
        / "stage-1"
        / language
        / "stage-1"
        / experiment
        / page
        / f"{page}_stage1_flat.txt"
    )
    assert dest_file.is_file()
    assert dest_file.read_text(encoding="utf-8") == "pred\n"
    assert language in manifest.migrated_languages

    manifest_path = dest_root / "migration_manifest.json"
    write_manifest(manifest, manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["migrated_languages"] == [language]


def test_run_migration_skips_not_in_dataset(tmp_path: Path) -> None:
    legacy_root = tmp_path / "dictionaries"
    dataset_dir = tmp_path / "dataset" / "MUDIDI" / "dictionaries"
    dest_root = tmp_path / "outputs" / "benchmark"
    dataset_dir.mkdir(parents=True)

    old_only = "Amharic-English"
    legacy_file = (
        legacy_root
        / old_only
        / "outputs"
        / "stage-1"
        / "exp"
        / "page_1"
        / "page_1_stage1_flat.txt"
    )
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text("x\n", encoding="utf-8")

    manifest = run_migration(
        legacy_root=legacy_root,
        dataset_dir=dataset_dir,
        dest_root=dest_root,
        dry_run=False,
    )
    assert old_only in manifest.skipped_not_in_dataset
    assert not (dest_root / "stage-1" / old_only).exists()
