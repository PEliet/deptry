from __future__ import annotations

from dataclasses import dataclass

from deptry.dependency_getter.builder import DependencyGetterBuilder
from deptry.imports.extract import get_imported_modules_from_list_of_files
from deptry.module import ModuleBuilder, ModuleLocations
from deptry.reporters import GithubReporter, JSONReporter, TextReporter
from deptry.scanners.base import ProjectScannerBase
from deptry.violations.finder import find_violations


@dataclass
class SingleProjectScanner(ProjectScannerBase):
    def run(self) -> None:
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

        violations = find_violations(
            imported_modules_with_locations,
            dependencies_extract.dependencies,
            self.config.ignore,
            self.config.per_rule_ignores,
            standard_library_modules,
        )
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

        self._exit(violations)
