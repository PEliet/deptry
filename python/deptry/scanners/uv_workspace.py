from __future__ import annotations

import logging
import site
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import TYPE_CHECKING

from deptry.scanners.single_project import SingleProjectScanner
from deptry.utils import load_pyproject_toml

if TYPE_CHECKING:
    from deptry.config import Config
    from deptry.core import UvWorkspaceConfig
    from deptry.violations import Violation


@dataclass
class UvWorkspaceScanner:
    config: Config
    workspace_config: UvWorkspaceConfig

    def scan(self) -> list[Violation]:
        members = self.workspace_config.members
        logging.info("Found %d uv workspace member(s):", len(members))
        for member in members:
            logging.info("  - %s", member)

        package_module_name_map = self._build_package_module_name_map(members)
        logging.info("Resolved package-to-module map from editable installs:")
        for package, modules in package_module_name_map.items():
            logging.info("  %s -> %s", package, ", ".join(modules))

        violations: list[Violation] = []
        for member in members:
            logging.info("Scanning workspace member: %s", member)
            member_package_name = self._get_package_name(member)
            member_module_names = (
                frozenset(package_module_name_map.get(member_package_name, ())) if member_package_name else frozenset()
            )
            sibling_module_names = (
                frozenset(
                    module_name
                    for pkg_name, module_names in package_module_name_map.items()
                    for module_name in module_names
                )
                - member_module_names
            )
            member_config = self.config.with_overrides({
                "config": member / "pyproject.toml",
                "root": (member,),
                "workspace_sibling_module_names": sibling_module_names,
            })
            violations += SingleProjectScanner(member_config).scan()
        return violations

    def _build_package_module_name_map(self, members: tuple[Path, ...]) -> dict[str, tuple[str, ...]]:
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
        """
        Use importlib.metadata to find the .pth file for the package, then discover
        top-level Python modules in the source root it points to.
        """
        try:
            dist = distribution(package_name)
        except PackageNotFoundError:
            logging.debug("Package '%s' is not installed in the current environment.", package_name)
            return ()

        site_packages_dirs = site.getsitepackages()

        for f in dist.files or []:
            if f.suffix != ".pth":
                continue
            for sp in site_packages_dirs:
                pth_path = Path(sp) / f
                if not pth_path.exists():
                    continue
                source_root = Path(pth_path.read_text(encoding="utf-8").strip())
                if not source_root.is_dir():
                    logging.debug(".pth for '%s' points to non-existent directory: %s", package_name, source_root)
                    continue
                return tuple(
                    entry.name if entry.is_dir() else entry.stem
                    for entry in sorted(source_root.iterdir())
                    if not entry.name.startswith(".")
                    and (
                        (entry.is_dir() and (entry / "__init__.py").exists())
                        or (entry.is_file() and entry.suffix == ".py" and entry.name != "__init__.py")
                    )
                )

        logging.debug("No .pth file found for package '%s'.", package_name)
        return ()
