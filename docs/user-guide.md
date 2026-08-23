# Localization Workflow User Guide

## Install the portable Windows build

1. Copy the entire `Localization Workflow` release folder to a writable location such as
   `F:\Apps\Localization Workflow`. Do not copy only the `.exe`; its `_internal` folder is
   required.
2. Double-click `Localization Workflow.exe`. The app automatically detects FFmpeg and FFprobe.
   If either tool is unavailable, select its `.exe` in the setup dialog; the companion tool in the
   same folder is filled automatically. Validated paths are saved for future launches.
3. If the Whisper CLI is unavailable, choose **Download Whisper CLI**, select an existing
   `main.exe`, or skip transcription setup for now. A validated path is saved automatically.
4. Open **Settings → AI model API settings** to enter or change translation API details.

Manual `.env` editing is not required for FFmpeg, FFprobe, or the Whisper CLI. Advanced users may
still create one from `.env.example` to override the default data directory or configure other
external tools.

The Whisper model remains external. Selecting an existing model records its path and does not
duplicate the model file.

## Data and backups

All projects, managed media, derived audio, wordbanks, and review states live under
`LOCALIZATION_WORKFLOW_DATA_DIR`. If that setting is blank, Windows chooses the application data
folder. The API key stays in the portable `.env` file and is not stored in the project database.

To back up the application while it is closed, copy both:

- the complete data directory;
- the `.env` file beside the executable.

Restore by putting those files back in their original locations. Keep `.env` private because it
contains the API key.

## Normal workflow

1. Create a project and choose the spoken source language.
2. Import media and prepare transcription audio.
3. Select an existing Whisper model, optionally enable its recognition wordbank, and transcribe.
4. Review and save source transcript edits.
5. Choose the target language and save translation context in the wordbank and AGENTS.md.
6. Translate all or selected segments, edit results, then mark them Reviewed or Approved.
7. Export SRT. Approved-only is the safe default; including Draft or Reviewed text requires an
   explicit choice. Outdated, failed, and missing translations are never exported.

## Troubleshooting

- **Media-tool setup appears:** choose `ffmpeg.exe` or `ffprobe.exe`. The app detects the other tool
  in the same folder, validates both, and saves their paths automatically.
- **Media import fails:** verify `FFPROBE_PATH`, file access, and free space in the data directory.
- **Prepare audio fails:** verify `FFMPEG_PATH` and that the selected media has an audio stream.
- **Transcribe stays unavailable:** prepare audio, choose a source language, and select an existing
  multilingual `ggml-*.bin` model.
- **Whisper fails:** verify the Const-me CLI and model paths, and confirm the PC supports its GPU
  and CPU requirements.
- **Translation fails:** review the neutral error details, API key, base URL, model selection, and
  network access. Error messages are not inserted as translations.
- **A translation is Outdated:** its source transcript changed. Regenerate it or manually edit and
  save it, then review and approve it again.
- **Export omits lines:** check the readiness summary. Outdated, failed, and missing lines cannot be
  exported; Draft and Reviewed lines require explicit inclusion.

## Uninstall

Close the app, delete the portable release folder, and optionally delete the configured data
directory. Removing the release folder alone does not delete project data stored elsewhere.
