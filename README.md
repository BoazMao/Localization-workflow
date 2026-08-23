# Localization Workflow

A local-first desktop workspace for AI-assisted video transcription and terminology-controlled translation.

## Phase One

The first usable release will import a video, extract audio, create a timestamped transcript, translate it with glossary constraints, support human review, and export SRT subtitles. Transcription and translation remain separate so a source only needs to be transcribed once.

## Technology

- Python 3.12+
- PySide6 (Qt) for the native desktop interface
- SQLAlchemy and Alembic for SQLite persistence
- FFmpeg/FFprobe for media processing
- Const-me/Whisper local speech-to-text behind a provider interface
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

5. Download `cli.zip` from the official Const-me/Whisper GitHub release and extract it.
6. Download a multilingual `ggml-*.bin` model from the official whisper.cpp model collection.
7. Copy `.env.example` to `.env`, then set `WHISPER_CLI_PATH` to `main.exe` and
   `WHISPER_MODEL_PATH` to the model file.
8. Run the desktop application:

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

## Build the portable Windows release

The project uses PyInstaller rather than maintaining a custom application bundler:

```powershell
.\scripts\build_windows.ps1
```

The complete portable package is written to `dist\Localization Workflow`. Keep the executable
and `_internal` folder together. On first launch the app detects FFmpeg and FFprobe or prompts for
their locations, then saves the configuration automatically. See `docs/user-guide.md` for
configuration, backups, and troubleshooting and
`docs/manual-acceptance.md` for the final release checklist.

## Local Windows environment

The current development checkout uses:

- source: `F:\Localization-workflow`
- virtual environment: `F:\Localization-workflow\.venv`
- runtime data: `F:\Localization-workflow-data`
- FFmpeg: `F:\Tools\FFmpeg`

The app detects FFmpeg and FFprobe on launch. Advanced local overrides can still be placed in
`.env`, then the app can be run with:

```powershell
.\.venv\Scripts\python.exe -m localization_workflow
```

## Local transcription requirements

- 64-bit Windows with a Direct3D 11-capable GPU
- CPU support for AVX1 and F16C
- An explicit source language on each project

The application invokes the unmodified official Const-me/Whisper CLI in a background worker.
The separate WhisperDesktop interface is not launched or required.
