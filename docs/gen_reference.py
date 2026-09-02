"""Generate curated API reference pages for the pyclickplc documentation build."""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

PACKAGE = "pyclickplc"
DOCS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ReferencePage:
    slug: str
    title: str
    tier: str
    summary: str
    symbols: tuple[str, ...]


PAGES: tuple[ReferencePage, ...] = (
    ReferencePage(
        slug="client",
        title="Client API",
        tier="Stable Core",
        summary="Async client and response mapping APIs.",
        symbols=("ClickClient", "ModbusResponse"),
    ),
    ReferencePage(
        slug="service",
        title="Service API",
        tier="Stable Core",
        summary="Synchronous service wrapper and polling lifecycle APIs.",
        symbols=("ModbusService", "ReconnectConfig", "ConnectionState", "WriteResult"),
    ),
    ReferencePage(
        slug="server",
        title="Server API",
        tier="Stable Core",
        summary="CLICK Modbus TCP simulator and server utilities.",
        symbols=("ClickServer", "MemoryDataProvider", "ServerClientInfo", "run_server_tui"),
    ),
    ReferencePage(
        slug="files",
        title="Files API",
        tier="Stable Core",
        summary="Nickname CSV and DataView CDV models and file I/O helpers.",
        symbols=(
            "read_csv",
            "write_csv",
            "AddressRecordMap",
            "make_address_record",
            "read_cdv",
            "write_cdv",
            "verify_cdv",
            "check_cdv_file",
            "DataViewFile",
            "DataViewRecord",
            "make_dataview_record",
            "get_data_type_for_address",
            "validate_new_value",
            "read_plc_data",
            "write_plc_data",
        ),
    ),
    ReferencePage(
        slug="addressing",
        title="Addressing API",
        tier="Stable Core",
        summary="Address model and canonical normalized address helpers.",
        symbols=(
            "AddressRecord",
            "parse_address",
            "normalize_address",
            "format_address_display",
        ),
    ),
    ReferencePage(
        slug="validation",
        title="Validation API",
        tier="Stable Core",
        summary="Nickname/comment/initial-value validators and system nickname constants.",
        symbols=(
            "AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE",
            "AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE",
            "AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON",
            "AUTOMATIONDIRECT_SYSTEM_NICKNAMES",
            "SystemNicknameGuidance",
            "SYSTEM_NICKNAME_TYPES",
            "canonical_system_nickname",
            "canonicalize_system_nickname",
            "is_canonical_system_nickname",
            "validate_nickname",
            "validate_comment",
            "validate_initial_value",
        ),
    ),
    ReferencePage(
        slug="advanced",
        title="Advanced API",
        tier="Advanced / Evolving",
        summary="Lower-level bank metadata and Modbus mapping helpers.",
        symbols=(
            "BANKS",
            "BankConfig",
            "DataType",
            "ModbusMapping",
            "plc_to_modbus",
            "modbus_to_plc",
            "pack_value",
            "unpack_value",
        ),
    ),
)


def _validate_manifest() -> None:
    exported = set(import_module(PACKAGE).__all__)
    assigned = [symbol for page in PAGES for symbol in page.symbols]
    counts = Counter(assigned)

    duplicates = sorted(symbol for symbol, count in counts.items() if count > 1)
    assigned_set = set(counts)
    missing = sorted(exported - assigned_set)
    extra = sorted(assigned_set - exported)

    if not (duplicates or missing or extra):
        return

    parts: list[str] = ["API reference manifest does not match pyclickplc.__all__."]
    if duplicates:
        parts.append(f"Duplicate symbols: {', '.join(duplicates)}")
    if missing:
        parts.append(f"Missing exported symbols: {', '.join(missing)}")
    if extra:
        parts.append(f"Unknown symbols not exported: {', '.join(extra)}")
    raise RuntimeError(" ".join(parts))


def _write_text(output_dir: Path, relative_path: Path, text: str) -> Path:
    destination = output_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.rstrip() + "\n", encoding="utf-8")
    return destination


def _write_reference_page(page: ReferencePage, output_dir: Path) -> Path:
    doc_rel_path = Path("reference/api") / f"{page.slug}.md"
    lines = [
        f"# {page.title}",
        "",
        f"**Tier:** {page.tier}",
        "",
        page.summary,
        "",
    ]
    if page.slug == "client":
        lines.extend(
            [
                "## Client Surface",
                "",
                "- Dynamic bank accessors: `plc.ds`, `plc.df`, `plc.y`, `plc.txt`, etc.",
                "- Display-indexed accessors: `plc.xd` and `plc.yd` use display indices `0..8`.",
                "- Upper-byte aliases: `plc.xd0u` and `plc.yd0u` expose `XD0u` / `YD0u`.",
                "- String-address interface: `plc.addr.read(...)` and `plc.addr.write(...)`.",
                "- Nickname/tag interface: `plc.tag.read(...)`, `plc.tag.write(...)`, and `plc.tag.read_all(...)`.",
                "",
                "Because accessor attributes are dynamic, this section is hand-curated and complements docstring-generated signatures below.",
                "",
            ]
        )
    for symbol in page.symbols:
        lines.append(f"::: {PACKAGE}.{symbol}")
        lines.append("")

    return _write_text(output_dir, doc_rel_path, "\n".join(lines))


def _write_index(output_dir: Path) -> Path:
    stable_pages = [page for page in PAGES if page.tier == "Stable Core"]
    advanced_pages = [page for page in PAGES if page.tier != "Stable Core"]
    lines = [
        "# API Reference",
        "",
        "This section is generated from an explicit, versioned public API manifest.",
        "",
        "## Stability Policy",
        "",
        "- Stable core pages document v0.1 compatibility commitments.",
        "- Advanced API pages document lower-level helpers that may evolve faster.",
        "",
        "## Stable Core Pages",
        "",
    ]
    for page in stable_pages:
        lines.append(f"- [{page.title}](api/{page.slug}.md)")

    lines.extend(["", "## Advanced Pages", ""])
    for page in advanced_pages:
        lines.append(f"- [{page.title}](api/{page.slug}.md)")

    return _write_text(output_dir, Path("reference/index.md"), "\n".join(lines))


def generate(output_dir: Path = DOCS_DIR) -> tuple[Path, ...]:
    """Generate the curated reference Markdown and return the written paths."""
    _validate_manifest()
    reference_dir = output_dir / "reference"
    if reference_dir.exists():
        shutil.rmtree(reference_dir)

    paths = [_write_reference_page(page, output_dir) for page in PAGES]
    paths.append(_write_index(output_dir))
    return tuple(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DOCS_DIR,
        help="Documentation source directory to receive generated files",
    )
    args = parser.parse_args()
    paths = generate(args.output_dir.resolve())
    print(f"Generated {len(paths)} API reference page(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
