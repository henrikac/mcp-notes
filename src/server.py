from mcp.server.fastmcp import FastMCP

from notes import create_note as create_note_file
from notes import fetch_notes
from notes import search_notes as search_note_files
from notes import view_note as view_note_file


mcp = FastMCP("knowledge-assistant")


@mcp.tool()
def list_notes() -> list[dict[str, str | int]]:
    """Gets an ordered list of saved notes."""
    return fetch_notes()


@mcp.tool()
def search_notes(query: str) -> list[dict[str, str]]:
    """Search saved notes by title and content."""
    return search_note_files(query)


@mcp.tool()
def create_note(title: str, content: str) -> dict[str, str]:
    """Create a new Markdown note from a title and content."""
    return create_note_file(title, content)


@mcp.tool()
def view_note(identifier: str) -> dict[str, str]:
    """View a saved note by list number, title, filename, filename stem, or slug."""
    return view_note_file(identifier)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
