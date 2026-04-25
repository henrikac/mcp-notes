import json
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data"
DEFAULT_NOTES_PATH = DATA_PATH / "notes"
NOTES_PATH_ENV_VAR = "KNOWLEDGE_ASSISTANT_NOTES_PATH"
STORAGE_STATE_PATH = DATA_PATH / "storage.json"
NOTES_PATH = DEFAULT_NOTES_PATH
_STORAGE_INITIALIZED = False


def initialize_storage() -> Path:
    """Initialize note storage and migrate notes if the configured path changed."""
    global NOTES_PATH, _STORAGE_INITIALIZED

    configured_path = os.environ.get(NOTES_PATH_ENV_VAR, "").strip()
    desired_path = (
        Path(configured_path).expanduser()
        if configured_path
        else DEFAULT_NOTES_PATH
    ).resolve()

    previous_path = read_previous_notes_path()
    migration_source = previous_path if previous_path != desired_path else None

    if migration_source is None and configured_path and DEFAULT_NOTES_PATH != desired_path:
        migration_source = DEFAULT_NOTES_PATH

    desired_path.mkdir(parents=True, exist_ok=True)

    if migration_source is not None:
        migrate_notes(migration_source, desired_path)

    write_storage_state(desired_path)
    NOTES_PATH = desired_path
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


def search_notes(query: str) -> list[dict[str, str]]:
    """Search note titles and contents for a case-insensitive query."""
    ensure_storage()
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    results = []
    for file in note_files():
        content = file.read_text(encoding="utf-8")
        title = normalize_file_name(file)

        if normalized_query in title.lower() or normalized_query in content.lower():
            results.append({
                "title": title,
                "filename": file.name,
                "path": display_path(file),
                "excerpt": extract_excerpt(content, normalized_query),
            })

    return results


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

    return {
        "title": normalize_file_name(note_path),
        "filename": filename,
        "path": display_path(note_path),
    }


def view_note(identifier: str) -> dict[str, str]:
    """Return a saved note's metadata and Markdown content."""
    ensure_storage()
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Note not found: {identifier}")

    return {
        "title": normalize_file_name(note_path),
        "filename": note_path.name,
        "path": display_path(note_path),
        "content": note_path.read_text(encoding="utf-8"),
    }


def find_note(identifier: str) -> Path | None:
    """Find a note by list number, title, filename, filename stem, or slug."""
    normalized_identifier = identifier.strip().lower()
    files = note_files()

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


def note_files() -> list[Path]:
    """Return all note files sorted by filename."""
    if not NOTES_PATH.exists():
        return []

    return [
        file
        for file in sorted(NOTES_PATH.iterdir())
        if file.is_file() and not file.name.startswith(".")
    ]


def ensure_storage() -> None:
    """Create default storage for direct module use before server startup."""
    if not _STORAGE_INITIALIZED:
        initialize_storage()


def read_previous_notes_path() -> Path | None:
    """Read the last active notes path from internal server state."""
    if not STORAGE_STATE_PATH.exists():
        return None

    try:
        state = json.loads(STORAGE_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    notes_path = state.get("notes_path")
    if not isinstance(notes_path, str) or not notes_path.strip():
        return None

    return Path(notes_path).expanduser().resolve()


def write_storage_state(notes_path: Path) -> None:
    """Persist the active notes path so future starts can migrate from it."""
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_STATE_PATH.write_text(
        json.dumps({"notes_path": str(notes_path)}, indent=2) + "\n",
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
    if resolved_file.is_relative_to(PROJECT_ROOT):
        return str(resolved_file.relative_to(PROJECT_ROOT))
    return str(resolved_file)


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
