# ADR 0002: Const-me Whisper as the initial transcription engine

- Status: Accepted
- Date: 2026-08-18

## Context

The application requires private, local, timestamped transcription on 64-bit Windows. The
user selected Const-me/Whisper as the foundation and requires full workflow integration,
not launching its separate desktop interface.

## Decision

Integrate the unmodified Const-me Whisper binaries and official command-line component
behind the application's `SpeechToTextProvider` boundary. The application will manage model
selection, invoke transcription, parse timestamped output into stable segments, and present
results in its own Qt workspace.

## Consequences

- The initial engine requires 64-bit Windows, Direct3D 11, AVX1, and F16C.
- The CLI is used instead of WhisperPS because WhisperPS 1.12.0 returned zero timestamps
  for every segment during integration verification, while the same release's CLI returned
  the native timestamp intervals correctly.
- Projects must specify a source language because this engine does not implement automatic
  language detection.
- Whisper binaries remain separately identifiable under Mozilla Public License 2.0, with
  their notices and source location included in distributions.
- A later provider can be added without replacing the transcript data model.
