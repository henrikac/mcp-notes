import os

import pytest

import notes


@pytest.fixture
def isolated_notes(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.delenv(notes.NOTES_PATH_ENV_VAR, raising=False)
    monkeypatch.setattr(notes, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(notes, "DATA_PATH", project_root / "data")
    monkeypatch.setattr(notes, "DEFAULT_NOTES_PATH", project_root / "data" / "notes")
    monkeypatch.setattr(
        notes,
        "DEFAULT_ARCHIVE_PATH",
        project_root / "data" / "archive",
    )
    monkeypatch.setattr(notes, "STORAGE_STATE_PATH", project_root / "data" / "storage.json")
    monkeypatch.setattr(notes, "NOTES_PATH", project_root / "data" / "notes")
    monkeypatch.setattr(notes, "ARCHIVE_PATH", project_root / "data" / "archive")
    monkeypatch.setattr(notes, "_STORAGE_INITIALIZED", False)

    return project_root


def test_initialize_storage_creates_default_directories_and_state(isolated_notes):
    notes.initialize_storage()

    assert notes.NOTES_PATH == (isolated_notes / "data" / "notes").resolve()
    assert notes.ARCHIVE_PATH == (isolated_notes / "data" / "archive").resolve()
    assert notes.NOTES_PATH.exists()
    assert notes.ARCHIVE_PATH.exists()
    assert notes.STORAGE_STATE_PATH.exists()


def test_initialize_storage_migrates_default_notes_to_custom_path(
    isolated_notes,
    monkeypatch,
    tmp_path,
):
    notes.DEFAULT_NOTES_PATH.mkdir(parents=True)
    (notes.DEFAULT_NOTES_PATH / "old.md").write_text("Old note\n", encoding="utf-8")
    custom_notes_path = tmp_path / "custom" / "notes"
    monkeypatch.setenv(notes.NOTES_PATH_ENV_VAR, str(custom_notes_path))

    notes.initialize_storage()

    assert notes.NOTES_PATH == custom_notes_path.resolve()
    assert (custom_notes_path / "old.md").read_text(encoding="utf-8") == "Old note\n"
    assert not (notes.DEFAULT_NOTES_PATH / "old.md").exists()


def test_initialize_storage_migrates_previous_storage_with_collision_suffix(
    isolated_notes,
    monkeypatch,
    tmp_path,
):
    previous_notes_path = tmp_path / "previous" / "notes"
    previous_archive_path = tmp_path / "previous" / "archive"
    new_notes_path = tmp_path / "new" / "notes"
    new_archive_path = tmp_path / "new" / "archive"
    previous_notes_path.mkdir(parents=True)
    previous_archive_path.mkdir(parents=True)
    new_notes_path.mkdir(parents=True)
    new_archive_path.mkdir(parents=True)
    (previous_notes_path / "dupe.md").write_text("Previous note\n", encoding="utf-8")
    (new_notes_path / "dupe.md").write_text("New note\n", encoding="utf-8")
    (previous_archive_path / "archived.md").write_text("Archived\n", encoding="utf-8")
    notes.write_storage_state(previous_notes_path, previous_archive_path)
    monkeypatch.setenv(notes.NOTES_PATH_ENV_VAR, str(new_notes_path))

    notes.initialize_storage()

    assert (new_notes_path / "dupe.md").read_text(encoding="utf-8") == "New note\n"
    assert (new_notes_path / "dupe-2.md").read_text(encoding="utf-8") == "Previous note\n"
    assert (new_archive_path / "archived.md").read_text(encoding="utf-8") == "Archived\n"


def test_custom_notes_path_returns_absolute_paths(isolated_notes, monkeypatch, tmp_path):
    custom_notes_path = tmp_path / "outside-project" / "notes"
    monkeypatch.setenv(notes.NOTES_PATH_ENV_VAR, str(custom_notes_path))

    created = notes.create_note("External Note", "Content")

    assert notes.NOTES_PATH == custom_notes_path.resolve()
    assert notes.ARCHIVE_PATH == (custom_notes_path.parent / "archive").resolve()
    assert created["path"] == str((custom_notes_path / "external-note.md").resolve())


def test_create_list_view_and_find_note(isolated_notes):
    created = notes.create_note("Symfony Cache", "Use cache pools.")

    assert created == {
        "title": "Symfony cache",
        "filename": "symfony-cache.md",
        "path": "data/notes/symfony-cache.md",
    }
    assert notes.fetch_notes() == [{"number": 1} | created]
    assert notes.view_note("1")["body"] == "Use cache pools.\n"
    assert notes.view_note("Symfony cache")["filename"] == "symfony-cache.md"
    assert notes.view_note("symfony-cache.md")["filename"] == "symfony-cache.md"
    assert notes.view_note("symfony-cache")["filename"] == "symfony-cache.md"


def test_create_note_rejects_empty_and_duplicate_titles(isolated_notes):
    with pytest.raises(ValueError, match="Title cannot be empty"):
        notes.create_note(" ", "Content")
    with pytest.raises(ValueError, match="Title must contain at least one letter or number"):
        notes.create_note("!!!", "Content")

    notes.create_note("Duplicate", "One")

    with pytest.raises(FileExistsError, match="Note already exists"):
        notes.create_note("Duplicate", "Two")


def test_append_to_note_preserves_content_and_optional_heading(isolated_notes):
    notes.create_note("Symfony Cache", "Initial")

    result = notes.append_to_note("1", "  Use pools.  ", "Tip")

    assert result["filename"] == "symfony-cache.md"
    assert notes.view_note("symfony-cache")["body"] == "Initial\n\n## Tip\n\n  Use pools.\n"


def test_append_and_update_reject_empty_inputs(isolated_notes):
    notes.create_note("Symfony Cache", "Initial")

    with pytest.raises(ValueError, match="Note identifier cannot be empty"):
        notes.append_to_note(" ", "More")
    with pytest.raises(ValueError, match="Content cannot be empty"):
        notes.append_to_note("symfony-cache", " ")
    with pytest.raises(ValueError, match="Content cannot be empty"):
        notes.update_note("symfony-cache", " ")


def test_update_note_replaces_body_and_preserves_filename(isolated_notes):
    notes.create_note("Symfony Cache", "Initial")

    result = notes.update_note("symfony-cache", "Replacement")

    assert result["filename"] == "symfony-cache.md"
    assert notes.view_note("symfony-cache")["body"] == "Replacement\n"


def test_archive_list_and_restore_note_with_collision_safe_suffix(isolated_notes):
    notes.create_note("Symfony Cache", "Archived body")
    archived = notes.archive_note("symfony-cache")

    assert archived["path"] == "data/archive/symfony-cache.md"
    assert notes.fetch_notes() == []
    assert notes.search_notes("Archived") == []
    assert notes.list_archived_notes()[0]["filename"] == "symfony-cache.md"

    notes.create_note("Symfony Cache", "Active collision")
    restored = notes.restore_note("1")

    assert restored["filename"] == "symfony-cache-2.md"
    assert sorted(file.name for file in notes.note_files()) == [
        "symfony-cache-2.md",
        "symfony-cache.md",
    ]


def test_visible_files_ignore_hidden_files(isolated_notes):
    notes.initialize_storage()
    (notes.NOTES_PATH / ".hidden.md").write_text("Hidden\n", encoding="utf-8")
    notes.create_note("Visible", "Visible\n")

    assert [file.name for file in notes.note_files()] == ["visible.md"]
    assert [item["filename"] for item in notes.fetch_notes()] == ["visible.md"]


def test_search_ranks_title_and_phrase_matches_over_content_only(isolated_notes):
    notes.create_note("Symfony Cache", "Use adapters for storage.")
    notes.create_note("Random Note", "This mentions symfony and later cache pools.")
    notes.create_note("No Match", "Banana apple pear.")

    results = notes.search_notes("symfony cache")

    assert [result["filename"] for result in results] == [
        "symfony-cache.md",
        "random-note.md",
    ]
    assert results[0]["score"] > results[1]["score"]
    assert "symfony" in results[1]["excerpt"].lower()
    assert notes.search_notes("missing") == []
    assert notes.search_notes(" ") == []


def test_recent_notes_sorts_by_modified_time_and_clamps_limit(isolated_notes):
    notes.create_note("Old", "Old")
    notes.create_note("Middle", "Middle")
    notes.create_note("New", "New")
    now = 1_800_000_000
    os.utime(notes.NOTES_PATH / "old.md", (now - 20, now - 20))
    os.utime(notes.NOTES_PATH / "middle.md", (now - 10, now - 10))
    os.utime(notes.NOTES_PATH / "new.md", (now, now))

    recent = notes.recent_notes()

    assert [result["filename"] for result in recent] == [
        "new.md",
        "middle.md",
        "old.md",
    ]
    assert "modified" in recent[0]
    assert "modified_timestamp" in recent[0]
    assert len(notes.recent_notes(2)) == 2
    assert len(notes.recent_notes(500)) == 3
    assert notes.recent_notes(-1) == []


def test_frontmatter_tags_and_tag_filtering(isolated_notes):
    plain = notes.create_note("Plain Note", "No metadata")
    tagged = notes.create_note(
        "Symfony Messenger",
        "Queue transport notes",
        ["Symfony", "queues", "symfony", "PHP!"],
    )

    assert "metadata" not in plain
    assert tagged["tags"] == ["php", "queues", "symfony"]
    viewed = notes.view_note("Symfony Messenger")
    assert viewed["metadata"]["title"] == "Symfony Messenger"
    assert viewed["metadata"]["tags"] == ["php", "queues", "symfony"]
    assert viewed["body"] == "Queue transport notes\n"
    assert viewed["content"].startswith("---\n")
    assert notes.list_tags() == [
        {"tag": "php", "count": 1},
        {"tag": "queues", "count": 1},
        {"tag": "symfony", "count": 1},
    ]
    assert [item["filename"] for item in notes.fetch_notes("Symfony")] == [
        "symfony-messenger.md"
    ]
    assert notes.create_note("No Tags", "Body", ["", "!!!"]) == {
        "title": "No tags",
        "filename": "no-tags.md",
        "path": "data/notes/no-tags.md",
    }


def test_append_and_update_refresh_updated_frontmatter(isolated_notes):
    notes.create_note("Symfony Messenger", "Queue transport notes", ["symfony"])
    before = notes.view_note("symfony-messenger")["metadata"]["updated"]

    notes.append_to_note("symfony-messenger", "More details")
    after_append = notes.view_note("symfony-messenger")

    assert after_append["metadata"]["updated"] >= before
    assert after_append["body"] == "Queue transport notes\n\nMore details\n"

    notes.update_note("symfony-messenger", "Replacement body")
    after_update = notes.view_note("symfony-messenger")

    assert after_update["metadata"]["tags"] == ["symfony"]
    assert after_update["body"] == "Replacement body\n"


def test_manual_frontmatter_and_malformed_frontmatter(isolated_notes):
    notes.initialize_storage()
    manual = notes.NOTES_PATH / "manual.md"
    manual.write_text(
        "---\ntitle: Manual Title\ntags: [Alpha, beta, alpha]\n---\n\nManual body\n",
        encoding="utf-8",
    )

    manual_view = notes.view_note("manual")

    assert manual_view["title"] == "Manual Title"
    assert manual_view["tags"] == ["alpha", "beta"]
    assert manual_view["body"] == "Manual body\n"

    broken = notes.NOTES_PATH / "broken.md"
    broken.write_text("---\ntags: [oops\n---\nBody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed frontmatter"):
        notes.view_note("broken")

    missing_close = notes.NOTES_PATH / "missing-close.md"
    missing_close.write_text("---\ntitle: Missing close\nBody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing closing ---"):
        notes.view_note("missing-close")


def test_backlinks_resolve_title_and_slug_links_while_ignoring_archived_notes(
    isolated_notes,
):
    notes.create_note("Symfony Cache", "Cache pools and adapters", ["symfony", "cache"])
    notes.create_note("Performance", "Use [[Symfony Cache]] for repeated reads")
    notes.create_note("Redis", "Redis can back [[symfony-cache]] pools")
    notes.create_note("Archived Source", "Old link [[Symfony Cache]]")
    notes.archive_note("archived-source")

    backlinks = notes.backlinks("symfony-cache")

    assert [item["filename"] for item in backlinks] == ["performance.md", "redis.md"]
    assert "Symfony Cache" in backlinks[0]["excerpt"]
    assert notes.backlinks("redis") == []


def test_find_related_notes_scores_links_tags_and_terms(isolated_notes):
    notes.create_note("Symfony Cache", "Cache pools and adapters", ["symfony", "cache"])
    notes.create_note(
        "Performance",
        "Use [[Symfony Cache]] for repeated reads",
        ["symfony"],
    )
    notes.create_note("Redis", "Redis can back [[symfony-cache]] pools", ["cache", "redis"])
    notes.create_note("Unrelated", "Banana apple pear")

    related = notes.find_related_notes("symfony-cache")
    filenames = [item["filename"] for item in related]

    assert "symfony-cache.md" not in filenames
    assert {"performance.md", "redis.md"}.issubset(filenames)
    assert [item["score"] for item in related] == sorted(
        [item["score"] for item in related],
        reverse=True,
    )
    assert any("wiki-link relationship" in item["reason"] for item in related)
    assert len(notes.find_related_notes("symfony-cache", 1)) == 1
    assert notes.find_related_notes("unrelated") == []


def test_invalid_wiki_link_labels_are_ignored(isolated_notes):
    notes.create_note("Target", "Target body")
    notes.create_note("Invalid Link", "Ignore [[!!!]] and keep going.")

    assert notes.backlinks("target") == []
    assert notes.find_related_notes("target") == []


def test_missing_notes_raise_clear_errors(isolated_notes):
    with pytest.raises(FileNotFoundError, match="Note not found"):
        notes.view_note("missing")
    with pytest.raises(FileNotFoundError, match="Note not found"):
        notes.backlinks("missing")
    with pytest.raises(FileNotFoundError, match="Note not found"):
        notes.find_related_notes("missing")
    with pytest.raises(FileNotFoundError, match="Archived note not found"):
        notes.restore_note("missing")
