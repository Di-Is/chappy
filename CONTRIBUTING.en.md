# Contributing Guide

[日本語](CONTRIBUTING.md) | **English**

Bug reports, feature suggestions, and pull requests are welcome.

## Reporting bugs and suggesting features

Open an issue on [Issues](https://github.com/Di-Is/qso-chappy/issues).
For bug reports, the following details make investigation much easier:

- What you were trying to do, and what happened instead
- Your OS and version (Windows / macOS / Linux)
- Any relevant excerpt from the logs (`~/.chappy/log/`)

## Development setup

### Prerequisites

- Python 3.12+
- [mise](https://mise.jdx.dev/) — tool version management
- [uv](https://github.com/astral-sh/uv) — Python package management

### Steps

1. Install mise and the pinned tools:

   ```bash
   curl https://mise.jdx.dev/install.sh | sh   # if not already installed
   mise install
   ```

2. Install dependencies:

   ```bash
   uv sync --all-extras
   ```

   `uv sync` creates `.venv` for you, so there is no need to run `uv venv` first.
   Every command below goes through `uv run`, so you never have to activate the environment either.

3. Install git hooks:

   ```bash
   lefthook install
   ```

   From then on, lint, type checks, and tests run automatically on every commit and push.
   See [`lefthook.yml`](lefthook.yml) for what each hook covers.

## Development workflow

### Running the application

```bash
uv run chappy
```

### Quality checks

```bash
uv run ruff check .           # linter
uv run ruff format .          # formatter
uv run mypy src/              # type checker
uv run pytest                 # tests
uv run lint-imports           # architecture boundary checks
```

To run a single test:

```bash
uv run pytest tests/test_voigt.py::TestVoigtProfile::test_gaussian_limit
```

### Generating the user manual

```bash
uv run --project docs/user_manual -m chappy_user_manual_generator
```

Output goes to `docs/user_manual/dist/` and is not committed.
For releases, GitHub Actions generates it and bundles it into the distributed package.

## Coding conventions

- Prioritize type safety and maintainability
- Internal structure is free to change; large rewrites are welcome when they improve
  maintainability and fit the architecture
- Do not leave code that is never executed

The layered architecture is enforced mechanically by `lint-imports` (the import-linter contracts in
`pyproject.toml`). If you need to add an import that crosses layers, consider whether the contract
itself should change.

## Versioning

Versions follow [Semantic Versioning](https://semver.org/).
As a GUI application, chappy exposes no public API for library consumers; instead, the following are
treated as the promise made to users:

- Saved file formats — projects (`.h5` / `.hdf5`) and presets (`~/.chappy/presets.json`)
- Command-line arguments and environment variables such as `CHAPPY_CONFIG_DIR`

| Change | Bump |
|--|--|
| Files saved by an earlier version no longer open, or an existing argument stops working | MAJOR |
| A feature is added (earlier files still open) | MINOR |
| Bug fixes only | PATCH |

When changing `PROJECT_SCHEMA_VERSION` (`src/chappy/application/project_schema.py`) or
`PRESET_FILE_SCHEMA_VERSION` (`src/chappy/infrastructure/preset_store.py`), always add a migration
path that reads the older format.
The current loader requires an exact schema-version match, so bumping the constant without a
migration makes every file a user has already saved fail to load.

### Release process

1. Update `version` in `pyproject.toml`
2. Push a `v<version>` tag (for example, `v1.2.0`)

Pushing the tag makes GitHub Actions generate the user manual, build the distributable package, and
publish the release. The package version is taken from `pyproject.toml`, so do step 1 first to keep
it in sync with the tag.

## Pull request process

1. Create a feature branch
2. Make your changes
3. Confirm that all quality checks above pass
4. Open a pull request

If you add or change user-facing text, update both the Japanese and English versions.
