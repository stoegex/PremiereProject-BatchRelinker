# Premiere Project Batch Relinker

A safe, dependency-free utility for repairing offline-media paths in Adobe Premiere Pro `.prproj` files. It always creates a new project file and never overwrites the source project.

## What it does

- Replaces a known drive or folder prefix throughout a project, for example `/Volumes/T7/Project` to `H:\\Project`.
- Can search a new media parent folder recursively when the old folder structure has changed completely.
- Writes the output to a separate `__BATCH-NEUVERKNUEPFT.prproj` file.
- Supports the GZip-compressed project files used by current Premiere versions.
- Validates the written project before committing it to its final filename.

## Quick start on Windows

1. Drag a `.prproj` file onto `premiere_prproj_prefix_relinker.bat`.
2. Enter the old stored prefix exactly as it appeared on the previous system.
3. Enter the new prefix.
4. Open the newly created `__BATCH-NEUVERKNUEPFT.prproj` file in Premiere.

Example:

```text
Old prefix: /Volumes/T7 Shield 2/My Project
New prefix: H:\\My Project
```

## Command line

```bat
premiere_prproj_prefix_relinker.bat "H:\\Project\\Edit.prproj" --old-prefix "/Volumes/SSD/Project" --new-prefix "H:\\Project"
```

Use `--dry-run` to see the number of replacements without writing a project:

```bat
premiere_prproj_prefix_relinker.bat "H:\\Project\\Edit.prproj" --old-prefix "/Volumes/SSD/Project" --new-prefix "H:\\Project" --dry-run
```

## Find media when the folder layout changed

If only the new media parent folder is known, use `--media-root`:

```bat
premiere_prproj_prefix_relinker.bat "H:\\Project\\Edit.prproj" --media-root "H:\\Recovered Media"
```

The tool recursively indexes files under `H:\\Recovered Media`, then matches every missing Premiere media path by filename. If multiple files have the same name, it prefers a unique candidate with matching trailing folder names. If a choice is still ambiguous, it stops without writing anything and prints the candidate paths instead of risking a wrong relink.

Choose the highest-level folder that still contains only the relevant media. Existing links are left unchanged.

## Requirements

Python 3 is the only requirement; no packages need to be installed. The batch launcher tries the Windows `py -3` command first and then `python`.
