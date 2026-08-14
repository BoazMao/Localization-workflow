# AGENTS.md

## Product

Localization Workflow is a local-first, single-user desktop application for video transcription and terminology-controlled translation.

## Architecture rules

- Use Python 3.12+ and PySide6.
- Keep UI code in `localization_workflow.ui`.
- Keep business rules independent of Qt wherever practical.
- Keep transcription and translation behind separate provider interfaces.
- Use stable UUIDs for transcript segments. Editing source text must never replace a segment ID.
- Store revision numbers on source segments. A translation is outdated when its recorded source revision differs from the segment revision.
- Use SQLite through SQLAlchemy; schema changes require Alembic migrations.
- Run FFmpeg as a subprocess through one media-service boundary. Never scatter subprocess calls through UI code.
- Keep API keys out of source, logs, fixtures, and the database.
- All network and media work must run outside the UI thread.
- Tests must not call paid AI APIs. Use deterministic fake providers.

## Commands

```powershell
python -m pip install -e ".[dev]"
python -m localization_workflow
ruff check .
ruff format --check .
mypy src
pytest
```

## Change discipline

- Read `docs/phase-one.md` and `docs/architecture.md` before changing scope or boundaries.
- Implement one milestone at a time.
- Add or update tests for business rules.
- Preserve unrelated changes.
- Record meaningful architectural decisions under `docs/decisions/`.
- Report verification performed and remaining limitations.
