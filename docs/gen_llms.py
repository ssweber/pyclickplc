"""Generate the curated llms.txt index for the pyclickplc documentation site."""

from __future__ import annotations

import argparse
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin

DOCS_DIR = Path(__file__).resolve().parent
CONFIG_FILE = DOCS_DIR.parent / "mkdocs.yml"

SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Getting Started", (("Quickstart", "getting-started/quickstart.md"),)),
    (
        "Guides",
        (
            ("Addressing", "guides/addressing.md"),
            ("Client", "guides/client.md"),
            ("Examples", "guides/examples.md"),
            ("File I/O", "guides/files.md"),
            ("Modbus Service", "guides/modbus_service.md"),
            ("Server & Simulator", "guides/server.md"),
            ("Types & Values", "guides/types.md"),
        ),
    ),
    (
        "API Reference",
        (
            ("Overview", "reference/index.md"),
            ("Addressing API", "reference/api/addressing.md"),
            ("Advanced API", "reference/api/advanced.md"),
            ("Client API", "reference/api/client.md"),
            ("Files API", "reference/api/files.md"),
            ("Server API", "reference/api/server.md"),
            ("Service API", "reference/api/service.md"),
            ("Validation API", "reference/api/validation.md"),
        ),
    ),
)


def _simple_config_value(config_file: Path, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*?)\s*$")
    for line in config_file.read_text(encoding="utf-8").splitlines():
        if match := pattern.match(line):
            return match.group(1).strip("\"'")
    raise RuntimeError(f"Missing {key!r} in {config_file}.")


def _page_url(site_url: str, source_path: str) -> str:
    path = PurePosixPath(source_path)
    if path.name == "index.md":
        route = path.parent.as_posix()
    else:
        route = path.with_suffix("").as_posix()
    return urljoin(site_url.rstrip("/") + "/", route.rstrip("/") + "/")


def generate(
    output_file: Path = DOCS_DIR / "llms.txt",
    *,
    docs_dir: Path = DOCS_DIR,
    config_file: Path = CONFIG_FILE,
) -> Path:
    """Generate the curated HTML-route index used by public agents."""
    site_name = _simple_config_value(config_file, "site_name")
    site_description = _simple_config_value(config_file, "site_description")
    site_url = _simple_config_value(config_file, "site_url")
    lines = [f"# {site_name}", "", f"> {site_description}", ""]

    for section, pages in SECTIONS:
        lines.extend((f"## {section}", ""))
        for label, source_path in pages:
            markdown_file = docs_dir / Path(source_path)
            if not markdown_file.is_file():
                raise RuntimeError(f"Missing llms.txt source page: {markdown_file}.")
            lines.append(f"- [{label}]({_page_url(site_url, source_path)})")
        lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DOCS_DIR,
        help="Prepared documentation source directory",
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        default=CONFIG_FILE,
        help="Site configuration containing name, description, and URL",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=DOCS_DIR / "llms.txt",
        help="Path to generated llms.txt",
    )
    args = parser.parse_args()
    generate(
        args.output_file.resolve(),
        docs_dir=args.docs_dir.resolve(),
        config_file=args.config_file.resolve(),
    )
    print("Generated llms.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
