# uv_workspace fixture

A uv workspace with a root package and three member packages used to test workspace-aware dependency checks.

## Workspace structure

```
uv_workspace/
├── pyproject.toml              # workspace root (members = ["packages/*"]), also a package declaring `foo` as dep
├── uv_workspace_pkg/           # root package source: imports `foo` (ok) and `pandas` (undeclared)
└── packages/
    ├── bar/                    # exposes module `bar2`; declares `pandas` as dependency but never uses it
    ├── baz/                    # declares `foo` as dependency; imports workspace sibling `bar2`
    └── foo/                    # no declared dependencies; imports `pandas`.
```

## Expected violations

| Location | Code | Description |
|---|---|---|
| `uv_workspace_pkg/__init__.py:2:8` | DEP102 | `pandas` imported but not declared as a dependency — available only because `bar` declares it |
| `packages/bar/pyproject.toml` | DEP002 | `pandas` defined as a dependency but not used in the codebase |
| `packages/baz/baz/__init__.py:2:1` | DEP101 | `bar2` imported but `bar` is a uv workspace sibling not declared as a dependency |
| `packages/foo/foo/__init__.py:1:8` | DEP102 | `pandas` imported but not declared as a dependency — available only because `bar` declares it |
