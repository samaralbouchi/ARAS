"""Data contract for the Mode Selector Agent.

This module defines the single output type produced by the
`ModeSelectorAgent`: which operating mode the rest of the AutoFix
pipeline (AutoFix agent, Human validation agent, Simulation agent)
should run in for a given assessment.

No git operations or evidence collection belong here — this is a data
container only.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional


class OperatingMode(str, Enum):
    """The two ways the AutoFix pipeline can operate.

    Attributes:
        GIT_REPO: A local, writable git working directory is
            available. The AutoFix agent can generate real diffs and
            (after human validation) apply them; the Simulation agent
            can re-run the assessment against the patched code.
        BLACK_BOX: No source access is available, only the public
            URL. The AutoFix agent can only propose textual fixes
            (config snippets, headers, instructions) for a human to
            apply manually; the Simulation agent can at best re-run a
            live HTTP check, or skip.
    """

    GIT_REPO = "git_repo"
    BLACK_BOX = "black_box"


@dataclass(frozen=True)
class ModeSelection:
    """Result of selecting an operating mode for the AutoFix pipeline.

    Attributes:
        mode: The selected `OperatingMode`.
        can_apply_fixes: Whether downstream agents may write changes
            to disk (True only for `GIT_REPO` with a valid working
            directory).
        repo_path: Local filesystem path to the git working directory,
            when `mode` is `GIT_REPO`. `None` in `BLACK_BOX` mode.
        reason: Human-readable explanation of why this mode was
            selected (useful for the final report and for debugging
            fallbacks from GIT_REPO to BLACK_BOX).
        source: Where the repo came from: `"local"` (an existing local
            path was given), `"cloned"` (cloned from `repo_url`), or
            `"none"` (no repo, black box).
    """

    mode: OperatingMode
    can_apply_fixes: bool
    repo_path: Optional[str] = None
    reason: str = ""
    source: str = "none"

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the result.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)