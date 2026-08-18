# Localization Workflow

A local-first desktop workspace for AI-assisted video transcription and terminology-controlled translation.

## Phase One

The first usable release will import a video, extract audio, create a timestamped transcript, translate it with glossary constraints, support human review, and export SRT subtitles. Transcription and translation remain separate so a source only needs to be transcribed once.

## Technology

- Python 3.12+
- PySide6 (Qt) for the native desktop interface
- SQLAlchemy and Alembic for SQLite persistence
- FFmpeg/FFprobe for media processing
- OpenAI speech-to-text behind a provider interface
- Pluggable translation providers

The project deliberately uses mature open-source libraries instead of rebuilding desktop, database, and media foundations.

## Development setup

1. Install Python 3.12 or newer.
2. Install FFmpeg and ensure `ffmpeg` and `ffprobe` are available on `PATH`.
3. Create and activate a virtual environment.
4. Install the project:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

5. Copy `.env.example` to `.env` and add API credentials when provider work begins.
6. Run the desktop application:

   ```powershell
   python -m localization_workflow
   ```

## Verification

```powershell
ruff check .
ruff format --check .
mypy src
pytest
```

## Local Windows environment

The current development checkout uses:

- source: `F:\Localization-workflow`
- virtual environment: `F:\Localization-workflow\.venv`
- runtime data: `F:\Localization-workflow-data`
- FFmpeg: `F:\Tools\FFmpeg`

Copy `.env.example` to `.env`, configure the data directory and FFprobe path, then run:

```powershell
.\.venv\Scripts\python.exe -m localization_workflow
```

## Status

Milestone 1 provides persistent projects, managed video/audio import, FFprobe metadata,
and embedded Qt playback. Transcription begins in a later milestone.
