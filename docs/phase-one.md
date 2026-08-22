# Phase One Deliverable

## Goal

Deliver a local, single-user desktop application that takes one video from import through timestamped transcription, terminology-controlled translation, human review, and SRT export.

## Definition of done

A representative 5–15 minute video can complete this workflow:

1. Create and reopen a project.
2. Import and play a supported video or audio file.
3. Extract normalized audio with FFmpeg.
4. Transcribe into ordered segments with stable IDs and timestamps.
5. Edit source text without changing segment IDs.
6. Define glossary constraints for a target language.
7. Translate all or individual segments.
8. Mark translations outdated when the source revision changes.
9. Edit, regenerate, review, and approve translations.
10. Export approved translations as a valid SRT file.

Automated tests cover the critical data and workflow rules, and setup documentation works on a clean development machine.

## Milestones

### 0 — Foundation

Native desktop shell, project configuration, repository guidance, architecture records, automated checks, and documented setup.

### 1 — Projects and media import

Project creation/listing, safe media storage, FFprobe metadata, and desktop playback.

Implemented locally on the `agent/milestone-one` branch with SQLite/Alembic persistence,
managed media copies, background import, and Qt Multimedia playback.

### 2 — Media processing

FFmpeg audio extraction, progress state, reusable derived media, and actionable errors.

Implemented locally on `agent/milestone-two` with cancellable background processing,
validated mono 16 kHz PCM WAV output, persisted status, reuse, and failure cleanup.

### 3 — Transcription

Provider abstraction, Const-me/Whisper adapter, timestamp normalization, stable segment
persistence, deterministic test provider, and read-only transcript display.

### 4 — Transcript review

Segment editor, click-to-seek, save feedback, revision tracking, and restart persistence.

Implemented locally on `agent/milestone-four` with atomic source-text edits, stable segment
IDs, revision increments, click-to-seek playback, and unsaved-change protection.

### 5 — Glossary

Language-aware terminology entries, matching, constraints, and per-segment preview.

Implemented locally on `agent/milestone-five` with persistent target languages, validated
terminology CRUD, case-insensitive whole-term matching, and transcript constraint previews.

### 6 — Translation

Provider abstraction, target language selection, bulk and single translation, persistence, regeneration, and partial retry.

### 7 — Review and invalidation

Draft/review/approved/outdated states, editing, approval, filters, and source-revision invalidation.

Implemented locally with persistent human review states, editable translations, bulk review
and approval actions, state filters, and automatic source-revision invalidation.

### 8 — SRT export

Validated timestamps, ordered cues, warnings for missing or outdated translations, and downloadable export.

Implemented locally with export-readiness counts, approved-only and explicit draft-inclusive
modes, chronological timestamp validation, safe filenames, atomic UTF-8 BOM output, and clear
warnings for every omitted review state.

### 9 — Hardening

End-to-end verification, failure recovery, secret review, packaging documentation, and demonstration project.

## Deferred

Authentication, cloud deployment, collaboration, guaranteed diarization, word-level timing, dubbing, voice cloning, translation memory, timing-aware rewriting, bulk processing, and production billing.
