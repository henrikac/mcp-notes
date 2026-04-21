# Knowledge Assistant

Knowledge Assistant is a small MCP server for working with local Markdown
notes. It lets MCP clients such as Codex, Claude, and Gemini list notes, view
individual notes, search through note titles and contents, and create new notes.

Notes are stored as Markdown files in:

```text
data/notes
```

## Tools

The server exposes these MCP tools:

| Tool | Description |
| --- | --- |
| `list_notes()` | Returns an ordered list of all saved notes. |
| `view_note(identifier)` | Returns one saved note's Markdown content. |
| `search_notes(query)` | Searches note titles and contents. |
| `create_note(title, content)` | Creates a new Markdown note. |

`list_notes` returns structured data with the ordered number, note title,
filename, and relative path.

`view_note` accepts the note number from `list_notes`, a note title, filename,
filename stem, or slug and returns the note title, filename, relative path, and
Markdown content.

`search_notes` returns structured data with the note title, filename, relative
path, and a short excerpt.

`create_note` converts the title into a lowercase kebab-case filename. For
example:

```text
My New Note -> my-new-note.md
Sådan tilføjer man et MCP tool -> sådan-tilføjer-man-et-mcp-tool.md
```

Existing notes are not overwritten.

## Requirements

- Python 3.14 or newer
- `uv`

Install dependencies:

```bash
uv sync
```

## Run Locally

Start the MCP server over stdio:

```bash
uv run python src/server.py
```

## Add to Codex CLI

Register the server with Codex CLI:

```bash
codex mcp add knowledge-assistant -- /path/to/knowledge-assistant/.venv/bin/python /path/to/knowledge-assistant/src/server.py
```

Verify the registration:

```bash
codex mcp get knowledge-assistant
```

The expected configuration should look like this:

```text
command: /path/to/knowledge-assistant/.venv/bin/python
args: /path/to/knowledge-assistant/src/server.py
```

Remove the server later with:

```bash
codex mcp remove knowledge-assistant
```

## Project Structure

```text
src/server.py   MCP server and tool definitions
src/notes.py    Note storage, search, and creation logic
data/notes      Markdown note files
```
