# Living Folders

**A directory should be allowed to present itself according to its purpose.**

Living Folders is a small semantic lens over the ordinary filesystem. It reads
an optional `.living-folder.json`, notices the folder's real contents, and
renders the directory as a workbench, project ground, factory, gallery, ruin,
or another kind of place.

```powershell
python -m pip install -e .
living-folders .
```

Inspect the same canonical portrait without opening a window:

```powershell
living-folders . --inspect
```

Give an existing directory a starter constitution:

```powershell
living-folders C:\some\folder --init
```

The fuller orientation and manifest SoftSpec live in `docs/raw/`.
