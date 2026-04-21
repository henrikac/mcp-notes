from pathlib import Path


NOTES_PATH = Path(__file__).resolve().parent.parent / "data" / "notes"


def fetch_notes() -> list[dict[str, str | int]]:
    """Return ordered display metadata for all saved notes."""
    return [
        {
            "number": index,
            "title": normalize_file_name(file),
            "filename": file.name,
            "path": str(file.relative_to(NOTES_PATH.parent.parent)),
        }
        for index, file in enumerate(note_files(), start=1)
    ]


def search_notes(query: str) -> list[dict[str, str]]:
    """Search note titles and contents for a case-insensitive query."""
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
                "path": str(file.relative_to(NOTES_PATH.parent.parent)),
                "excerpt": extract_excerpt(content, normalized_query),
            })

    return results


def create_note(title: str, content: str) -> dict[str, str]:
    """Create a Markdown note and return its metadata."""
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
        "path": str(note_path.relative_to(NOTES_PATH.parent.parent)),
    }


def view_note(identifier: str) -> dict[str, str]:
    """Return a saved note's metadata and Markdown content."""
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Note identifier cannot be empty.")

    note_path = find_note(normalized_identifier)
    if note_path is None:
        raise FileNotFoundError(f"Note not found: {identifier}")

    return {
        "title": normalize_file_name(note_path),
        "filename": note_path.name,
        "path": str(note_path.relative_to(NOTES_PATH.parent.parent)),
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
