# Living Folders

**A directory should be allowed to present itself according to its purpose.**

Living Folders is a small semantic lens over the ordinary filesystem. It reads
an optional `.living-folder/description.json`, notices the folder's real contents, and
renders the directory as a workbench, project ground, factory, gallery, ruin,
or another kind of place.

Legacy `.living-folder.json` files remain readable. New writes use the
`.living-folder/` directory form.

```powershell
python -m pip install -e .
living-folders --execpath.folder .
```

Inspect the same canonical portrait without opening a window:

```powershell
living-folders --execpath.folder . inspect
```

Give an existing directory a starter constitution:

```powershell
living-folders --execpath.folder C:\some\folder init
```

The window provides editable path navigation, back/up/refresh controls,
presentation override, compact folder buttons, Explorer and shell escape
hatches, and a draggable/resizable Directory Map presentation.

The fuller orientation and manifest SoftSpec live in `docs/raw/`.

## Machine-wide runtime

Machine Root must define:

```text
living-folders-runtime = C:\lion\installed\living-folders
path-dir = C:\bin
```

This directory owns the single-instance `lock-file.json`, FileTalk-style
`inbox/`, and the isolated lionscliapp configuration directory. The launcher
is installed into `path-dir` by:

```powershell
living-folders install-launcher
```

Invoking `living-folders.pyw` starts Living Folders or summons the existing
window.

An optional folder redirects the resident window:

```powershell
living-folders.pyw "C:\lion\github"
```

The development installation currently uses:

```powershell
python -m pip install -e C:\lion\github\living-folders
living-folders install-launcher
```
