# Living Folders

**A directory should be allowed to present itself according to its purpose.**

Living Folders is a small semantic lens over the ordinary filesystem. It reads
an optional `.living-folder/description.json`, notices the folder's real contents, and
renders the directory as a workbench, project ground, factory, gallery, ruin,
temporal landscape, or another kind of place.

Legacy `.living-folder.json` files remain readable. New writes use the
`.living-folder/` directory form.

```powershell
python -m pip install -e .
python -m livingfolders --execpath.open-at .
```

Inspect the same canonical portrait without opening a window:

```powershell
python -m livingfolders --execpath.open-at . inspect
```

Give an existing directory a starter constitution:

```powershell
python -m livingfolders --execpath.open-at C:\some\folder init
```

The window provides editable path navigation, back/up/refresh controls,
presentation override, compact folder buttons, Explorer and shell escape
hatches, and a draggable/resizable Directory Map presentation.

Directory Map treats its layout as a human-authored composition. Newly
discovered files and folders wait in a fixed Incoming dock until they are
clicked or dragged into place. Entries may be ignored without altering the
filesystem. A placed entry that later disappears remains as a removable red
ghost so the map can remember what was there.

Folders dominated by valid `YYYY-MM-DD` entry names are inferred as Temporal
Folders. Their Daystream presentation places canonical date folders and dated
artifacts onto a continuous Monday-first week strip, supplies a month/year
minimap, preserves undated entries in an exceptions shelf, and smart-opens or
creates the selected temporal node. The files and directories remain ordinary
filesystem entries; the calendar is only their interpretation.

The fuller orientation and manifest SoftSpec live in `docs/raw/`.

## Stable runtime root

Living Folders now relies directly on `lionscliapp`'s Tk single-instance
runtime. To make that machine-stable, launch it with an explicit `--execroot`.
The package no longer installs a bare `living-folders.exe` script; the intended
Windows entry path is through the launcher batch files or `python -m`.

The included Windows launchers in [launchers](C:/lion/github/living-folders/launchers)
assume:

```text
C:\lion\runtime\living-folders
```

as the stable runtime root.

The GUI launcher:

```powershell
launchers\living-folders.bat "C:\lion\github"
```

translates to:

```powershell
pythonw -m livingfolders --execroot C:\lion\runtime\living-folders --execpath.open-at "C:\lion\github"
```

The debug launcher uses `python` instead of `pythonw`:

```powershell
launchers\living-folders-debug.bat "C:\lion\github"
```
