from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from inline_snapshot import snapshot

from tests.functional.utils import Project

if TYPE_CHECKING:
    from tests.utils import UvVenvFactory


@pytest.mark.xdist_group(name=Project.UV_WORKSPACE)
def test_cli_with_uv_workspace(uv_venv_factory: UvVenvFactory) -> None:
    with uv_venv_factory(Project.UV_WORKSPACE) as virtual_env:
        result = virtual_env.run_deptry(".")

        assert result.returncode == 1
        assert result.stderr == snapshot("""\
Assuming the corresponding module name of package 'pandas' is 'pandas'. Install the package or configure a package_module_name_map entry to override this behaviour.
Assuming the corresponding module name of package 'foo' is 'foo'. Install the package or configure a package_module_name_map entry to override this behaviour.
Scanning 1 file...
Scanning 1 file...
Scanning 1 file...

packages/bar/pyproject.toml: DEP002 'pandas' defined as a dependency but not used in the codebase
packages/baz/baz/__init__.py:2:1: DEP001 'bar2' imported but missing from the dependency definitions
packages/foo/foo/__init__.py:1:8: DEP001 'pandas' imported but missing from the dependency definitions
Found 3 dependency issues.

For more information, see the documentation: https://deptry.com/
""")
