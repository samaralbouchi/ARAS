"""Unit tests for :class:`ModeSelectorAgent`.

Covers: no repo info given (black box default), a valid local repo
(git repo mode), an invalid local repo path (fallback to black box
with a reason), and the `run()` standard input contract. Cloning from
a `repo_url` is exercised against a real local bare repo created on
disk in `setUp`, so no network access is required.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.mode_selector_agent import ModeSelectorAgent
from models.mode import OperatingMode


class ModeSelectorAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.agent = ModeSelectorAgent(work_dir=str(self.tmp_path / "work"))

    def _make_local_git_repo(self) -> Path:
        repo = self.tmp_path / "sample_repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo

    def test_no_repo_info_defaults_to_black_box(self) -> None:
        selection = self.agent.select()

        self.assertEqual(selection.mode, OperatingMode.BLACK_BOX)
        self.assertFalse(selection.can_apply_fixes)
        self.assertIsNone(selection.repo_path)
        self.assertEqual(selection.source, "none")

    def test_valid_local_repo_selects_git_repo_mode(self) -> None:
        repo = self._make_local_git_repo()

        selection = self.agent.select(repo_path=str(repo))

        self.assertEqual(selection.mode, OperatingMode.GIT_REPO)
        self.assertTrue(selection.can_apply_fixes)
        self.assertEqual(Path(selection.repo_path), repo.resolve())
        self.assertEqual(selection.source, "local")

    def test_invalid_local_repo_falls_back_to_black_box(self) -> None:
        not_a_repo = self.tmp_path / "not_a_repo"
        not_a_repo.mkdir()  # exists, but no .git

        selection = self.agent.select(repo_path=str(not_a_repo))

        self.assertEqual(selection.mode, OperatingMode.BLACK_BOX)
        self.assertFalse(selection.can_apply_fixes)
        self.assertIn("invalide", selection.reason)

    def test_nonexistent_local_repo_falls_back_to_black_box(self) -> None:
        selection = self.agent.select(repo_path=str(self.tmp_path / "does_not_exist"))

        self.assertEqual(selection.mode, OperatingMode.BLACK_BOX)
        self.assertFalse(selection.can_apply_fixes)

    def test_repo_url_clones_successfully(self) -> None:
        source_repo = self._make_local_git_repo()
        (source_repo / "README.md").write_text("hello")
        subprocess.run(["git", "-C", str(source_repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source_repo),
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=Test",
                "commit",
                "-q",
                "-m",
                "init",
            ],
            check=True,
        )

        selection = self.agent.select(repo_url=str(source_repo))

        self.assertEqual(selection.mode, OperatingMode.GIT_REPO)
        self.assertTrue(selection.can_apply_fixes)
        self.assertEqual(selection.source, "cloned")
        self.assertTrue((Path(selection.repo_path) / "README.md").exists())

    def test_invalid_repo_url_falls_back_to_black_box(self) -> None:
        selection = self.agent.select(repo_url="/path/that/does/not/exist")

        self.assertEqual(selection.mode, OperatingMode.BLACK_BOX)
        self.assertFalse(selection.can_apply_fixes)
        self.assertIn("Échec du clonage", selection.reason)

    def test_run_standard_input_contract(self) -> None:
        repo = self._make_local_git_repo()

        selection = self.agent.run({"repo_path": str(repo)})

        self.assertEqual(selection.mode, OperatingMode.GIT_REPO)


if __name__ == "__main__":
    unittest.main()