"""Generate curated MkDocs API reference pages for pyclickplc public exports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

import mkdocs_gen_files

PACKAGE = "pyclickplc"


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
            "read_cdv",
            "write_cdv",
            "verify_cdv",
            "check_cdv_file",
            "DataViewFile",
            "DataViewRecord",
            "get_data_type_for_address",
            "validate_new_value",
        ),
    ),
    ReferencePage(
        slug="addressing",
        title="Addressing API",
        tier="Stable Core",
        summary="Address model and canonical normalized address helpers.",
        symbols=("AddressRecord", "parse_address", "normalize_address", "format_address_display"),
    ),
    ReferencePage(
        slug="validation",
        title="Validation API",
        tier="Stable Core",
        summary="Nickname/comment/initial-value validators and system nickname constants.",
        symbols=(
            "SYSTEM_NICKNAME_TYPES",
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


def _write_reference_page(page: ReferencePage) -> None:
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

    with mkdocs_gen_files.open(doc_rel_path, "w") as fd:
        fd.write("\n".join(lines).rstrip() + "\n")
    mkdocs_gen_files.set_edit_path(doc_rel_path, Path("docs/gen_reference.py"))


def _write_index() -> None:
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

    with mkdocs_gen_files.open("reference/index.md", "w") as fd:
        fd.write("\n".join(lines).rstrip() + "\n")
    mkdocs_gen_files.set_edit_path("reference/index.md", Path("docs/gen_reference.py"))


_validate_manifest()
for ref_page in PAGES:
    _write_reference_page(ref_page)
_write_index()
