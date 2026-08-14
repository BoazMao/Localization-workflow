# ADR 0001: Native Python desktop stack

- Status: Accepted
- Date: 2026-08-13

## Context

The product is a personal, local-first audiovisual localization workspace. It needs desktop media playback, local filesystem access, background processing, SQLite storage, and external AI API integration. A browser interface is explicitly out of scope.

## Decision

Use Python 3.12+ with PySide6/Qt for the application. Use SQLAlchemy and Alembic with SQLite, FFmpeg/FFprobe for media processing, Pydantic for settings and boundary validation, and pytest/pytest-qt for verification.

## Rationale

Qt is a mature cross-platform desktop toolkit with multimedia, model/view, threading, and accessibility support. Python integrates cleanly with AI SDKs and media tooling. This keeps Phase One in one programming language and avoids maintaining a web server, browser runtime, or custom widget toolkit.

## Consequences

- Application packaging must eventually bundle Qt and provide or locate FFmpeg.
- Long operations require deliberate worker/thread boundaries.
- UI-specific code remains separated so core workflow rules are fast to test.
- Mature third-party libraries are preferred over bespoke replacements.
