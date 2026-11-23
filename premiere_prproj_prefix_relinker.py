#!/usr/bin/env python3
"""Safely create a Premiere .prproj copy with a different media-path prefix.

Premiere project files are normally GZip-compressed UTF-8 XML.  This program
never changes the source project: it writes a separately named output file and
checks that the written project can be read back again.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import os
import re
import shutil
import sys
from pathlib import Path


GZIP_MAGIC = b"\x1f\x8b"
FILE_PATH_TAG = re.compile(r"<(?:ActualMedia)?FilePath>(.*?)</(?:ActualMedia)?FilePath>", re.DOTALL)


def read_project(path: Path) -> tuple[str, bool]:
    """Return project text and whether the source used GZip compression."""
    payload = path.read_bytes()
    compressed = payload.startswith(GZIP_MAGIC)
    if compressed:
        try:
            payload = gzip.decompress(payload)
        except OSError as exc:
            raise ValueError("The project file could not be read as GZip.") from exc

    try:
        return payload.decode("utf-8-sig"), compressed
    except UnicodeDecodeError as exc:
        raise ValueError("The project file is not a UTF-8 Premiere project.") from exc


def output_path_for(source: Path) -> Path:
    return source.with_name(f"{source.stem}__BATCH-NEUVERKNUEPFT{source.suffix}")


def normalise_prefix(prefix: str) -> str:
    """Permit a pasted trailing slash without changing a filesystem root."""
    prefix = prefix.strip().strip('"')
    if prefix in {"/", "\\"} or (len(prefix) == 3 and prefix[1:] in {":\\", ":/"}):
        return prefix
    return prefix.rstrip("/\\")


def replace_prefix(text: str, old_prefix: str, new_prefix: str) -> tuple[str, int]:
    """Replace literal path prefixes, including every XML occurrence of it.

    The replacement is deliberately literal.  It does not guess folders or
    alter clip names, and it works for both Mac (/Volumes/...) and Windows
    (H:\\...) prefixes.  A boundary check avoids replacing e.g. /Media inside
    /Media_Archive.
    """
    if not old_prefix:
        raise ValueError("The old prefix must not be empty.")
    if old_prefix == new_prefix:
        raise ValueError("The old and new prefixes are identical.")

    count = 0
    pieces: list[str] = []
    position = 0
    while True:
        found = text.find(old_prefix, position)
        if found < 0:
            break
        end = found + len(old_prefix)
        next_character = text[end : end + 1]
        if next_character and next_character not in "/\\":
            position = end
            continue
        pieces.append(text[position:found])
        pieces.append(new_prefix)
        position = end
        count += 1
    pieces.append(text[position:])
    return "".join(pieces), count


def media_paths_in_project(text: str) -> set[str]:
    """Return absolute-looking file paths stored in Premiere media-path tags."""
    paths = set()
    for match in FILE_PATH_TAG.finditer(text):
        value = match.group(1)
        if "/" in value or "\\" in value:
            paths.add(value)
    return paths


def build_filename_index(media_root: Path) -> dict[str, list[Path]]:
    """Index every file below the user-selected media root by casefolded name."""
    index: dict[str, list[Path]] = defaultdict(list)
    for directory, _, filenames in os.walk(media_root):
        folder = Path(directory)
        for filename in filenames:
            index[filename.casefold()].append(folder / filename)
    return index


def path_tail_score(old_path: str, candidate: Path, media_root: Path) -> int:
    """Prefer candidates whose parent-folder tail matches the stored path."""
    old_parts = [part.casefold() for part in re.split(r"[\\\\/]", old_path) if part]
    try:
        new_parts = [part.casefold() for part in candidate.relative_to(media_root).parts]
    except ValueError:
        return 0
    score = 0
    for old, new in zip(reversed(old_parts[:-1]), reversed(new_parts[:-1])):
        if old != new:
            break
        score += 1
    return score


def find_media_replacements(text: str, media_root: Path) -> tuple[dict[str, str], list[str], dict[str, list[Path]]]:
    """Map missing project media paths to unique matches below ``media_root``.

    Existing paths are left alone. When a filename exists more than once, a
    unique best matching folder tail is accepted; ties are reported instead of
    silently picking the wrong clip.
    """
    index = build_filename_index(media_root)
    replacements: dict[str, str] = {}
    missing: list[str] = []
    ambiguous: dict[str, list[Path]] = {}
    for stored_path in sorted(media_paths_in_project(text)):
        if Path(stored_path).is_file():
            continue
        filename = re.split(r"[\\\\/]", stored_path)[-1]
        candidates = index.get(filename.casefold(), [])
        if not candidates:
            missing.append(stored_path)
            continue
        if len(candidates) == 1:
            replacements[stored_path] = str(candidates[0])
            continue
        scores = {candidate: path_tail_score(stored_path, candidate, media_root) for candidate in candidates}
        highest = max(scores.values())
        winners = [candidate for candidate, score in scores.items() if score == highest]
        if highest > 0 and len(winners) == 1:
            replacements[stored_path] = str(winners[0])
        else:
            ambiguous[stored_path] = winners
    return replacements, missing, ambiguous


def replace_exact_paths(text: str, replacements: dict[str, str]) -> tuple[str, int]:
    count = 0
    for old_path, new_path in replacements.items():
        occurrences = text.count(old_path)
        text = text.replace(old_path, new_path)
        count += occurrences
    return text, count


def write_project(path: Path, text: str, compressed: bool) -> None:
    payload = text.encode("utf-8")
    if compressed:
        with gzip.open(path, "wb", compresslevel=9) as output:
            output.write(payload)
    else:
        path.write_bytes(payload)


def prompt(value: str | None, label: str) -> str:
    return value if value else input(f"{label}: ").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a safe Premiere project copy with updated media-path prefixes."
    )
    parser.add_argument("project", nargs="?", help="Premiere project file (.prproj)")
    parser.add_argument("--old-prefix", help="Stored old prefix, e.g. /Volumes/T7/Project")
    parser.add_argument("--new-prefix", help="New prefix, e.g. H:\\Project")
    parser.add_argument("--media-root", help="New media parent folder to search recursively for missing clips")
    parser.add_argument("--output", help="Path for the newly created project file")
    parser.add_argument("--dry-run", action="store_true", help="Only report changes; do not write a file")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source_text = prompt(args.project, "Path to the .prproj file")
        source = Path(source_text.strip('"')).expanduser()
        if not source.is_file():
            raise ValueError(f"File not found: {source}")
        if source.suffix.lower() != ".prproj":
            raise ValueError("Please provide a .prproj file.")

        project_text, compressed = read_project(source)
        old_prefix = ""
        new_prefix = ""
        if args.media_root:
            media_root = Path(args.media_root.strip('"')).expanduser()
            if not media_root.is_dir():
                raise ValueError(f"Media folder not found: {media_root}")
            print(f"Searching media folder: {media_root}")
            path_mapping, missing, ambiguous = find_media_replacements(project_text, media_root)
            print(f"Uniquely matched clips: {len(path_mapping)}")
            if missing:
                print("Not found (first 10):", *missing[:10], sep="\n  ", file=sys.stderr)
            if ambiguous:
                print("Ambiguous matches (first 10):", file=sys.stderr)
                for path, candidates in list(ambiguous.items())[:10]:
                    print(f"  {path}\n    Candidates: " + "; ".join(map(str, candidates)), file=sys.stderr)
            if missing or ambiguous:
                raise ValueError("No file was written: choose a more specific media folder or resolve duplicate filenames.")
            if not path_mapping:
                raise ValueError("No missing media paths with matching files were found.")
            updated_text, replacements = replace_exact_paths(project_text, path_mapping)
        else:
            old_prefix = normalise_prefix(prompt(args.old_prefix, "Old prefix (exactly as stored in the project)"))
            new_prefix = normalise_prefix(prompt(args.new_prefix, "New prefix"))
            updated_text, replacements = replace_prefix(project_text, old_prefix, new_prefix)
            if replacements == 0:
                raise ValueError(
                    "The old prefix was not found in the project. "
                    "Check spelling and slash direction (/ versus \\)."
                )

        print(f"Path references found and replaced: {replacements}")
        if args.dry_run:
            print("Dry run complete: no file was written.")
            return 0

        target = Path(args.output).expanduser() if args.output else output_path_for(source)
        target = target.resolve()
        if target == source.resolve():
            raise ValueError("The source project must not be overwritten. Choose another output path.")
        if target.exists() and not args.force:
            raise ValueError(f"Output file already exists: {target}\nUse --force to overwrite it.")
        target.parent.mkdir(parents=True, exist_ok=True)

        # Copy first so a failed write can never leave an unrelated partial file.
        temporary = target.with_suffix(target.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        shutil.copy2(source, temporary)
        write_project(temporary, updated_text, compressed)

        # Integrity check: the saved output must read normally and contain no old prefix.
        check_text, _ = read_project(temporary)
        if old_prefix and old_prefix in check_text:
            raise ValueError("Verification failed: the old prefix is still present.")
        if new_prefix and check_text.count(new_prefix) < replacements:
            raise ValueError("Verification failed: not all new prefixes were saved.")
        temporary.replace(target)

        print("\nDone. The source project was left unchanged.")
        print(f"New project file: {target}")
        print("Open this copy in Premiere first and verify the media links.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
