from __future__ import annotations

import logging
import re
import site
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import TYPE_CHECKING

from deptry.dependency_getter.base import DependenciesExtract
from deptry.dependency_getter.pep621.uv import UvDependencyGetter
from deptry.scanners.project import ProjectScanner
from deptry.utils import load_pyproject_toml

if TYPE_CHECKING:
    from importlib.metadata import Distribution

    from deptry.config import Config
    from deptry.core import UvWorkspaceConfig
    from deptry.violations import Violation


@dataclass
class UvWorkspaceScanner:
    config: Config
    uv_workspace_config: UvWorkspaceConfig

    def scan(self) -> list[Violation]:
        root_path = self.config.config.parent
        all_members = (root_path, *self.uv_workspace_config.members)

        package_module_map = self._build_workspace_package_module_name_map(all_members)
        member_configs, member_dependency_extracts = self._collect_member_configs_and_dependency_extracts(all_members)
        all_workspace_modules = frozenset(m for modules in package_module_map.values() for m in modules)

        violations: list[Violation] = []
        for member in all_members:
            logging.debug("Scanning workspace member: %s", member)
            violations += self._scan_member(
                member, member_configs[member], member_dependency_extracts, package_module_map, all_workspace_modules
            )
        return violations

    def _collect_member_configs_and_dependency_extracts(
        self, all_members: tuple[Path, ...]
    ) -> tuple[dict[Path, Config], dict[Path, DependenciesExtract]]:
        """Build a Config and resolve dependencies for every workspace member."""
        configs: dict[Path, Config] = {}
        extracts: dict[Path, DependenciesExtract] = {}
        for member in all_members:
            config = self._build_member_base_config(member)
            configs[member] = config
            extracts[member] = UvDependencyGetter(
                member / "pyproject.toml",
                config.package_module_name_map,
                config.optional_dependencies_dev_groups,
                config.non_dev_dependency_groups,
            ).get()
        return configs, extracts

    def _scan_member(
        self,
        member: Path,
        config: Config,
        member_dependency_extracts: dict[Path, DependenciesExtract],
        package_module_map: dict[str, tuple[str, ...]],
        all_workspace_modules: frozenset[str],
    ) -> list[Violation]:
        """Scan a single workspace member with full sibling context."""
        extract = self._build_member_dependency_extract(member, member_dependency_extracts)

        member_package_name = self._get_package_name(member)
        member_modules = (
            frozenset(package_module_map.get(member_package_name, ())) if member_package_name else frozenset()
        )
        sibling_modules, sibling_deps = self._get_sibling_context(
            member, all_workspace_modules, member_modules, member_dependency_extracts
        )

        return ProjectScanner(config, extract, sibling_modules, sibling_deps).scan()

    def _build_member_dependency_extract(
        self, member: Path, member_dependency_extracts: dict[Path, DependenciesExtract]
    ) -> DependenciesExtract:
        """For non-root members, merge in the root's dev dependencies (they live in the shared environment)."""
        root_path = self.config.config.parent
        if member == root_path:
            return member_dependency_extracts[member]
        return DependenciesExtract(
            dependencies=member_dependency_extracts[member].dependencies,
            dev_dependencies=[
                *member_dependency_extracts[member].dev_dependencies,
                *member_dependency_extracts[root_path].dev_dependencies,
            ],
        )

    @staticmethod
    def _get_sibling_context(
        member: Path,
        all_workspace_modules: frozenset[str],
        member_modules: frozenset[str],
        member_dependency_extracts: dict[Path, DependenciesExtract],
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Compute the module names and dependency names from all sibling members."""
        sibling_modules = all_workspace_modules - member_modules
        sibling_deps = frozenset(
            dep.name
            for other_member, extract in member_dependency_extracts.items()
            if other_member != member
            for dep in (*extract.dependencies, *extract.dev_dependencies)
        )
        return sibling_modules, sibling_deps

    def _build_member_base_config(self, member: Path) -> Config:
        """Build a Config for a workspace member, applying any [tool.deptry] from its pyproject.toml.

        For the workspace root, member directories are excluded to avoid scanning their files twice.
        For other members, any [tool.deptry] overrides from their pyproject.toml are applied."""
        if member == self.config.config.parent:
            # Exclude member directories so their files are only scanned during their own member scan.
            root_path = self.config.config.parent
            member_excludes = tuple(re.escape(str(m.relative_to(root_path))) for m in self.uv_workspace_config.members)
            return self.config.with_overrides({
                "extend_exclude": (*self.config.extend_exclude, *member_excludes),
            })

        try:
            data = load_pyproject_toml(member / "pyproject.toml")
        except FileNotFoundError:
            data = {}
        member_deptry_config = data.get("tool", {}).get("deptry", {})
        return self.config.with_overrides({
            **member_deptry_config,
            "config": member / "pyproject.toml",
            "root": (member,),
        })

    def _build_workspace_package_module_name_map(self, members: tuple[Path, ...]) -> dict[str, tuple[str, ...]]:
        """
        For each workspace member, find its editable-install .pth file via importlib.metadata,
        resolve the source root it points to, and discover top-level Python modules there.
        Returns a mapping of {package_name: (module_name, ...)}.
        """
        result: dict[str, tuple[str, ...]] = {}

        for member in members:
            package_name = self._get_package_name(member)
            if package_name is None:
                logging.debug("Could not determine package name for %s, skipping.", member)
                continue

            modules = self._get_modules_for_package(package_name)
            if modules:
                logging.debug("Package '%s': modules: %s", package_name, modules)
                result[package_name] = modules

        return result

    @staticmethod
    def _get_package_name(member: Path) -> str | None:
        """Read the distribution name from the member's pyproject.toml."""
        try:
            data = load_pyproject_toml(member / "pyproject.toml")
        except FileNotFoundError:
            return None
        name = data.get("project", {}).get("name")
        return str(name) if name is not None else None

    @staticmethod
    def _get_modules_for_package(package_name: str) -> tuple[str, ...]:
        """Use importlib.metadata to find the editable-install .pth file for the package,
        then discover top-level Python modules in the source root it points to."""
        try:
            dist = distribution(package_name)
        except PackageNotFoundError:
            logging.debug("Package '%s' is not installed in the current environment.", package_name)
            return ()

        source_root = UvWorkspaceScanner._find_pth_source_root(package_name, dist)
        if source_root is None:
            logging.debug("No .pth file found for package '%s'.", package_name)
            return ()

        return UvWorkspaceScanner._collect_top_level_modules(source_root)

    @staticmethod
    def _find_pth_source_root(package_name: str, dist: Distribution) -> Path | None:
        """Locate the editable-install .pth file in site-packages and return the source root it points to."""
        for f in (f for f in dist.files or [] if f.suffix == ".pth"):
            for sp in site.getsitepackages():
                pth_path = Path(sp) / f
                if not pth_path.exists():
                    continue
                source_root = Path(pth_path.read_text(encoding="utf-8").strip())
                if source_root.is_dir():
                    return source_root
                logging.debug(".pth for '%s' points to non-existent directory: %s", package_name, source_root)
        return None

    @staticmethod
    def _collect_top_level_modules(source_root: Path) -> tuple[str, ...]:
        """Discover top-level Python packages and modules directly under source_root."""
        return tuple(
            entry.name if entry.is_dir() else entry.stem
            for entry in sorted(source_root.iterdir())
            if not entry.name.startswith(".")
            and (
                (entry.is_dir() and (entry / "__init__.py").exists())
                or (entry.is_file() and entry.suffix == ".py" and entry.name != "__init__.py")
            )
        )
