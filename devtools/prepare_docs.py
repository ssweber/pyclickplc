"""Prepare publishable authored documentation in an ignored build directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE_DOCS_DIR = ROOT_DIR / "docs"
OUTPUT_DOCS_DIR = ROOT_DIR / "docs_build"
BLOCKED_FILENAMES = {
    "agents.md",
    "claude.md",
    "gen_llms.py",
    "gen_reference.py",
    "llms-full.txt",
    "llms.txt",
}


def _is_publishable(relative_path: Path) -> bool:
    parts = tuple(part.lower() for part in relative_path.parts)
    if "internal" in parts or "__pycache__" in parts:
        return False
    if parts and parts[0] == "reference":
        return False
    if relative_path.suffix.lower() in {".py", ".pyc", ".pyo"}:
        return False
    return relative_path.name.lower() not in BLOCKED_FILENAMES


def prepare(
    source_dir: Path = SOURCE_DOCS_DIR,
    output_dir: Path = OUTPUT_DOCS_DIR,
) -> tuple[Path, ...]:
    """Copy publishable source files into a clean generated docs directory."""
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == source_dir or output_dir.is_relative_to(source_dir):
        raise RuntimeError("Prepared docs directory must be outside source docs.")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    copied: list[Path] = []
    for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
        relative_path = source.relative_to(source_dir)
        if not _is_publishable(relative_path):
            continue
        destination = output_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
    return tuple(copied)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=SOURCE_DOCS_DIR,
        help="Authored documentation directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DOCS_DIR,
        help="Ignored directory to receive publishable documentation",
    )
    args = parser.parse_args()
    copied = prepare(args.source_dir, args.output_dir)
    print(f"Prepared {len(copied)} authored documentation file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
