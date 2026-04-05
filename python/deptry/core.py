from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from deptry.exceptions import PyprojectFileNotFoundError
from deptry.reporters import GithubReporter, JSONReporter, TextReporter
from deptry.scanners.single_project import SingleProjectScanner
from deptry.scanners.uv_workspace import UvWorkspaceScanner
from deptry.utils import load_pyproject_toml

if TYPE_CHECKING:
    from pathlib import Path

    from deptry.config import Config


@dataclass
class UvWorkspaceConfig:
    members: tuple[Path, ...]


@dataclass
class Core:
    config: Config

    def run(self) -> None:
        uv_workspace_config = self._get_uv_workspace_config()
        if uv_workspace_config is None:
            violations = SingleProjectScanner(self.config).scan()
        else:
            violations = UvWorkspaceScanner(self.config, uv_workspace_config).scan()

        TextReporter(
            violations, enforce_posix_paths=self.config.enforce_posix_paths, use_ansi=not self.config.no_ansi
        ).report()

        if self.config.json_output:
            JSONReporter(
                violations, enforce_posix_paths=self.config.enforce_posix_paths, json_output=self.config.json_output
            ).report()

        if self.config.github_output:
            GithubReporter(
                violations,
                enforce_posix_paths=self.config.enforce_posix_paths,
                warning_ids=self.config.github_warning_errors,
            ).report()

        sys.exit(bool(violations))

    def _get_uv_workspace_config(self) -> UvWorkspaceConfig | None:
        try:
            pyproject_data = load_pyproject_toml(self.config.config)
        except PyprojectFileNotFoundError:
            return None

        workspace = pyproject_data.get("tool", {}).get("uv", {}).get("workspace")
        if not workspace:
            return None

        root = self.config.config.parent
        exclude_globs: list[str] = workspace.get("exclude", [])
        excluded = {path for glob_pattern in exclude_globs for path in root.glob(glob_pattern)}

        members = tuple(
            path
            for glob_pattern in workspace.get("members", [])
            for path in sorted(root.glob(glob_pattern))
            if path not in excluded
        )

        return UvWorkspaceConfig(members=members)
