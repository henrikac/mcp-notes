from mcp.server.fastmcp import FastMCP

from notes import append_to_note as append_to_note_file
from notes import archive_note as archive_note_file
from notes import backlinks as note_backlinks
from notes import create_note as create_note_file
from notes import find_related_notes as related_note_files
from notes import fetch_notes
from notes import initialize_storage
from notes import list_archived_notes as list_archived_note_files
from notes import list_tags as list_note_tags
from notes import recent_notes as recent_note_files
from notes import restore_note as restore_note_file
from notes import search_notes as search_note_files
from notes import update_note as update_note_file
from notes import view_note as view_note_file


mcp = FastMCP("knowledge-assistant")


@mcp.tool()
def list_notes(tag: str | None = None) -> list[dict[str, str | int | list[str] | dict]]:
    """Gets an ordered list of saved notes."""
    return fetch_notes(tag)


@mcp.tool()
def list_tags() -> list[dict[str, str | int]]:
    """Gets normalized tags with active note counts."""
    return list_note_tags()


@mcp.tool()
def search_notes(query: str) -> list[dict[str, str | int]]:
    """Search saved notes by title and content."""
    return search_note_files(query)


@mcp.tool()
def recent_notes(limit: int = 10) -> list[dict[str, str | int | float]]:
    """Gets active notes ordered by most recent modification time."""
    return recent_note_files(limit)


@mcp.tool()
def backlinks(identifier: str) -> list[dict[str, str | list[str] | dict]]:
    """Find active notes that link to a note with wiki-links."""
    return note_backlinks(identifier)


@mcp.tool()
def find_related_notes(
    identifier: str,
    limit: int = 5,
) -> list[dict[str, str | int | float | list[str] | dict]]:
    """Find active notes that are likely related to a note."""
    return related_note_files(identifier, limit)


@mcp.tool()
def append_to_note(
    identifier: str,
    content: str,
    heading: str | None = None,
) -> dict[str, str]:
    """Append Markdown content to an existing note."""
    return append_to_note_file(identifier, content, heading)


@mcp.tool()
def update_note(identifier: str, content: str) -> dict[str, str]:
    """Replace the full Markdown content of an existing note."""
    return update_note_file(identifier, content)


@mcp.tool()
def create_note(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> dict[str, str | list[str] | dict]:
    """Create a new Markdown note from a title and content."""
    return create_note_file(title, content, tags)


@mcp.tool()
def view_note(identifier: str) -> dict[str, str | list[str] | dict]:
    """View a saved note by list number, title, filename, filename stem, or slug."""
    return view_note_file(identifier)


@mcp.tool()
def archive_note(identifier: str) -> dict[str, str]:
    """Move an active note to the archive."""
    return archive_note_file(identifier)


@mcp.tool()
def list_archived_notes() -> list[dict[str, str | int]]:
    """Gets an ordered list of archived notes."""
    return list_archived_note_files()


@mcp.tool()
def restore_note(identifier: str) -> dict[str, str]:
    """Move an archived note back to the active note directory."""
    return restore_note_file(identifier)


def main():
    initialize_storage()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
