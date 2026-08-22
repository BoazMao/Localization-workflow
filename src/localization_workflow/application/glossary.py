"""Project glossary management and terminology matching."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from localization_workflow.domain.projects import GlossaryEntry, Project, TranscriptSegment
from localization_workflow.infrastructure.database import GlossaryRepository, ProjectRepository


class GlossaryService:
    """Manage target-language terminology constraints."""

    def __init__(self, projects: ProjectRepository, glossary: GlossaryRepository) -> None:
        self._projects = projects
        self._glossary = glossary

    def set_target_language(self, project_id: str, language: str) -> Project:
        clean_language = language.strip()
        if clean_language not in {"English", "Simplified Chinese"}:
            raise ValueError("Target language must be English or Simplified Chinese.")
        project = self._require_project(project_id)
        updated = replace(
            project,
            target_language=clean_language,
            updated_at=datetime.now(UTC),
        )
        self._projects.update(updated)
        return updated

    def read_wordbank(self, project_id: str) -> str:
        return self._require_project(project_id).wordbank

    def save_wordbank(self, project_id: str, text: str) -> Project:
        project = self._require_project(project_id)
        updated = replace(project, wordbank=text.strip(), updated_at=datetime.now(UTC))
        self._projects.update(updated)
        return updated

    def list_entries(self, project_id: str) -> list[GlossaryEntry]:
        self._require_project(project_id)
        return self._glossary.list_for_project(project_id)

    def add_entry(self, project_id: str, source_term: str, target_term: str) -> GlossaryEntry:
        self._require_project(project_id)
        source, target = self._validate_terms(source_term, target_term)
        entry = GlossaryEntry(str(uuid4()), project_id, source, target)
        self._glossary.add(entry)
        return entry

    def update_entry(
        self,
        project_id: str,
        entry_id: str,
        source_term: str,
        target_term: str,
    ) -> GlossaryEntry:
        self._require_project(project_id)
        source, target = self._validate_terms(source_term, target_term)
        entry = GlossaryEntry(entry_id, project_id, source, target)
        self._glossary.update(entry)
        return entry

    def delete_entry(self, project_id: str, entry_id: str) -> None:
        self._require_project(project_id)
        self._glossary.delete(project_id, entry_id)

    def matches_for_text(self, project_id: str, text: str) -> list[GlossaryEntry]:
        entries = self.list_entries(project_id)
        matches = [entry for entry in entries if self._matches(entry.source_term, text)]
        return sorted(
            matches, key=lambda entry: (-len(entry.source_term), entry.source_term.casefold())
        )

    def matches_for_segments(
        self, project_id: str, segments: list[TranscriptSegment]
    ) -> dict[str, list[GlossaryEntry]]:
        entries = self.list_entries(project_id)
        return {
            segment.id: sorted(
                [entry for entry in entries if self._matches(entry.source_term, segment.text)],
                key=lambda entry: (-len(entry.source_term), entry.source_term.casefold()),
            )
            for segment in segments
        }

    def _require_project(self, project_id: str) -> Project:
        project = self._projects.get(project_id)
        if project is None:
            raise LookupError(project_id)
        return project

    @staticmethod
    def _validate_terms(source_term: str, target_term: str) -> tuple[str, str]:
        source = source_term.strip()
        target = target_term.strip()
        if not source:
            raise ValueError("Source term is required.")
        if not target:
            raise ValueError("Required translation is required.")
        return source, target

    @staticmethod
    def _matches(term: str, text: str) -> bool:
        pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
