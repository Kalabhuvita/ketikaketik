# Ketikaketik

A markdown editor for writing novel. Linux, PySide6 (Qt 6), one folder per project.

Untuk anak-anak bulu: Keanu, Lemon, Sabrina, Boba, Mia, Goomba, Koopa, Ultra, Jaja,
Atom, Hawai, dan Puri

```bash
./run.sh                       # launch
./run.sh ~/Novel/my-novel      # open a project folder directly
```

## Requirements

- Linux, Python **3.9+** (the source parses under 3.9 grammar; no newer syntax)
- PySide6 / Qt 6
  - Arch: `sudo pacman -S pyside6`
  - Fedora: `sudo dnf install python3-pyside6`
  - Ubuntu: `sudo apt install python3-pyside6.qtwidgets`, or a venv with `pip install PySide6`
- `pandoc` — only needed for `.docx` export
- `run.sh` resolves the interpreter itself: local `.venv`, then `/usr/bin/python3`, then `python3`

Tested on CachyOS/Arch with Python 3.14 and PySide6 6.12. No distro-specific code paths.

## Two distros, one source tree (dual boot)

The code can live on a shared partition. The *interpreter* cannot be shared: Arch ships
Python 3.14 while Mint ships 3.12 (or 3.10), and a virtualenv is tied to one interpreter.

- `run.sh` looks for, in order: `.venv-<distro id>`, `.venv`, `venv`, `/usr/bin/python3`,
  `python3`. So `.venv-cachyos` and `.venv-linuxmint` can coexist next to the app and each
  distro picks its own. Create the venv **on the distro that will use it**.
- Settings (theme, recent projects, hidden chapters) are per-user by default, so each
  distro would start with its own. To share them: create an empty file `settings.ini` next
  to `main.py` (or export `KETIKAKETIK_CONFIG=/path/to/dir`). Settings then live in
  `.config/` beside the app instead of `~/.config`.

CachyOS + COSMIC is Wayland, Mint Cinnamon is X11; both work — the Qt Wayland plugin is
present and X11 uses `libqxcb`. If a Wayland session misbehaves, force XWayland with
`QT_QPA_PLATFORM=xcb`.

## Features

**Projects & files**
- One folder = one novel. Every `.md` in the folder root is a chapter, ordered by file name.
  Subfolders (`.history/`, `notes/`, `research/`, anything) are ignored entirely.
- Sidebar chapter list; create / rename / delete a chapter (moved to `.history/deleted/`,
  never erased).
- **Remove from Project (keep file)** — File menu, or right-click a chapter. The file stays
  exactly where it is; it just stops appearing in the chapter list and the outline. Bring it
  back with `File → Hidden Chapters…`, which lists everything currently hidden.
- Recent projects (last 10); the most recent one opens automatically on launch.
  `File → Recent Projects → Manage Recent Projects…` removes entries from the list without
  touching any file on disk.
- Session restore: last file and cursor position.

**Two ways to work**

- **Open Project Folder…** (`Ctrl+Shift+O`) — a folder of `.md` novels, listed in the Chapters panel.
  Press `F5` (or just switch back to the window) to rescan, so files copied into the folder appear
  immediately without restarting. If the folder itself was renamed or moved outside the app, the
  status bar says so instead of silently showing an empty list.
- **Open File…** (`Ctrl+O`) — the classic single-file mode: no Chapters panel, the outline shows only
  that file, and the window title is the file name. Everything else works the same (atomic saving,
  recovery journal, history, repetition). Recent Files keeps the last twelve.

**Repetition analysis (for Indonesian prose)**

Indonesian has far fewer content words to spare than English, so repetition is the most common
flaw in Indonesian fiction — and no English writing tool handles it. `Ctrl+Shift+R` opens a
separate analysis window; **nothing is added to the writing screen**.

- **Frequent words** — counts for the open novel or just the section you are in, with density per
  1000 words. **Nothing is filtered out by default**: function words, particles, clichés and
  fiction habits all appear, and every row says what kind of word it is.
- **Close repetitions** — words that come back within a few sentences (default 3), sorted by
  *count × density* so long tight chains come first.
- **Repeated phrases** — phrases of 2 to N words (default 5) that occur at least twice, never
  crossing a sentence boundary. Nested phrases are dropped: if "ia menghela napas panjang" is
  reported, "menghela napas" is not. Longest phrases come first, because two-word function-word
  collocations ("aku tidak", "di dalam") would otherwise fill the list; click a column header to
  re-sort.
- **Clichés** — formulaic phrases ("pada saat itu", "hal ini") flagged as one unit.
- **Scope: Whole novel ↔ This section.** One `.md` file is one novel; a section runs from the
  heading your cursor is in to the next heading of the same or higher level. In *This section*
  mode the analysis **re-runs by itself when the cursor moves into another heading** (400 ms
  debounce, no Refresh needed), the status line names the section, and a one-line hint under the
  controls explains the rule. A section with almost no text says so instead of quietly showing zero.
- **Ignore per item** — right-click a word or phrase to ignore it; it stays visible but struck out
  and dimmed, and disappears from every list once *Hide them in the lists* is on. The ignore list
  is remembered across projects, and *Ignored…* restores entries one by one.
- Click any finding to jump to that line; the analysis window stays open.
- The window remembers size, position and settings, can be pinned on top, and narrows to ~380 px.
- Results refresh 1.5 s after you stop typing, only while the window is open. A full 86k-word novel
  takes ~0.4 s for words and ~0.9 s for phrases.
- Word and sentence totals come from the same counter as the status bar, so the two windows can
  never disagree; only the scope differs, and the label says which.
- `-nya`, `-ku`, `-mu` are treated as enclitics; `di` as a preposition is not confused with the
  `di-` prefix.

**File safety**

Saving is built so that a crash, a full disk, or a power cut cannot corrupt a chapter.

- Writes go to a temporary file in the same folder, are `fsync`-ed, then published with
  `os.replace` (atomic). The directory is `fsync`-ed too, so the rename survives a power cut.
- The temporary file is read back **before** publishing, and the published file is verified
  again afterwards (identity check + byte comparison).
- File mode, symlinks, UTF-8 BOM and CRLF line endings are preserved.
- A file that is not valid UTF-8 is opened **read-only** — the app refuses to write it rather
  than destroy its bytes.
- A recovery journal (`.recovery/`) is written every 8 seconds while there are unsaved
  changes; if the app dies, the next time you open that chapter it offers to restore it.
- The previous version is copied to `.history/` on **every** save that changes something.
- If saving fails, you are told and nothing is silently lost; switching chapters or quitting
  is cancelled instead of discarding your text.
- A project lock (`.history/ketikaketik.lock`) stops two windows from overwriting each other,
  and autosave pauses when the file changed on disk.

**Editor**
- **Enter behaves like Obsidian**: one Enter is a tight line break, a blank line is a new
  paragraph with visible spacing, and three Enters do not add an empty paragraph. Qt's own
  markdown renderer cannot tell those apart (it turns every newline into a paragraph and
  collapses extras), so the preview layout is post-processed: lines belonging to one
  paragraph are re-joined with a line separator, and only the first block of each paragraph
  gets a top margin. The `.md` file stays clean; export applies the same rule, so preview
  and `.docx` agree.
- Two modes: **Raw** (markers visible, plain) and **Formatted source** (bold / italic /
  headings rendered, `**`, `#` and backticks dimmed but still editable).
- Undo/redo, cut/copy/paste, save, save as.
- **Reflow Paragraphs** (`Ctrl+Shift+J`): joins lines that were hard-wrapped in the middle of
  a paragraph, without touching headings, lists, quotes, tables or code fences. A file
  wrapped at 78 columns otherwise looks like text that stops before the right edge,
  especially once the editor pane is narrowed by split view.
- Quit confirmation: **Save / Discard / Cancel** when there are unsaved changes,
  **Quit / Cancel** when everything is already on disk. It is drawn *inside* the
  window (dimmed backdrop, card centred on the app), because desktop environments —
  Wayland in particular — are free to ignore an application's requested dialog position.
- **External changes are detected.** If the `.md` was changed by another program since you
  opened it, autosave pauses instead of overwriting it, and Save asks whether to overwrite
  or to load the version from disk. The other version is always kept in `.history/`.
- Autosave with a selectable interval: **every 3, 5, or 10 minutes** (View → Autosave).
  Writes are atomic (temp file then `os.replace`), so a crash or power cut never leaves a
  half-written chapter.
- Version history: the previous content is copied to `.history/<chapter-name>/` at most
  once every 10 minutes, up to 40 snapshots per chapter.

**Search**
- **Persistent highlighting**: every match stays lit while you keep typing. Replace one
  occurrence and its highlight disappears, the remaining ones stay lit, and the match
  counter drops with it.
- The active match is orange, the rest are yellow. Typing in the search field keeps
  focus there; the editor scrolls to each match instead of stealing the cursor.
- **Whole word is on by default**, so `yang` does not match `sayang` or `peyang`; toggle it
  with the `ab` button. The `Aa` button switches between case-sensitive and case-insensitive
  matching. Both choices are remembered between sessions, and both apply to highlighting,
  the result counter, navigation, Replace and Replace All.
- Regex mode (`.*`) takes over the pattern, so whole word is disabled while it is active.
- Next/previous, replace, replace all (a single undo step).
- Find & replace across the whole project, with the result list acting as a preview.

**View**
- **Day** (cream) and **Night** (warm dark, not pure black) themes — two complete palettes:
  background, text, cursor, selection, search highlight, sidebar, status bar.
- Font family, size and **line spacing** are chosen from an **in-window panel** that previews
  the change on
  the manuscript as you pick it; **Cancel** restores the previous font, **OK** saves it.
  (The system font dialog was replaced: on PySide6 6.12 it returns its values in the
  opposite order, which silently broke font switching.)
- Maximum line width in `em` (28 / 34 / 40 / 46 / 60, custom, or unlimited).
- The window opens at **70% of the available screen** and is centred on it
  (`View → Reset Window Size` re-applies it). On Wayland the compositor, not the app,
  decides where a top-level window lands, so only the size is guaranteed there.
- The About card is drawn **inside** the window, fades in over ~170 ms and rises ~10 px,
  so it cannot be misplaced by the window manager.
- **Split view**: the left and right pane are each either **editor** or **preview**.
  The divider drags freely (8px handle, 140px minimum per pane) and both the pane ratio
  and the window geometry are remembered between sessions.
  Preview is read-only rendered markdown (true WYSIWYG: `**bold**` shows as bold with no
  markers), refreshed ~450 ms after you stop typing (1,2 s for novels over ~200 000
  characters, so it never renders mid-keystroke). Its scroll position is pinned to the
  **same paragraph**, found by searching the paragraph's own text in the rendered document,
  with paragraph ordinal and character offset as fallbacks. Relative images resolve against
  the project folder.

**Everything else**
- Automatic outline from every heading in every chapter; click to jump.
- Cursor position (`Ln 12, Col 8`) in the status bar.
- Word counter, sentence counter, paragraph count, estimated reading time, and this
  session's word count (delta since the app opened).
- **Markdown issues panel** (`F7`), a dock at the bottom that stays open while you work.
  Single-click an issue and the editor scrolls to that line, puts the cursor on it, and
  flashes the whole line for 2.5 s. The list refreshes as you type. Checks: heading level
  jumps, headings without a title, broken relative links, unbalanced `**`, unbalanced
  backticks, unclosed code fences. It runs when you pause typing, not on every keystroke.
- `File → New Chapter from Sample Text`: drops a ready-made 2,100-word story (about AI, in
  Indonesian) into a **new** chapter of the open project. It contains two deliberate
  markdown flaws — an H2→H4 jump and one unclosed `**` — so the issues panel has something
  to show. Both are explained in the closing note of the story itself.
- `.docx` export through pandoc, in manuscript format: Times New Roman 12pt, double
  spacing, 0.5" first-line indent, page break between chapters.

## Shortcuts

| Action | Keys |
|---|---|
| Find | `Ctrl+F` |
| Find & replace | `Ctrl+H` |
| Next / previous match | `F3` / `Shift+F3` |
| Find in project | `Ctrl+Shift+F` |
| Save / save as | `Ctrl+S` / `Ctrl+Shift+S` |
| New chapter | `Ctrl+N` |
| Open project | `Ctrl+O` |
| Toggle theme | `Ctrl+D` |
| Split view | `Ctrl+\` |
| Export .docx | `Ctrl+E` |
| Check markdown | `F7` |
| Close search | `Esc` |

## Project layout

```
MyNovel/
├── 01-first-chapter.md
├── 02-second-chapter.md
├── notes/                   # ignored
└── .history/                # automatic snapshots, leave it alone
```

Prefix file names with numbers so chapter order is unambiguous. No database and no custom
format — plain `.md` files that open in Obsidian, in git, anywhere.

## Known limitations

- **The two editor panes do not share a document.** Qt does not allow one `QTextDocument`
  to back two `QPlainTextEdit` widgets (the pane renders blank), and in PySide6 6.12
  `setDocument()` is effectively ignored. Text is therefore mirrored with a ~220 ms delay,
  and undo in the pane you are *not* typing in is reset when it catches up. Typing in the
  active pane is unaffected.
- Search highlighting appears in the editor only, not in the preview pane.
- The preview uses Qt's built-in md4c renderer: headings, bold/italic, lists, blockquotes,
  tables, code blocks. No footnotes.
- Search matches within a line; regex spanning multiple lines is not supported.

## Tests

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tests/smoke.py   # 147 checks
/usr/bin/python3 tests/stress_save.py                        # 29 file-safety checks
/usr/bin/python3 tests/screenshot.py                        # day & night screenshots
```