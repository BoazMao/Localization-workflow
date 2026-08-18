# Architecture

## Shape

Localization Workflow is a local-first modular desktop application. PySide6 owns presentation and interaction; application services coordinate use cases; domain objects enforce workflow rules; infrastructure adapters handle SQLite, files, FFmpeg, and external AI providers.

```text
Qt UI
  -> Application services
      -> Domain model
      -> Repository interfaces
      -> SpeechToTextProvider
      -> TranslationProvider
      -> Media service
          -> SQLAlchemy / SQLite
          -> Local files
          -> FFmpeg / FFprobe
          -> External provider adapters
```

Dependencies point inward. Domain and application logic must remain usable in tests without constructing Qt widgets.

## Module direction

- `ui`: windows, dialogs, view models, and Qt workers
- `application`: workflow orchestration and commands
- `domain`: entities, value objects, statuses, and invariants
- `providers`: transcription and translation contracts/adapters
- `infrastructure`: database, filesystem, media subprocesses, settings
- `core`: small cross-cutting primitives with no feature ownership

Feature modules will be added only when their milestone begins.

## Concurrency

Video processing and API requests cannot run on the Qt UI thread. Long-running operations use explicit workers that report progress, completion, cancellation, and structured errors.

## Persistence

SQLite is accessed through SQLAlchemy. Alembic owns schema migrations. Original media, derived audio, and exports live under the application data directory; the database stores managed paths and metadata, not video blobs.

Milestone 1 introduces `ProjectService` as the application boundary. It coordinates a
`ProjectRepository` and `ManagedMediaStore`; the Qt interface does not issue SQL or media
subprocess commands directly. Database startup runs the bundled Alembic migrations.

## Managed media

Imported media is copied into an application-owned directory scoped by project UUID. The
original user-selected file is never modified. FFprobe runs behind `FFprobeMediaProbe`, and
its provider-specific JSON is normalized into a `MediaInfo` domain value. Replacement and
deletion operate only on paths verified to remain beneath the managed media root.

## Stable segment rule

Every transcript segment receives a UUID that survives source-text edits. A segment has a monotonically increasing source revision. Each translation records the source revision from which it was produced. A mismatch makes that translation outdated without deleting it.

## Provider boundaries

Transcription and translation are separate protocols. Provider-specific request/response formats are normalized at the adapter boundary. Automated tests use deterministic fake providers and never call paid services.

## Secrets

Credentials come from environment variables or a future operating-system credential store. They are never committed, logged, included in exported projects, or persisted in plain text by the application.
