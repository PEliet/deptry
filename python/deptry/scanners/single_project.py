from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from deptry.dependency_getter.builder import DependencyGetterBuilder
from deptry.imports.extract import get_imported_modules_from_list_of_files
from deptry.module import ModuleBuilder, ModuleLocations
from deptry.scanners.base import ProjectScannerBase
from deptry.violations.finder import find_violations

if TYPE_CHECKING:
    from deptry.violations import Violation


@dataclass
class SingleProjectScanner(ProjectScannerBase):
    def scan(self) -> list[Violation]:
        self._log_config()

        dependency_getter = DependencyGetterBuilder(
            self.config.config,
            self.config.package_module_name_map,
            self.config.optional_dependencies_dev_groups,
            self.config.non_dev_dependency_groups,
            self.config.requirements_files,
            self.config.using_default_requirements_files,
            self.config.requirements_files_dev,
        ).build()

        dependencies_extract = dependency_getter.get()

        self._log_dependencies(dependencies_extract)

        python_files = self._find_python_files()
        local_modules = self._get_local_modules()
        standard_library_modules = self._get_standard_library_modules()

        imported_modules_with_locations = [
            ModuleLocations(
                ModuleBuilder(
                    module,
                    local_modules,
                    standard_library_modules,
                    dependencies_extract.dependencies,
                    dependencies_extract.dev_dependencies,
                ).build(),
                locations,
            )
            for module, locations in get_imported_modules_from_list_of_files(python_files).items()
        ]

        return find_violations(
            imported_modules_with_locations,
            dependencies_extract.dependencies,
            self.config.ignore,
            self.config.per_rule_ignores,
            standard_library_modules,
            self.config.workspace_sibling_module_names,
        )
