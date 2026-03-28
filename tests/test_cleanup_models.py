from pathlib import Path

from tools.cleanup_models import cleanup_models


def test_cleanup_moves_non_model_files(tmp_path: Path):
    models = tmp_path / "models"
    archive = models / "archive"
    models.mkdir(parents=True, exist_ok=True)
    (models / "a.zip").write_text("zip", encoding="utf-8")
    (models / "b.json").write_text("json", encoding="utf-8")
    (models / "c.pt").write_text("pt", encoding="utf-8")
    (models / "legacy_placeholder").write_text("x", encoding="utf-8")

    moved = cleanup_models(models, archive, apply=True)
    assert moved == 1
    assert (archive / "legacy_placeholder").exists()
    assert (models / "a.zip").exists()
