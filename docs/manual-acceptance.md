# Phase One Manual Acceptance Checklist

Use a representative 5–15 minute video and a non-production API key with a spending limit.

## Clean-machine setup

- [ ] Extract the complete portable release folder on 64-bit Windows.
- [ ] Launch without `.env`; confirm FFmpeg and FFprobe are detected or can be selected through the
      setup dialog and that the saved paths are reused on the next launch.
- [ ] Launch by double-clicking the executable without Python or a terminal.
- [ ] Confirm no terminal window appears and startup errors use a visible dialog.

## End-to-end workflow

- [ ] Create a project, close the app, reopen it, and confirm the project persists.
- [ ] Import and play the representative media file.
- [ ] Import different media and confirm its derived audio replaces the previous media's audio.
- [ ] Prepare mono 16 kHz transcription audio and test cancellation/restart.
- [ ] Select an existing model without copying it; edit and toggle the Whisper wordbank.
- [ ] Transcribe and verify multiple distinct timestamps against playback.
- [ ] Edit source text, save it, and confirm its revision increments.
- [ ] Configure target language, translation wordbank, AGENTS.md, and API details.
- [ ] Translate all in one contextual request; cancel once and confirm controls recover.
- [ ] Confirm API errors appear as errors and never as translated text.
- [ ] Edit translations, mark Reviewed and Approved, and filter each state.
- [ ] Edit approved source text and confirm its translation becomes Outdated.
- [ ] Click transcript and translation rows and confirm playback seeks to their timestamps.
- [ ] Export approved-only SRT and explicitly test draft-inclusive export.
- [ ] Open the SRT in a subtitle-capable player and verify order, Unicode text, and timing.

## Safety and recovery

- [ ] Restart after each major stage and confirm persisted state is unchanged.
- [ ] Temporarily use invalid tool/model/API paths and confirm actionable recovery messages.
- [ ] Confirm `.env`, API keys, media, models, databases, and exports are absent from Git history.
- [ ] Back up the closed data directory, restore it to the configured path, and reopen the project.

Record the Windows version, GPU, Whisper model, video duration, selected translation model, test
date, failures, and final result with the release candidate notes.
