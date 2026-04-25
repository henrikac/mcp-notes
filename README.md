# Knowledge Assistant

Knowledge Assistant is a small MCP server for working with local Markdown
notes. It lets MCP clients such as Codex, Claude, and Gemini list notes, view
individual notes, search through note titles and contents, and create new notes.

## Storage

By default, notes are stored as Markdown files in:

```text
data/notes
```

The server creates this directory and `data/archive` on startup when no custom
location is configured. Runtime note data is stored outside git, including the
default `data/notes` and `data/archive` directories and the local
`data/storage.json` state file.

To store notes somewhere else, set `KNOWLEDGE_ASSISTANT_NOTES_PATH` before
starting the server:

```bash
KNOWLEDGE_ASSISTANT_NOTES_PATH="$HOME/Notes/knowledge-assistant" uv run python src/server.py
```

When a custom notes directory is configured, the archive directory is created
next to it.

When the configured location changes later, the server moves existing note files
from the previous location to the new one during startup. Existing files in the
new location are not overwritten; moved files with duplicate names receive a
numeric suffix.

## Tools

The server exposes these MCP tools:

| Tool | Description |
| --- | --- |
| `list_notes()` | Returns an ordered list of all saved notes. |
| `view_note(identifier)` | Returns one saved note's Markdown content. |
| `search_notes(query)` | Searches note titles and contents. |
| `create_note(title, content)` | Creates a new Markdown note. |
| `append_to_note(identifier, content, heading)` | Appends Markdown content to an existing note. |
| `update_note(identifier, content)` | Replaces an existing note's Markdown content. |
| `archive_note(identifier)` | Moves an active note to the archive. |
| `list_archived_notes()` | Returns an ordered list of archived notes. |
| `restore_note(identifier)` | Moves an archived note back to active notes. |

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

`append_to_note` resolves notes the same way as `view_note`. It appends content
to the end of the note and can optionally insert a Markdown heading before the
new content.

`update_note` resolves notes the same way as `view_note` and replaces the full
Markdown body while preserving the existing filename.

Archived notes are excluded from `list_notes` and `search_notes`.
`list_archived_notes` lists archived notes, and `restore_note` moves an archived
note back to the active note directory. Archive and restore operations preserve
existing files by adding a numeric suffix when a filename already exists.

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

For a custom notes directory, add the environment variable to your MCP client
configuration:

```text
env:
  KNOWLEDGE_ASSISTANT_NOTES_PATH: /path/to/notes
```

Remove the server later with:

```bash
codex mcp remove knowledge-assistant
```

## Project Structure

```text
src/server.py MCP server and tool definitions
src/notes.py  Note storage, search, and creation logic
```
