# ADR 0002: Const-me Whisper as the initial transcription engine

- Status: Accepted
- Date: 2026-08-18

## Context

The application requires private, local, timestamped transcription on 64-bit Windows. The
user selected Const-me/Whisper as the foundation and requires full workflow integration,
not launching its separate desktop interface.

## Decision

Integrate the unmodified Const-me Whisper binaries and WhisperPS automation components
behind the application's `SpeechToTextProvider` boundary. The application will manage model
selection, invoke transcription, parse timestamped output into stable segments, and present
results in its own Qt workspace.

## Consequences

- The initial engine requires 64-bit Windows, Direct3D 11, AVX1, and F16C.
- Projects must specify a source language because this engine does not implement automatic
  language detection.
- Whisper binaries remain separately identifiable under Mozilla Public License 2.0, with
  their notices and source location included in distributions.
- A later provider can be added without replacing the transcript data model.
