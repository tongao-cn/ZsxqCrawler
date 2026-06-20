import tempfile
import unittest
from pathlib import Path


class ScratchArtifactPathTests(unittest.TestCase):
    def test_resolve_scratch_artifact_path_stays_under_output_scratch(self):
        from scripts.artifact_paths import resolve_scratch_artifact_path

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            path = resolve_scratch_artifact_path(
                "stock analysis",
                "run-1",
                "manifest.json",
                project_root=project_root,
            )

        self.assertEqual(
            project_root / "output" / "scratch" / "stock-analysis" / "run-1" / "manifest.json",
            path,
        )

    def test_resolve_scratch_artifact_path_rejects_escape(self):
        from scripts.artifact_paths import resolve_scratch_artifact_path

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "escapes output/scratch"):
                resolve_scratch_artifact_path("stock-analysis", "..", "..", "root.log", project_root=Path(temp_dir))

    def test_ensure_scratch_artifact_path_creates_parent_directory(self):
        from scripts.artifact_paths import ensure_scratch_artifact_path

        with tempfile.TemporaryDirectory() as temp_dir:
            path = ensure_scratch_artifact_path(
                "stock-analysis",
                "archive",
                "result.json",
                project_root=Path(temp_dir),
            )

            self.assertTrue(path.parent.exists())
            self.assertFalse(path.exists())

    def test_find_forbidden_root_artifacts_matches_only_root_files(self):
        from scripts.check_scratch_artifacts import find_forbidden_root_artifacts

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            root_file = project_root / "tmp_stock_analysis_run.log"
            nested_file = project_root / "output" / "scratch" / "tmp_stock_analysis_run.log"
            nested_file.parent.mkdir(parents=True)
            root_file.write_text("root", encoding="utf-8")
            nested_file.write_text("nested", encoding="utf-8")

            matches = find_forbidden_root_artifacts(project_root)

        self.assertEqual([root_file], matches)
