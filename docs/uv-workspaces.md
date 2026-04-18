---
icon: lucide/folder-tree
---
# uv Workspaces

_deptry_ has built-in support for [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/). When a workspace is
detected, _deptry_ scans each member package individually and applies workspace-aware dependency rules that catch issues
specific to multi-package projects.

## Detection

_deptry_ auto-detects uv workspaces by looking for a `[tool.uv.workspace]` section in the root `pyproject.toml`. No
extra CLI flag is needed.

## How it works

When a uv workspace is detected, _deptry_:

1. **Scans the root package** using the paths provided on the CLI (e.g. `deptry .` or `deptry src`).
2. **Auto-discovers and scans each workspace member** listed under `[tool.uv.workspace].members`.
3. **Builds a cross-member module map** from editable installs (`.pth` files) so that imports of sibling packages can be
   recognised and validated.

This means a single `deptry .` invocation checks every package in the workspace.

## Prerequisites

All workspace members must be editable-installed so that _deptry_ can discover their modules. Run:

```shell
uv sync --all-packages
```

before invoking _deptry_.

## Running deptry

From the workspace root, run:

```shell
uv run deptry .
```

If the root package uses a `src` layout, pass that directory instead:

```shell
uv run deptry src
```

## Configuration

- Each member can have its own `[tool.deptry]` section in its `pyproject.toml`. Member-level settings override the
  root-level defaults.
- Root-level dev dependencies (`[tool.uv.dev-dependencies]`, `[dependency-groups]`) are automatically merged into each
  non-root member's dev dependencies during scanning, since they are installed into the shared workspace environment.

## Workspace-specific rules

In addition to the [standard rules](rules-violations.md), _deptry_ applies two workspace-specific rules:

- [**DEP101** — Missing workspace dependency](rules-violations.md#missing-workspace-dependency-dep101): a module provided
  by a sibling workspace member is imported, but that sibling is not declared as a dependency.
- [**DEP102** — Workspace transitive dependency](rules-violations.md#workspace-transitive-dependency-dep102): a
  third-party package is imported without being declared as a dependency — it only resolves because another workspace
  member declares it.

These rules only apply when _deptry_ detects a uv workspace.

## Example

Consider the following workspace layout:

```
my-workspace/
├── pyproject.toml          # workspace root; depends on `foo`
├── my_workspace/
│   └── __init__.py         # imports `foo` (ok) and `pandas` (not declared)
└── packages/
    ├── bar/                # declares `pandas`; exposes module `bar2`
    ├── baz/                # declares `foo`; imports `bar2` without declaring `bar`
    └── foo/                # no dependencies; imports `pandas`
```

Root `pyproject.toml`:

```toml
[project]
name = "my-workspace"
dependencies = ["foo"]

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
foo = { workspace = true }
```

Running `deptry .` produces:

```
my_workspace/__init__.py:2:8: DEP102 'pandas' imported but is not declared as a dependency, it is available only because another workspace member declares it
packages/bar/pyproject.toml: DEP002 'pandas' defined as a dependency but not used in the codebase
packages/baz/baz/__init__.py:2:1: DEP101 'bar2' imported but it is a uv workspace sibling not declared as a dependency
packages/foo/foo/__init__.py:1:8: DEP102 'pandas' imported but is not declared as a dependency, it is available only because another workspace member declares it
```
