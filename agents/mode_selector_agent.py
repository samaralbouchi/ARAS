"""Mode Selector Agent.

This module is the entry point of the AutoFix extension pipeline. It
sits between the existing Agentic Readiness Report and the new
AutoFix agent: given the standard AutoFix input contract (optionally
including a local `repo_path` or a remote `repo_url`), it decides
whether the rest of the pipeline can operate in `GIT_REPO` mode (real
diffs, real re-simulation) or must fall back to `BLACK_BOX` mode
(textual, human-applied suggestions only).

This agent MUST NOT:
    - generate fixes itself (that is the AutoFix agent's job)
    - decide whether a fix is acceptable (that is the Human
      validation agent's job)
    - score anything (that is the Simulation agent's job)

It only inspects/prepares a repo location and returns a
`ModeSelection`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from models.mode import ModeSelection, OperatingMode

_CLONE_TIMEOUT_SECONDS = 60


class ModeSelectorAgent:
    """Decides GIT_REPO vs BLACK_BOX for the AutoFix pipeline.

    Every collaborator that touches the filesystem or spawns processes
    is isolated behind small, overridable methods so tests can run
    without any real git binary or network access.
    """

    def __init__(self, work_dir: Optional[str] = None) -> None:
        """Initialize the agent.

        Args:
            work_dir: Base directory used to clone remote repos into
                when only a `repo_url` is given. Defaults to a fresh
                temp directory created on demand.
        """
        self._work_dir = work_dir

    def run(self, input_data: dict[str, Any]) -> ModeSelection:
        """Run the agent given the standard AutoFix input contract.

        Args:
            input_data: A dict that may contain:
                - `repo_path` (str, optional): local git working
                  directory.
                - `repo_url` (str, optional): remote git URL to clone
                  if no valid `repo_path` is given.

        Returns:
            The resulting `ModeSelection`.
        """
        return self.select(
            repo_path=input_data.get("repo_path"),
            repo_url=input_data.get("repo_url"),
        )

    def select(
        self,
        repo_path: Optional[str] = None,
        repo_url: Optional[str] = None,
    ) -> ModeSelection:
        """Select the operating mode for the AutoFix pipeline.

        Args:
            repo_path: Local filesystem path to a git working
                directory, if the caller already has one checked out.
            repo_url: Remote git URL to clone, used only when
                `repo_path` is absent or invalid.

        Returns:
            A `ModeSelection` describing the chosen mode, whether
            fixes may be applied, and why.
        """
        if repo_path:
            validated = self._validate_local_repo(repo_path)
            if validated is not None:
                return ModeSelection(
                    mode=OperatingMode.GIT_REPO,
                    can_apply_fixes=True,
                    repo_path=validated,
                    reason="Dépôt git local valide fourni.",
                    source="local",
                )
            # An explicit but invalid repo_path is a hard signal the
            # caller intended GIT_REPO mode: fall through to repo_url
            # only if one was also given, otherwise go black box with
            # a clear reason rather than silently ignoring the input.
            if not repo_url:
                return ModeSelection(
                    mode=OperatingMode.BLACK_BOX,
                    can_apply_fixes=False,
                    reason=(
                        f"repo_path '{repo_path}' invalide ou sans dossier "
                        f".git : repli en mode boîte noire."
                    ),
                    source="none",
                )

        if repo_url:
            cloned_path, error = self._clone_repo(repo_url)
            if cloned_path is not None:
                return ModeSelection(
                    mode=OperatingMode.GIT_REPO,
                    can_apply_fixes=True,
                    repo_path=cloned_path,
                    reason=f"Dépôt cloné avec succès depuis {repo_url}.",
                    source="cloned",
                )
            return ModeSelection(
                mode=OperatingMode.BLACK_BOX,
                can_apply_fixes=False,
                reason=(
                    f"Échec du clonage de {repo_url} ({error}) : "
                    f"repli en mode boîte noire."
                ),
                source="none",
            )

        return ModeSelection(
            mode=OperatingMode.BLACK_BOX,
            can_apply_fixes=False,
            reason="Aucun repo_path ni repo_url fourni : mode boîte noire par défaut.",
            source="none",
        )

    # ------------------------------------------------------------------
    # Local repo validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_local_repo(repo_path: str) -> Optional[str]:
        """Check that `repo_path` is an existing, writable git working dir.

        Args:
            repo_path: Candidate local filesystem path.

        Returns:
            The resolved absolute path as a string if valid, else
            `None`.
        """
        path = Path(repo_path).expanduser().resolve()

        if not path.is_dir():
            return None

        if not (path / ".git").exists():
            return None

        import os

        if not os.access(path, os.W_OK):
            return None

        return str(path)

    # ------------------------------------------------------------------
    # Remote clone
    # ------------------------------------------------------------------

    def _clone_repo(self, repo_url: str) -> tuple[Optional[str], str]:
        """Shallow-clone `repo_url` into a fresh working directory.

        Args:
            repo_url: Git remote URL to clone.

        Returns:
            A `(path, error)` tuple. On success `path` is the local
            clone directory and `error` is `""`. On failure `path` is
            `None` and `error` describes what went wrong.
        """
        if shutil.which("git") is None:
            return None, "git binaire introuvable sur cette machine"

        base = Path(self._work_dir) if self._work_dir else Path(tempfile.mkdtemp(prefix="aras_autofix_"))
        base.mkdir(parents=True, exist_ok=True)
        dest = base / "repo"

        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(dest)],
                capture_output=True,
                text=True,
                timeout=_CLONE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None, "délai de clonage dépassé"
        except Exception as exc:  # pragma: no cover - defensive
            return None, str(exc)

        if result.returncode != 0:
            return None, result.stderr.strip()[:300]

        return str(dest), ""