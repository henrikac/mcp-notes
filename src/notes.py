import json
import os
import re
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
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "det",
    "der",
    "en",
    "er",
    "for",
    "fra",
    "i",
    "in",
    "is",
    "it",
    "med",
    "of",
    "og",
    "on",
    "or",
    "på",
    "som",
    "the",
    "til",
    "to",
    "with",
}
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]")


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


def fetch_notes(tag: str | None = None) -> list[dict[str, str | int | list[str] | dict]]:
    """Return ordered display metadata for all saved notes."""
    ensure_storage()
    normalized_tag = normalize_tag(tag) if tag else None
    files = [
        file
        for file in note_files()
        if normalized_tag is None or normalized_tag in note_tags(file)
    ]

    return [
        {"number": index} | note_metadata(file)
        for index, file in enumerate(files, start=1)
    ]


def search_notes(query: str) -> list[dict[str, str | int]]:
    """Search note titles and contents with ranked results."""
    ensure_storage()
    search_query = normalize_search_query(query)
    if not search_query:
        return []

    results = []
    for file in note_files():
        document = read_note_document(file)
        title = note_title(file, document["metadata"])
        body = str(document["body"])
        score = search_score(title, body, search_query)

        if score > 0:
            results.append(
                note_metadata_from_metadata(file, document["metadata"])
                | {
                    "score": score,
                    "excerpt": extract_search_excerpt(body, search_query),
                }
            )

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
    document = read_note_document(note_path)
    existing_content = str(document["body"]).rstrip("\n")
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

    metadata = dict(document["metadata"])
    if metadata:
        metadata["updated"] = current_date()

    write_note_document(note_path, metadata, new_content)
    return note_metadata(note_path)


def update_note(identifier: str, content: str) -> dict[str, str]:
    """Replace the full Markdown content of an existing note."""
    ensure_storage()
    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("Content cannot be empty.")

    note_path = require_note(identifier)
    document = read_note_document(note_path)
    metadata = dict(document["metadata"])
    if metadata:
        metadata["updated"] = current_date()

    write_note_document(note_path, metadata, content.rstrip() + "\n")
    return note_metadata(note_path)


def create_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> dict[str, str | list[str] | dict]:
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

    normalized_tags = normalize_tags(tags or [])
    metadata = {}
    if normalized_tags:
        today = current_date()
        metadata = {
            "title": normalized_title,
            "created": today,
            "updated": today,
            "tags": normalized_tags,
        }

    write_note_document(note_path, metadata, content.rstrip() + "\n")

    return note_metadata(note_path)


def view_note(identifier: str) -> dict[str, str | list[str] | dict]:
    """Return a saved note's metadata and Markdown content."""
    ensure_storage()
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Note not found: {identifier}")

    document = read_note_document(note_path)
    return note_metadata_from_metadata(note_path, document["metadata"]) | {
        "content": document["raw"],
        "body": document["body"],
    }


def list_tags() -> list[dict[str, str | int]]:
    """Return normalized tags with active note counts."""
    ensure_storage()
    tag_counts: dict[str, int] = {}

    for file in note_files():
        for tag in note_tags(file):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(tag_counts.items())
    ]


def backlinks(identifier: str) -> list[dict[str, str | list[str] | dict]]:
    """Return active notes that link to the target note with wiki-links."""
    ensure_storage()
    target_path = require_note(identifier)
    results = []

    for file in note_files():
        if file == target_path:
            continue

        document = read_note_document(file)
        body = str(document["body"])
        matching_link = first_link_to_target(body, target_path)
        if matching_link is None:
            continue

        results.append(
            note_metadata_from_metadata(file, document["metadata"])
            | {"excerpt": extract_excerpt(body, matching_link.lower())}
        )

    return results


def find_related_notes(
    identifier: str,
    limit: int = 5,
) -> list[dict[str, str | int | float | list[str] | dict]]:
    """Return active notes that are likely related to the source note."""
    ensure_storage()
    source_path = require_note(identifier)
    source_document = read_note_document(source_path)
    source_body = str(source_document["body"])
    source_metadata = source_document["metadata"]
    source_terms = related_terms(source_path, source_metadata, source_body)
    source_tags = set(note_tags(source_path))
    source_outgoing_paths = linked_note_paths(source_body)
    clamped_limit = max(0, min(limit, 100))
    related = []

    for file in note_files():
        if file == source_path:
            continue

        document = read_note_document(file)
        body = str(document["body"])
        metadata = document["metadata"]
        candidate_terms = related_terms(file, metadata, body)
        shared_terms = source_terms & candidate_terms
        shared_tags = source_tags & set(note_tags(file))
        candidate_outgoing_paths = linked_note_paths(body)
        has_link_relationship = (
            file in source_outgoing_paths or source_path in candidate_outgoing_paths
        )

        score = float(len(shared_terms))
        score += len(shared_tags) * 10
        if has_link_relationship:
            score += 25

        if score <= 0:
            continue

        related.append(
            note_metadata_from_metadata(file, metadata)
            | {
                "score": score,
                "reason": related_reason(shared_terms, shared_tags, has_link_relationship),
            }
        )

    return sorted(
        related,
        key=lambda result: (-float(result["score"]), str(result["title"])),
    )[:clamped_limit]


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
        metadata = read_note_document(file)["metadata"]
        title = note_title(file, metadata).lower()
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
    metadata = read_note_document(file)["metadata"]
    return note_metadata_from_metadata(file, metadata)


def note_metadata_from_metadata(
    file: Path,
    metadata: dict[str, str | list[str]],
) -> dict[str, str | list[str] | dict]:
    """Return common metadata for a note file and parsed frontmatter."""
    result = {
        "title": note_title(file, metadata),
        "filename": file.name,
        "path": display_path(file),
    }

    if metadata:
        result["metadata"] = metadata

    tags = metadata.get("tags")
    if isinstance(tags, list):
        result["tags"] = tags

    return result


def note_title(file: Path, metadata: dict[str, str | list[str]]) -> str:
    """Return the frontmatter title when available, otherwise filename title."""
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title
    return normalize_file_name(file)


def note_tags(file: Path) -> list[str]:
    """Return normalized tags for a note file."""
    metadata = read_note_document(file)["metadata"]
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return []
    return tags


def read_note_document(file: Path) -> dict[str, str | dict[str, str | list[str]]]:
    """Read a note and parse optional YAML-style frontmatter."""
    raw_content = file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw_content, file.name)
    return {
        "raw": raw_content,
        "metadata": metadata,
        "body": body,
    }


def write_note_document(
    file: Path,
    metadata: dict[str, str | list[str]],
    body: str,
) -> None:
    """Write note body with optional frontmatter metadata."""
    normalized_body = body.rstrip() + "\n"
    if metadata:
        file.write_text(
            serialize_frontmatter(metadata) + "\n" + normalized_body,
            encoding="utf-8",
        )
        return

    file.write_text(normalized_body, encoding="utf-8")


def parse_frontmatter(
    content: str,
    filename: str,
) -> tuple[dict[str, str | list[str]], str]:
    """Parse simple YAML-style frontmatter from a Markdown document."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, content

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        raise ValueError(f"Malformed frontmatter in {filename}: missing closing ---")

    metadata_lines = lines[1:closing_index]
    body = "".join(lines[closing_index + 1 :])
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return parse_metadata_lines(metadata_lines, filename), body


def parse_metadata_lines(
    lines: list[str],
    filename: str,
) -> dict[str, str | list[str]]:
    """Parse a conservative subset of YAML frontmatter."""
    metadata: dict[str, str | list[str]] = {}

    for line_number, line in enumerate(lines, start=2):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if ":" not in stripped_line:
            raise ValueError(
                f"Malformed frontmatter in {filename}: line {line_number}"
            )

        key, value = stripped_line.split(":", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError(
                f"Malformed frontmatter in {filename}: line {line_number}"
            )

        metadata[normalized_key] = parse_metadata_value(normalized_key, value.strip())

    tags = metadata.get("tags")
    if isinstance(tags, list):
        metadata["tags"] = normalize_tags(tags)

    return metadata


def parse_metadata_value(key: str, value: str) -> str | list[str]:
    """Parse a simple frontmatter scalar or inline list value."""
    if key == "tags":
        return parse_tags_value(value)
    return value.strip("\"'")


def parse_tags_value(value: str) -> list[str]:
    """Parse tags from an inline YAML-style list or comma-separated string."""
    if not value:
        return []

    normalized_value = value.strip()
    if normalized_value.startswith("["):
        if not normalized_value.endswith("]"):
            raise ValueError("Malformed frontmatter tags: missing closing ]")
        normalized_value = normalized_value[1:-1]

    return [
        item.strip().strip("\"'")
        for item in normalized_value.split(",")
        if item.strip().strip("\"'")
    ]


def serialize_frontmatter(metadata: dict[str, str | list[str]]) -> str:
    """Serialize simple metadata as YAML-style frontmatter."""
    lines = ["---"]
    preferred_keys = ["title", "created", "updated", "tags"]
    ordered_keys = preferred_keys + [
        key for key in sorted(metadata) if key not in preferred_keys
    ]

    for key in ordered_keys:
        if key not in metadata:
            continue

        value = metadata[key]
        if isinstance(value, list):
            serialized_value = "[" + ", ".join(value) + "]"
        else:
            serialized_value = str(value)
        lines.append(f"{key}: {serialized_value}")

    lines.append("---")
    return "\n".join(lines) + "\n"


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalize, deduplicate, and sort tag values."""
    normalized_tags = []
    for tag in tags:
        normalized_tag = normalize_tag(tag)
        if normalized_tag and normalized_tag not in normalized_tags:
            normalized_tags.append(normalized_tag)
    return sorted(normalized_tags)


def normalize_tag(tag: str) -> str:
    """Convert a tag into a lowercase slug-like value."""
    try:
        return slugify(tag)
    except ValueError:
        return ""


def current_date() -> str:
    """Return the current UTC date for note metadata."""
    return datetime.now(UTC).date().isoformat()


def extract_wiki_links(content: str) -> list[str]:
    """Return wiki-link labels from Markdown content."""
    return [
        match.group(1).strip()
        for match in WIKI_LINK_PATTERN.finditer(content)
        if match.group(1).strip()
    ]


def first_link_to_target(content: str, target_path: Path) -> str | None:
    """Return the first wiki-link label that resolves to a target note."""
    for link_text in extract_wiki_links(content):
        linked_path = find_note_from_link(link_text)
        if linked_path == target_path:
            return link_text
    return None


def linked_note_paths(content: str) -> set[Path]:
    """Return active notes resolved from wiki-links in Markdown content."""
    paths = set()
    for link_text in extract_wiki_links(content):
        linked_path = find_note_from_link(link_text)
        if linked_path is not None:
            paths.add(linked_path)
    return paths


def find_note_from_link(link_text: str) -> Path | None:
    """Resolve a wiki-link label without failing on invalid labels."""
    try:
        return find_note(link_text)
    except ValueError:
        return None


def related_terms(
    file: Path,
    metadata: dict[str, str | list[str]],
    body: str,
) -> set[str]:
    """Return normalized non-stopword terms for related-note matching."""
    text = f"{note_title(file, metadata)} {body}"
    return {
        term
        for term in re.findall(r"[\w]+", text.lower())
        if len(term) > 2 and term not in STOP_WORDS
    }


def related_reason(
    shared_terms: set[str],
    shared_tags: set[str],
    has_link_relationship: bool,
) -> str:
    """Return a short deterministic explanation for a related-note score."""
    reasons = []
    if shared_tags:
        reasons.append("shared tags: " + ", ".join(sorted(shared_tags)[:3]))
    if has_link_relationship:
        reasons.append("wiki-link relationship")
    if shared_terms:
        reasons.append("shared terms: " + ", ".join(sorted(shared_terms)[:3]))
    return "; ".join(reasons)


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
