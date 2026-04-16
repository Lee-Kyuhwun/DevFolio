# Contributing to DevFolio

Thanks for contributing to DevFolio.

## Development Setup

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
pip install -e ".[dev]"
pytest
```

The project targets Python 3.11 or newer.

## Project Conventions

When making changes, follow the conventions already used in the codebase:

- use Pydantic v2 helpers such as `model_validate()` and `model_dump()`
- use `ruamel.yaml` for YAML handling
- keep heavy dependencies lazily imported when they are not needed for base CLI startup
- raise user-facing failures through `DevfolioError` subclasses with actionable hints where possible
- preserve the CLI-oriented workflow and local-first storage model

## Before You Start

For large features, workflow changes, or behavior changes that affect public CLI usage, open an issue or discussion first.

This helps avoid duplicated work and keeps the project direction consistent.

## Pull Request Guidance

- keep changes focused and scoped
- add or update tests when behavior changes
- make sure `pytest` passes before opening a PR
- update user-facing documentation when commands, flags, or workflows change

## Areas That Commonly Need Tests

- project and task CRUD behavior
- YAML and JSON import/export paths
- sync setup and sync execution behavior
- AI service fallbacks and error handling
- export and template behavior

## Documentation

If you change any public CLI workflow, update `README.md` as part of the same pull request.
