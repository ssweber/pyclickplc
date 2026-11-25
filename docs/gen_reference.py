"""Generate curated API reference pages for the pyclickplc documentation build."""

from __future__ import annotations

import argparse
import pkgutil
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
    summary: str
    symbols: tuple[str, ...]


PAGES: tuple[ReferencePage, ...] = (
    ReferencePage(
        slug="client",
        title="Client API",
        summary="Async client and response mapping APIs.",
        symbols=("ClickClient", "ModbusResponse"),
    ),
    ReferencePage(
        slug="service",
        title="Service API",
        summary="Synchronous service wrapper and polling lifecycle APIs.",
        symbols=("ModbusService", "ReconnectConfig", "ConnectionState", "WriteResult"),
    ),
    ReferencePage(
        slug="server",
        title="Server API",
        summary="CLICK Modbus TCP simulator and server utilities.",
        symbols=("ClickServer", "MemoryDataProvider", "ServerClientInfo", "run_server_tui"),
    ),
    ReferencePage(
        slug="files",
        title="Files API",
        summary=(
            "Nickname CSV, DataView CDV, PLC data, installed modules, channel parameters, "
            "and the PLC name."
        ),
        symbols=(
            "read_csv",
            "write_csv",
            "format_csv",
            "first_non_cp1252_char",
            "read_mdb_csv",
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
            "Module",
            "Modules",
            "UnknownModule",
            "read_modules",
            "ChannelParameters",
            "read_channel_parameters",
            "ModuleIO",
            "read_io_layout",
            "read_plc_name",
            "write_plc_name",
            "read_plc_data",
            "PlcDataReadError",
            "write_plc_data",
        ),
    ),
    ReferencePage(
        slug="addressing",
        title="Addressing API",
        summary="Address model and canonical normalized address helpers.",
        symbols=(
            "AddressRecord",
            "parse_address",
            "normalize_address",
            "format_address_display",
            "iter_address_slots",
        ),
    ),
    ReferencePage(
        slug="validation",
        title="Validation API",
        summary=(
            "Nickname/comment/initial-value and PLC/DataView name validators, "
            "and system nickname constants."
        ),
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
            "validate_click_name",
        ),
    ),
    ReferencePage(
        slug="advanced",
        title="Advanced API",
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


@dataclass(frozen=True)
class ModuleSection:
    module: str
    symbols: tuple[str, ...]


MODULES_PAGE_SLUG = "modules"
MODULES_PAGE_TITLE = "Modules API"

# The Modules API page has a section for each public module of pyclickplc. _validate_modules
# stops the build when a section's symbols differ from its module's __all__.
MODULES: tuple[ModuleSection, ...] = (
    ModuleSection(
        module="addresses",
        symbols=(
            "get_addr_key",
            "parse_addr_key",
            "is_xd_yd_hidden_slot",
            "xd_yd_display_to_mdb",
            "format_address_display",
            "iter_address_slots",
            "parse_address",
            "normalize_address",
            "AddressRecord",
            "make_address_record",
        ),
    ),
    ModuleSection(
        module="banks",
        symbols=(
            "DataType",
            "DATA_TYPE_DISPLAY",
            "DATA_TYPE_HINTS",
            "BankConfig",
            "BANKS",
            "MEMORY_TYPE_TO_DATA_TYPE",
            "BIT_ONLY_TYPES",
            "MEMORY_TYPE_BASES",
            "DEFAULT_RETENTIVE",
            "INTERLEAVED_PAIRS",
            "PAIRED_RETENTIVE_TYPES",
            "NON_EDITABLE_TYPES",
            "is_valid_address",
        ),
    ),
    ModuleSection(
        module="blocks",
        symbols=(
            "HasComment",
            "BlockRange",
            "BlockTag",
            "StructuredBlockName",
            "parse_structured_block_name",
            "compose_structured_block_name",
            "parse_block_tag",
            "strip_block_tag",
            "format_block_tag",
            "is_block_name_available",
            "find_paired_tag_index",
            "compute_all_block_ranges",
            "validate_block_span",
        ),
    ),
    ModuleSection(module="client", symbols=("ModbusResponse", "ClickClient")),
    ModuleSection(
        module="dataview",
        symbols=(
            "MAX_DATAVIEW_ROWS",
            "get_data_type_for_address",
            "DataViewRecord",
            "make_dataview_record",
            "validate_new_value",
            "DataViewFile",
            "read_cdv",
            "write_cdv",
            "check_cdv_file",
            "verify_cdv",
        ),
    ),
    ModuleSection(
        module="modbus",
        symbols=(
            "ModbusMapping",
            "MODBUS_MAPPINGS",
            "plc_to_modbus",
            "modbus_to_plc",
            "pack_value",
            "unpack_value",
        ),
    ),
    ModuleSection(
        module="modbus_service",
        symbols=("ConnectionState", "WriteResult", "ReconnectConfig", "ModbusService"),
    ),
    ModuleSection(
        module="nicknames",
        symbols=(
            "CSV_ENCODING",
            "first_non_cp1252_char",
            "AddressRecordMap",
            "REQUIRED_COLUMNS",
            "read_csv",
            "format_csv",
            "write_csv",
            "read_mdb_csv",
        ),
    ),
    ModuleSection(
        module="plcdata",
        symbols=("PlcDataReadError", "read_plc_data", "write_plc_data"),
    ),
    ModuleSection(
        module="project",
        symbols=(
            "Module",
            "Modules",
            "ChannelParameters",
            "ModuleIO",
            "UnknownModule",
            "read_modules",
            "read_channel_parameters",
            "read_io_layout",
            "read_plc_name",
            "write_plc_name",
        ),
    ),
    ModuleSection(
        module="server",
        symbols=(
            "PlcValue",
            "DataProvider",
            "MemoryDataProvider",
            "ServerClientInfo",
            "ClickServer",
        ),
    ),
    ModuleSection(module="server_tui", symbols=("run_server_tui",)),
    ModuleSection(
        module="system",
        symbols=(
            "AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE",
            "AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE",
            "AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON",
            "AUTOMATIONDIRECT_SYSTEM_NICKNAMES",
            "SystemNicknameGuidance",
            "canonical_system_nickname",
            "canonicalize_system_nickname",
            "is_canonical_system_nickname",
        ),
    ),
    ModuleSection(
        module="validation",
        symbols=(
            "NICKNAME_MAX_LENGTH",
            "COMMENT_MAX_LENGTH",
            "CLICK_NAME_MAX_LENGTH",
            "CLICK_NAME_PATTERN",
            "SYSTEM_NICKNAME_TYPES",
            "INT_MIN",
            "INT_MAX",
            "INT2_MIN",
            "INT2_MAX",
            "FLOAT_MIN",
            "FLOAT_MAX",
            "validate_nickname",
            "validate_comment",
            "validate_click_name",
            "validate_initial_value",
            "assert_runtime_value",
        ),
    ),
)


def _public_modules() -> list[str]:
    """Return the name of each submodule of pyclickplc whose dotted name has no part that
    starts with _."""
    package = import_module(PACKAGE)
    return sorted(
        info.name.removeprefix(f"{PACKAGE}.")
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{PACKAGE}.")
        if not any(part.startswith("_") for part in info.name.split("."))
    )


def _validate_modules() -> None:
    """Raise ``RuntimeError`` if a module's section and its ``__all__`` disagree."""
    package = import_module(PACKAGE)
    top_level = set(package.__all__)
    sections = [section.module for section in MODULES]
    problems: list[str] = []

    duplicates = sorted(name for name, count in Counter(sections).items() if count > 1)
    if duplicates:
        problems.append(f"Modules with two sections: {', '.join(duplicates)}")
    public = _public_modules()
    missing_sections = sorted(set(public) - set(sections))
    if missing_sections:
        problems.append(f"Modules with no section: {', '.join(missing_sections)}")
    unknown_sections = sorted(set(sections) - set(public))
    if unknown_sections:
        problems.append(f"Sections for no public module: {', '.join(unknown_sections)}")

    for section in MODULES:
        if section.module not in public:
            continue
        name = f"{PACKAGE}.{section.module}"
        module = import_module(name)
        exported = getattr(module, "__all__", None)
        if exported is None:
            problems.append(f"{name} has no __all__")
            continue
        counts = Counter(section.symbols)
        repeated = sorted(symbol for symbol, count in counts.items() if count > 1)
        missing = sorted(set(exported) - set(counts))
        extra = sorted(set(counts) - set(exported))
        if repeated:
            problems.append(f"{name}: symbols listed twice: {', '.join(repeated)}")
        if missing:
            problems.append(f"{name}: in __all__ but not in its section: {', '.join(missing)}")
        if extra:
            problems.append(f"{name}: in its section but not in __all__: {', '.join(extra)}")
        for symbol in section.symbols:
            if not hasattr(module, symbol):
                problems.append(f"{name} has no attribute {symbol}")
            elif symbol in top_level and getattr(module, symbol) is not getattr(package, symbol):
                problems.append(f"{name}.{symbol} is not the object pyclickplc.{symbol} names")

    if problems:
        raise RuntimeError(
            "API reference module sections do not match the modules' __all__. " + " ".join(problems)
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


def _write_modules_page(output_dir: Path) -> Path:
    page_of = {symbol: page.slug for page in PAGES for symbol in page.symbols}
    lines = [
        f"# {MODULES_PAGE_TITLE}",
        "",
        "Each module of pyclickplc lists its public names in `__all__`. "
        "This page lists them by module. "
        f"A name that you can also import from `{PACKAGE}` links to the page that documents it. "
        "The other names are documented in their module's section.",
        "",
    ]
    for section in MODULES:
        name = f"{PACKAGE}.{section.module}"
        module = import_module(name)
        lines.extend([f"## `{name}`", ""])
        summary = (module.__doc__ or "").strip().split("\n\n")[0]
        if summary:
            lines.extend([" ".join(summary.split()), ""])
        for symbol in section.symbols:
            if symbol in page_of:
                target = f"{page_of[symbol]}.md#{PACKAGE}.{symbol}"
            else:
                target = f"#{name}.{symbol}"
            lines.append(f"- [`{symbol}`]({target})")
        lines.append("")
        for symbol in section.symbols:
            if symbol not in page_of:
                lines.extend([f"::: {name}.{symbol}", "    options:", "      heading_level: 3", ""])

    doc_rel_path = Path("reference/api") / f"{MODULES_PAGE_SLUG}.md"
    return _write_text(output_dir, doc_rel_path, "\n".join(lines))


def _write_index(output_dir: Path) -> Path:
    lines = [
        "# API Reference",
        "",
        "This section is generated from an explicit, versioned public API manifest.",
        "",
        "## Stability Policy",
        "",
        "Every name in `pyclickplc.__all__` or in a module's `__all__` is public. "
        "If a release renames or removes a public name, "
        "the CHANGELOG lists it under Breaking changes.",
        "",
        "## Pages",
        "",
    ]
    for page in PAGES:
        lines.append(f"- [{page.title}](api/{page.slug}.md)")
    lines.append(
        f"- [{MODULES_PAGE_TITLE}](api/{MODULES_PAGE_SLUG}.md): "
        "each module's `__all__`, and the names that you import from a module "
        "and not from `pyclickplc`"
    )

    return _write_text(output_dir, Path("reference/index.md"), "\n".join(lines))


def generate(output_dir: Path = DOCS_DIR) -> tuple[Path, ...]:
    """Generate the curated reference Markdown and return the written paths."""
    _validate_manifest()
    _validate_modules()
    reference_dir = output_dir / "reference"
    if reference_dir.exists():
        shutil.rmtree(reference_dir)

    paths = [_write_reference_page(page, output_dir) for page in PAGES]
    paths.append(_write_modules_page(output_dir))
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
