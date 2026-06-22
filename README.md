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
