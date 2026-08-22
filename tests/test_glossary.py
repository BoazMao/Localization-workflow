from pathlib import Path

import pytest
from test_projects import FakeAudioProcessor, FakeProbe

from localization_workflow.application.glossary import GlossaryService
from localization_workflow.application.projects import ProjectService
from localization_workflow.domain.projects import TranscriptSegment
from localization_workflow.infrastructure.database import (
    Database,
    GlossaryRepository,
    ProjectRepository,
    TranscriptRepository,
)
from localization_workflow.infrastructure.media import ManagedMediaStore


def make_services(tmp_path: Path) -> tuple[ProjectService, GlossaryService]:
    database = Database(tmp_path / "projects.sqlite3")
    database.migrate()
    projects_repository = ProjectRepository(database)
    projects = ProjectService(
        projects_repository,
        ManagedMediaStore(tmp_path / "media", FakeProbe()),
        FakeAudioProcessor(),
        TranscriptRepository(database),
    )
    glossary = GlossaryService(projects_repository, GlossaryRepository(database))
    return projects, glossary


def test_target_language_and_glossary_survive_reopen(tmp_path: Path) -> None:
    projects, glossary = make_services(tmp_path)
    project = projects.create("Terminology", "English")

    updated = glossary.set_target_language(project.id, "Spanish")
    entry = glossary.add_entry(project.id, "drop ship", "nave de desembarco")
    _projects_reopened, glossary_reopened = make_services(tmp_path)

    assert updated.target_language == "Spanish"
    assert projects.get(project.id).target_language == "Spanish"
    assert glossary_reopened.list_entries(project.id) == [entry]


def test_duplicate_source_term_is_case_insensitive(tmp_path: Path) -> None:
    projects, glossary = make_services(tmp_path)
    project = projects.create("Duplicates")
    glossary.add_entry(project.id, "Apex", "Ápice")

    with pytest.raises(ValueError, match="already exists"):
        glossary.add_entry(project.id, "apex", "Cumbre")


def test_matching_uses_whole_terms_and_longest_first(tmp_path: Path) -> None:
    projects, glossary = make_services(tmp_path)
    project = projects.create("Matching")
    short = glossary.add_entry(project.id, "ship", "nave")
    long = glossary.add_entry(project.id, "drop ship", "nave de desembarco")
    glossary.add_entry(project.id, "cat", "gato")
    segment = TranscriptSegment(
        "segment-1",
        project.id,
        0,
        0,
        1000,
        "The Drop Ship arrived near the ship catalog.",
    )

    matches = glossary.matches_for_segments(project.id, [segment])

    assert matches[segment.id] == [long, short]


def test_glossary_entry_can_be_updated_and_deleted(tmp_path: Path) -> None:
    projects, glossary = make_services(tmp_path)
    project = projects.create("Editing")
    entry = glossary.add_entry(project.id, "armor", "armadura")

    updated = glossary.update_entry(project.id, entry.id, "body armor", "blindaje")
    glossary.delete_entry(project.id, entry.id)

    assert updated.id == entry.id
    assert updated.source_term == "body armor"
    assert glossary.list_entries(project.id) == []
