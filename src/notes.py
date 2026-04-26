import json
import os
import shutil
from datetime import UTC
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data"
DEFAULT_NOTES_PATH = DATA_PATH / "notes"
DEFAULT_ARCHIVE_PATH = DATA_PATH / "archive"
NOTES_PATH_ENV_VAR = "KNOWLEDGE_ASSISTANT_NOTES_PATH"
STORAGE_STATE_PATH = DATA_PATH / "storage.json"
NOTES_PATH = DEFAULT_NOTES_PATH
ARCHIVE_PATH = DEFAULT_ARCHIVE_PATH
_STORAGE_INITIALIZED = False


def initialize_storage() -> Path:
    """Initialize note storage and migrate notes if the configured path changed."""
    global ARCHIVE_PATH, NOTES_PATH, _STORAGE_INITIALIZED

    configured_path = os.environ.get(NOTES_PATH_ENV_VAR, "").strip()
    desired_path = (
        Path(configured_path).expanduser()
        if configured_path
        else DEFAULT_NOTES_PATH
    ).resolve()
    desired_archive_path = (desired_path.parent / "archive").resolve()

    previous_path, previous_archive_path = read_previous_storage_paths()
    migration_source = previous_path if previous_path != desired_path else None
    archive_migration_source = (
        previous_archive_path
        if previous_archive_path != desired_archive_path
        else None
    )

    if migration_source is None and configured_path and DEFAULT_NOTES_PATH != desired_path:
        migration_source = DEFAULT_NOTES_PATH
    if (
        archive_migration_source is None
        and configured_path
        and DEFAULT_ARCHIVE_PATH != desired_archive_path
    ):
        archive_migration_source = DEFAULT_ARCHIVE_PATH

    desired_path.mkdir(parents=True, exist_ok=True)
    desired_archive_path.mkdir(parents=True, exist_ok=True)

    if migration_source is not None:
        migrate_notes(migration_source, desired_path)
    if archive_migration_source is not None:
        migrate_notes(archive_migration_source, desired_archive_path)

    write_storage_state(desired_path, desired_archive_path)
    NOTES_PATH = desired_path
    ARCHIVE_PATH = desired_archive_path
    _STORAGE_INITIALIZED = True
    return NOTES_PATH


def fetch_notes() -> list[dict[str, str | int]]:
    """Return ordered display metadata for all saved notes."""
    ensure_storage()
    return [
        {
            "number": index,
            "title": normalize_file_name(file),
            "filename": file.name,
            "path": display_path(file),
        }
        for index, file in enumerate(note_files(), start=1)
    ]


def search_notes(query: str) -> list[dict[str, str | int]]:
    """Search note titles and contents with ranked results."""
    ensure_storage()
    search_query = normalize_search_query(query)
    if not search_query:
        return []

    results = []
    for file in note_files():
        content = file.read_text(encoding="utf-8")
        title = normalize_file_name(file)
        score = search_score(title, content, search_query)

        if score > 0:
            results.append({
                "title": title,
                "filename": file.name,
                "path": display_path(file),
                "score": score,
                "excerpt": extract_search_excerpt(content, search_query),
            })

    return sorted(results, key=lambda result: (-int(result["score"]), result["title"]))


def recent_notes(limit: int = 10) -> list[dict[str, str | int | float]]:
    """Return active notes ordered by most recent modification time."""
    ensure_storage()
    clamped_limit = max(0, min(limit, 100))
    files = sorted(
        note_files(),
        key=lambda file: file.stat().st_mtime,
        reverse=True,
    )

    return [
        {"number": index} | note_metadata(file) | modified_metadata(file)
        for index, file in enumerate(files[:clamped_limit], start=1)
    ]


def append_to_note(
    identifier: str,
    content: str,
    heading: str | None = None,
) -> dict[str, str]:
    """Append Markdown content to an existing note."""
    ensure_storage()
    if not content.strip():
        raise ValueError("Content cannot be empty.")

    note_path = require_note(identifier)
    existing_content = note_path.read_text(encoding="utf-8").rstrip("\n")
    append_parts = []

    normalized_heading = heading.strip() if heading is not None else ""
    if normalized_heading:
        append_parts.append(f"## {normalized_heading}")

    append_parts.append(content.rstrip())
    appended_content = "\n\n".join(append_parts)

    if existing_content:
        new_content = f"{existing_content}\n\n{appended_content}\n"
    else:
        new_content = f"{appended_content}\n"

    note_path.write_text(new_content, encoding="utf-8")
    return note_metadata(note_path)


def update_note(identifier: str, content: str) -> dict[str, str]:
    """Replace the full Markdown content of an existing note."""
    ensure_storage()
    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("Content cannot be empty.")

    note_path = require_note(identifier)
    note_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return note_metadata(note_path)


def create_note(title: str, content: str) -> dict[str, str]:
    """Create a Markdown note and return its metadata."""
    ensure_storage()
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("Title cannot be empty.")

    NOTES_PATH.mkdir(parents=True, exist_ok=True)

    filename = slugify(normalized_title) + ".md"
    note_path = NOTES_PATH / filename

    if note_path.exists():
        raise FileExistsError(f"Note already exists: {filename}")

    note_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    return note_metadata(note_path)


def view_note(identifier: str) -> dict[str, str]:
    """Return a saved note's metadata and Markdown content."""
    ensure_storage()
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Note not found: {identifier}")

    return note_metadata(note_path) | {"content": note_path.read_text(encoding="utf-8")}


def archive_note(identifier: str) -> dict[str, str]:
    """Move an active note to the archive."""
    ensure_storage()
    note_path = require_note(identifier)
    ARCHIVE_PATH.mkdir(parents=True, exist_ok=True)
    archived_path = unique_target_path(ARCHIVE_PATH / note_path.name)
    shutil.move(str(note_path), str(archived_path))
    return note_metadata(archived_path)


def list_archived_notes() -> list[dict[str, str | int]]:
    """Return ordered display metadata for all archived notes."""
    ensure_storage()
    return [
        {"number": index} | note_metadata(file)
        for index, file in enumerate(archived_note_files(), start=1)
    ]


def restore_note(identifier: str) -> dict[str, str]:
    """Move an archived note back to the active note directory."""
    ensure_storage()
    archived_path = require_archived_note(identifier)
    NOTES_PATH.mkdir(parents=True, exist_ok=True)
    restored_path = unique_target_path(NOTES_PATH / archived_path.name)
    shutil.move(str(archived_path), str(restored_path))
    return note_metadata(restored_path)


def find_note(identifier: str) -> Path | None:
    """Find a note by list number, title, filename, filename stem, or slug."""
    return find_note_in_files(identifier, note_files())


def find_archived_note(identifier: str) -> Path | None:
    """Find an archived note by list number, title, filename, stem, or slug."""
    return find_note_in_files(identifier, archived_note_files())


def find_note_in_files(identifier: str, files: list[Path]) -> Path | None:
    """Find a note in a specific file list."""
    normalized_identifier = identifier.strip().lower()

    if normalized_identifier.isdecimal():
        note_number = int(normalized_identifier)
        if 1 <= note_number <= len(files):
            return files[note_number - 1]
        return None

    slug_identifier = slugify(identifier)

    for file in files:
        title = normalize_file_name(file).lower()
        filename = file.name.lower()
        stem = file.stem.lower()

        if normalized_identifier in {title, filename, stem} or slug_identifier == stem:
            return file

    return None


def require_note(identifier: str) -> Path:
    """Return an active note path or raise a clear error."""
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Note not found: {identifier}")
    return note_path


def require_archived_note(identifier: str) -> Path:
    """Return an archived note path or raise a clear error."""
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_archived_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Archived note not found: {identifier}")
    return note_path


def note_files() -> list[Path]:
    """Return all note files sorted by filename."""
    return visible_files(NOTES_PATH)


def archived_note_files() -> list[Path]:
    """Return all archived note files sorted by filename."""
    return visible_files(ARCHIVE_PATH)


def visible_files(path: Path) -> list[Path]:
    """Return visible files from a directory sorted by filename."""
    if not path.exists():
        return []

    return [
        file
        for file in sorted(path.iterdir())
        if file.is_file() and not file.name.startswith(".")
    ]


def ensure_storage() -> None:
    """Create default storage for direct module use before server startup."""
    if not _STORAGE_INITIALIZED:
        initialize_storage()


def read_previous_storage_paths() -> tuple[Path | None, Path | None]:
    """Read the last active notes and archive paths from internal server state."""
    if not STORAGE_STATE_PATH.exists():
        return None, None

    try:
        state = json.loads(STORAGE_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None

    notes_path = state.get("notes_path")
    if not isinstance(notes_path, str) or not notes_path.strip():
        return None, None

    archive_path = state.get("archive_path")
    if isinstance(archive_path, str) and archive_path.strip():
        resolved_archive_path = Path(archive_path).expanduser().resolve()
    else:
        resolved_archive_path = Path(notes_path).expanduser().resolve().parent / "archive"

    return Path(notes_path).expanduser().resolve(), resolved_archive_path


def write_storage_state(notes_path: Path, archive_path: Path) -> None:
    """Persist the active notes path so future starts can migrate from it."""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_STATE_PATH.write_text(
        json.dumps(
            {
                "notes_path": str(notes_path),
                "archive_path": str(archive_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def migrate_notes(source_path: Path, target_path: Path) -> None:
    """Move existing note files from source to target without overwriting."""
    if not source_path.exists() or source_path == target_path:
        return

    target_path.mkdir(parents=True, exist_ok=True)

    for source_file in sorted(source_path.iterdir()):
        if not source_file.is_file() or source_file.name.startswith("."):
            continue

        target_file = unique_target_path(target_path / source_file.name)
        shutil.move(str(source_file), str(target_file))


def unique_target_path(target_file: Path) -> Path:
    """Return a non-existing path, preserving existing target files."""
    if not target_file.exists():
        return target_file

    index = 2
    while True:
        candidate = target_file.with_name(
            f"{target_file.stem}-{index}{target_file.suffix}"
        )
        if not candidate.exists():
            return candidate
        index += 1


def display_path(file: Path) -> str:
    """Return project-relative paths when possible, otherwise absolute paths."""
    resolved_file = file.resolve()
    resolved_project_root = PROJECT_ROOT.resolve()
    if resolved_file.is_relative_to(resolved_project_root):
        return str(resolved_file.relative_to(resolved_project_root))
    return str(resolved_file)


def note_metadata(file: Path) -> dict[str, str]:
    """Return common metadata for a note file."""
    return {
        "title": normalize_file_name(file),
        "filename": file.name,
        "path": display_path(file),
    }


def modified_metadata(file: Path) -> dict[str, float | str]:
    """Return filesystem modification time metadata for a note file."""
    modified_timestamp = file.stat().st_mtime
    return {
        "modified": datetime.fromtimestamp(modified_timestamp, UTC).isoformat(),
        "modified_timestamp": modified_timestamp,
    }


def normalize_search_query(query: str) -> dict[str, str | list[str]]:
    """Normalize a search query into its phrase and unique terms."""
    phrase = " ".join(query.strip().lower().split())
    if not phrase:
        return {}

    terms = []
    for term in phrase.split():
        if term not in terms:
            terms.append(term)

    return {"phrase": phrase, "terms": terms}


def search_score(
    title: str,
    content: str,
    search_query: dict[str, str | list[str]],
) -> int:
    """Score a note for a normalized search query."""
    phrase = str(search_query["phrase"])
    terms = list(search_query["terms"])
    normalized_title = title.lower()
    normalized_content = content.lower()
    score = 0

    if phrase in normalized_title:
        score += 100
    if phrase in normalized_content:
        score += 30

    for term in terms:
        if term in normalized_title:
            score += 20
        if term in normalized_content:
            score += 5

    return score


def extract_search_excerpt(
    content: str,
    search_query: dict[str, str | list[str]],
    radius: int = 80,
) -> str:
    """Return a short excerpt around the best content match."""
    phrase = str(search_query["phrase"])
    terms = list(search_query["terms"])
    normalized_content = content.lower()
    best_match = phrase if phrase in normalized_content else ""

    if not best_match:
        for term in terms:
            if term in normalized_content:
                best_match = term
                break

    if not best_match:
        return content.strip().splitlines()[0] if content.strip() else ""

    return extract_excerpt(content, best_match, radius)


def normalize_file_name(file: Path) -> str:
    """Convert a note filename into a human-readable display title."""
    return file.stem.replace("-", " ").capitalize()


def slugify(title: str) -> str:
    """Convert a title into a safe lowercase Markdown filename stem."""
    slug_parts = []
    previous_was_separator = False

    for character in title.strip().lower():
        if character.isalnum():
            slug_parts.append(character)
            previous_was_separator = False
        elif not previous_was_separator:
            slug_parts.append("-")
            previous_was_separator = True

    slug = "".join(slug_parts).strip("-")

    if not slug:
        raise ValueError("Title must contain at least one letter or number.")

    return slug


def extract_excerpt(content: str, query: str, radius: int = 80) -> str:
    """Return a short content excerpt around the first query match."""
    normalized_content = content.lower()
    match_index = normalized_content.find(query)

    if match_index == -1:
        return content.strip().splitlines()[0] if content.strip() else ""

    start = max(match_index - radius, 0)
    end = min(match_index + len(query) + radius, len(content))
    excerpt = content[start:end].strip()

    if start > 0:
        excerpt = "..." + excerpt
    if end < len(content):
        excerpt += "..."

    return excerpt
