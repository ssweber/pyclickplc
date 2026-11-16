"""Read installed modules, channel parameters and the PLC name from CLICK's Project.ini.

``write_plc_name`` sets the PLC name.
"""

from __future__ import annotations

import codecs
import io
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from ._module_catalog import _MODULE_CATALOG, Module
from .addresses import format_address_display, parse_address
from .validation import validate_click_name


@dataclass(frozen=True)
class Modules:
    """Installed CPU, CPU slots 0/1, and expansion positions 1..8.

    Empty positions are omitted from the read-only mappings. CPU is None if
    the project does not identify one. Power supplies are not included.
    """

    cpu: Module | None = None
    slots: Mapping[int, Module] = field(default_factory=dict)
    expansions: Mapping[int, Module] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Copy before wrapping so a caller cannot mutate a result indirectly.
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))
        object.__setattr__(self, "expansions", MappingProxyType(dict(self.expansions)))


@dataclass(frozen=True)
class ChannelParameters:
    """Normalized DF addresses assigned to analog input and output channels."""

    inputs: frozenset[str] = frozenset()
    outputs: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ModuleIO:
    """One installed module and the addresses of its I/O points.

    Position is 0 for the CPU, 0/1 for CLICK PLUS slots, and 1..8 for
    expansions. Discrete addresses follow the module's point counts. Analog
    tuples hold one DF address per channel in channel order, or None for a
    channel with no assignment.
    """

    location: Literal["cpu", "slot", "expansion"]
    position: int
    module: Module
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    analog_inputs: tuple[str | None, ...]
    analog_outputs: tuple[str | None, ...]


def _df_address(value: str, location: str) -> str:
    try:
        bank, index = parse_address(value)
        if bank != "DF":
            raise ValueError("expected a DF address")
    except ValueError as exc:
        raise ValueError(f"Invalid channel address at {location}: {value!r}") from exc
    return format_address_display(bank, index)


def _module(module_id: int, location: str) -> Module | None:
    if not module_id:
        return None
    try:
        return _MODULE_CATALOG[module_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported module ID {module_id} at {location}") from exc


# CLICK 4 writes Project.ini with placeholder section and key names. The values are
# unchanged; this table (from CLICK's SCFS.dll, the same in 3.92 and 4.00) maps back
# the names read here. A key ending in "_" is a prefix for numbered keys (Key3_1 ->
# Item1); every other key must match exactly.
_PLACEHOLDER_NAMES = {
    "Sec20": ("PLCName", {"Key1": "PLCName"}),
    "Sec21": ("SystemConfig", {"Key3_": "Item"}),
    "Sec22": ("SystemConfigData", {"Key1_": "Item"}),
    "Sec23": (
        "CPUBuild",
        {
            "Key1": "ID",
            "Key9": "AD1",
            "Key10": "AD2",
            "Key15": "AD3",
            "Key16": "AD4",
            "Key11": "DA1",
            "Key12": "DA2",
        },
    ),
}


def _placeholder_key(key: str, names: Mapping[str, str]) -> str | None:
    for placeholder, name in names.items():
        placeholder = placeholder.lower()
        if not placeholder.endswith("_"):
            if key == placeholder:
                return name
        elif key.startswith(placeholder) and key[len(placeholder) :].isdigit():
            return name + key[len(placeholder) :]
    return None


def _uses_placeholder_names(parser: ConfigParser) -> bool:
    """Whether the file as written uses CLICK 4's placeholder names."""
    return not parser.has_section("SystemConfig") and parser.has_section("Sec21")


def _placeholder_option(section: str, key: str) -> tuple[str, str]:
    """The CLICK 4 placeholder section and key for a named section and key."""
    for placeholder, (name, names) in _PLACEHOLDER_NAMES.items():
        if name != section:
            continue
        for placeholder_key, key_name in names.items():
            if key_name == key and not placeholder_key.endswith("_"):
                return placeholder, placeholder_key
    raise KeyError((section, key))


def _restore_names(parser: ConfigParser) -> None:
    """Rename a CLICK 4 file's placeholder sections and keys to the names read here."""
    if not _uses_placeholder_names(parser):
        return
    for placeholder, (section, names) in _PLACEHOLDER_NAMES.items():
        if not parser.has_section(placeholder):
            continue
        # A file can hold both, such as a [PLCName] another tool added. The placeholder's
        # values win over the named section's; checked in CLICK 4, which shows the
        # [Sec20] name over a stray [PLCName].
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in parser.items(placeholder):
            name = _placeholder_key(key, names)
            if name is not None:
                parser.set(section, name, value)


def _parse_project(
    data: bytes, path: str | Path, *, restore: bool = True, strict: bool = True
) -> ConfigParser:
    """Parse Project.ini bytes; with *restore*, CLICK 4's placeholder names are mapped back.

    Unless *strict*, a repeated section or option is accepted (the PLC name takes the first).
    """
    parser = ConfigParser(interpolation=None, strict=strict)
    try:
        # newline=None reads \r\n, \r and \n line ends as opening the file in text mode does.
        parser.read_file(io.StringIO(data.decode("utf-8-sig"), newline=None), source=str(path))
        if restore:
            _restore_names(parser)
    except (ConfigParserError, UnicodeError) as exc:
        raise ValueError(f"Invalid CLICK project configuration: {path}") from exc
    return parser


def _read_project(path: str | Path) -> ConfigParser:
    return _parse_project(Path(path).read_bytes(), path)


def _read_modules(parser: ConfigParser) -> Modules:
    # SystemConfig is authoritative. Do not evaluate stale CPUBuild data when
    # Item1 exists (including an explicit zero indicating no CPU).
    if parser.has_option("SystemConfig", "Item1"):
        cpu_id = parser.getint("SystemConfig", "Item1")
    else:
        cpu_id = parser.getint("CPUBuild", "ID", fallback=0)
    cpu = _module(cpu_id, "SystemConfig.Item1")
    expansions = {}
    for position in range(1, 9):
        key = f"Item{position + 1}"
        module = _module(parser.getint("SystemConfig", key, fallback=0), f"SystemConfig.{key}")
        if module is not None:
            expansions[position] = module
    # The original PLUS CPUs have one option slot; the -2 models have two.
    slot_count = 1 if cpu_id in range(196, 199) else 2 if cpu_id in range(199, 202) else 0
    slots = {}
    for position in range(slot_count):
        key = f"Item{position + 10}"
        module = _module(parser.getint("SystemConfig", key, fallback=0), f"SystemConfig.{key}")
        if module is not None:
            slots[position] = module
    return Modules(cpu=cpu, slots=slots, expansions=expansions)


def read_modules(path: str | Path) -> Modules:
    """Read installed hardware and I/O counts without requiring CLICK installed.

    CPU slots use keys 0 and 1; expansions use keys 1 through 8. Unpopulated
    positions and stale CPU slots unsupported by the installed CPU are omitted.
    Channel parameters are not interpreted, so malformed channel records do
    not prevent reading the hardware inventory.

    Raises OSError for unreadable files and ValueError for malformed INI data,
    invalid module IDs, or unknown installed hardware. Missing CPU information
    returns cpu=None; a file without installed modules returns empty mappings.
    """
    return _read_modules(_read_project(path))


_Location = Literal["cpu", "slot", "expansion"]
_Channels = tuple[tuple[str | None, ...], tuple[str | None, ...]]


def _installed(modules: Modules) -> list[tuple[_Location, int, Module]]:
    """Installed modules in physical order: CPU, slots, then expansions."""
    installed: list[tuple[_Location, int, Module]] = []
    if modules.cpu is not None:
        installed.append(("cpu", 0, modules.cpu))
    installed.extend(("slot", position, module) for position, module in modules.slots.items())
    installed.extend(
        ("expansion", position, module) for position, module in modules.expansions.items()
    )
    return installed


def _cpu_channel(parser: ConfigParser, key: str) -> str | None:
    value = parser.get("CPUBuild", key, fallback="").strip()
    return _df_address(value.split(",")[0], f"CPUBuild.{key}") if value else None


def _channels(
    parser: ConfigParser, location: _Location, position: int, module: Module
) -> _Channels:
    """Read one module's analog DF assignments in channel order; None if unassigned."""
    if location == "cpu":
        return (
            tuple(_cpu_channel(parser, f"AD{n}") for n in range(1, module.analog_inputs + 1)),
            tuple(_cpu_channel(parser, f"DA{n}") for n in range(1, module.analog_outputs + 1)),
        )

    count = module.analog_inputs + module.analog_outputs
    if not count:
        return (), ()
    key = f"Item{position + (10 if location == 'slot' else 1)}"
    value = parser.get("SystemConfigData", key, fallback="").strip(" \r\n")
    addresses: list[str | None] = [None] * count
    if value:
        records = value.split("\t")[1:]
        if len(records) < count or any(record.strip() for record in records[count:]):
            raise ValueError(f"Invalid channel count at SystemConfigData.{key} ({module.model})")
        for index, record in enumerate(records[:count]):
            if not record.strip():
                continue
            fields = record.split(",")
            channel_location = f"SystemConfigData.{key} channel {index + 1}"
            if len(fields) < 7:
                raise ValueError(f"Invalid channel record at {channel_location}")
            address = fields[6].strip()
            if address:
                addresses[index] = _df_address(address, channel_location)
    return tuple(addresses[: module.analog_inputs]), tuple(addresses[module.analog_inputs :])


def _discrete(bank: str, location: _Location, position: int, count: int) -> tuple[str, ...]:
    """Addresses of a module's discrete points of one kind.

    Built-in CPU points and PLUS slot 0 start at *001, PLUS slot 1 at *021
    (the XD0u/YD0u word, which CLICK documents as Slot1), and expansion n
    at *n01. Each position owns one 16-point sparse range.
    """
    base = position * 100 if location == "expansion" else 20 if position == 1 else 0
    return tuple(format_address_display(bank, base + point) for point in range(1, count + 1))


def read_channel_parameters(path: str | Path) -> ChannelParameters:
    """Read analog channel assignments for the installed CLICK hardware.

    Covers built-in CPU analog channels, expansion positions 1..8, and CLICK
    PLUS CPU slots 0 and 1. Output addresses are separate from input addresses;
    scaling and electrical ranges are not interpreted. Empty assignments and
    settings left behind by removed or non-analog modules are ignored.

    Returns empty sets if there are no assigned analog channels. Raises OSError
    for unreadable files and ValueError for malformed channel data or unknown
    installed hardware. No CLICK installation is required.
    """
    parser = _read_project(path)
    inputs: set[str] = set()
    outputs: set[str] = set()
    for location, position, module in _installed(_read_modules(parser)):
        analog_inputs, analog_outputs = _channels(parser, location, position, module)
        inputs.update(address for address in analog_inputs if address is not None)
        outputs.update(address for address in analog_outputs if address is not None)
    return ChannelParameters(frozenset(inputs), frozenset(outputs))


def read_io_layout(path: str | Path) -> tuple[ModuleIO, ...]:
    """Read every installed module with its discrete and analog addresses.

    Modules are returned in physical order: CPU, CLICK PLUS slots, then
    expansions; empty positions are omitted. Discrete addresses are fixed by
    position; analog channels use the DF assignments that
    ``read_channel_parameters`` reads, one entry per channel. Power supplies
    are not included.

    Raises OSError for unreadable files and ValueError for malformed INI data,
    malformed channel data, or unknown installed hardware. No CLICK
    installation is required.
    """
    parser = _read_project(path)
    layout: list[ModuleIO] = []
    for location, position, module in _installed(_read_modules(parser)):
        analog_inputs, analog_outputs = _channels(parser, location, position, module)
        layout.append(
            ModuleIO(
                location=location,
                position=position,
                module=module,
                inputs=_discrete("X", location, position, module.discrete_inputs),
                outputs=_discrete("Y", location, position, module.discrete_outputs),
                analog_inputs=analog_inputs,
                analog_outputs=analog_outputs,
            )
        )
    return tuple(layout)


_PLC_NAME = ("PLCName", "PLCName")

# A section header and the start of an option line, matched as configparser matches them.
_SECTION = re.compile(rb"\[(?P<header>.+)\]")
_OPTION = re.compile(rb"\s*(?P<option>.*?)\s*[=:]\s*")
_COMMENT_PREFIXES = (b"#", b";")


def _lines(data: bytes) -> tuple[bytes, list[bytes]]:
    bom = codecs.BOM_UTF8 if data.startswith(codecs.BOM_UTF8) else b""
    return bom, data[len(bom) :].splitlines(keepends=True)


def _find_option(lines: list[bytes], section: str, key: str) -> tuple[int | None, int | None]:
    """Line numbers of the first section named *section* and its first option *key*.

    Both match regardless of case, as CLICK matches them. Either is None if missing.
    Only the first matching section is searched for the key, as Windows'
    GetPrivateProfileString does: inferred, not tested in CLICK.
    """
    header = section.lower().encode("ascii")
    option = key.lower().encode("ascii")
    start = None
    option_indent = None
    for index, line in enumerate(lines):
        match = _SECTION.match(line.strip())
        if match is not None:
            if start is not None:
                return start, None
            if match["header"].lower() == header:
                start = index
        elif start is not None and line.strip() and not line.strip().startswith(_COMMENT_PREFIXES):
            indent = len(line) - len(line.lstrip())
            if option_indent is not None and indent > option_indent:
                continue  # A line that continues the option before it, as configparser reads it.
            found = _OPTION.match(line.rstrip(b"\r\n"))
            if found is None:
                continue
            option_indent = indent
            if found["option"].lower() == option:
                return start, index
    return start, None


def _is_click_4(parser: ConfigParser) -> bool:
    """Whether the file uses CLICK 4's placeholder names; section names match regardless of case."""
    names = {name.lower() for name in parser.sections()}
    return "systemconfig" not in names and "sec21" in names


def _plc_name_line(
    lines: list[bytes], written: ConfigParser
) -> tuple[str, str, int | None, int | None]:
    """The section and key the name is read from, and their line numbers if present.

    *written* is the file parsed as written, to tell a CLICK 4 file from a CLICK 3 one.
    """
    if not _is_click_4(written):
        return (*_PLC_NAME, *_find_option(lines, *_PLC_NAME))
    placeholder = _placeholder_option(*_PLC_NAME)
    found = _find_option(lines, *placeholder)
    if found[1] is not None:
        return (*placeholder, *found)
    legacy = _find_option(lines, *_PLC_NAME)
    if legacy[1] is not None:
        return (*_PLC_NAME, *legacy)
    # No name yet: use [PLCName] only if it is there and the placeholder section isn't.
    if legacy[0] is not None and found[0] is None:
        return (*_PLC_NAME, *legacy)
    return (*placeholder, *found)


def _plc_name(lines: list[bytes], written: ConfigParser) -> str | None:
    _, key, _, index = _plc_name_line(lines, written)
    if index is None:
        return None
    # Parse the option's line with the lines that continue its value.
    indent = len(lines[index]) - len(lines[index].lstrip())
    snippet = [lines[index]]
    for line in lines[index + 1 :]:
        stripped = line.strip()
        if stripped and not stripped.startswith(_COMMENT_PREFIXES):
            if len(line) - len(line.lstrip()) <= indent:
                break
        snippet.append(line)
    text = b"[s]\n" + b"".join(snippet)
    parser = ConfigParser(interpolation=None, strict=False)
    parser.read_file(io.StringIO(text.decode("utf-8"), newline=None))
    return parser.get("s", key, fallback="").strip() or None


def read_plc_name(path: str | Path) -> str | None:
    """Read the PLC name from a CLICK Project.ini file.

    The name is ``[PLCName] PLCName=``, which CLICK 4 writes as ``[Sec20] Key1=``.
    Section and key names match regardless of case, and the first match in the
    file wins, as in CLICK 4. If a CLICK 4 file has both, ``[Sec20]`` wins.
    Returns None if the project has no PLC name.

    Raises OSError for unreadable files and ValueError for malformed INI data.
    No CLICK installation is required.
    """
    data = Path(path).read_bytes()
    written = _parse_project(data, path, restore=False, strict=False)
    return _plc_name(_lines(data)[1], written)


def _line_end(line: bytes) -> bytes:
    return line[len(line.rstrip(b"\r\n")) :]


def _set_option(data: bytes, section: str, key: str, value: str) -> bytes:
    """Set one option in INI bytes, changing only its line, or add it if it's missing.

    The first section matching *section* and its first option matching *key*,
    regardless of case, are the ones used, and they keep their spelling. The
    value replaces whatever follows the option's delimiter, and the line keeps
    its own line end. A missing option goes right after its section header; a
    missing section goes at the end, with the line end the file already uses.
    """
    bom, lines = _lines(data)
    newline = next((_line_end(line) for line in lines if _line_end(line)), b"\r\n")
    encoded = value.encode("ascii")
    start, index = _find_option(lines, section, key)

    if start is None:
        if lines and not _line_end(lines[-1]):
            lines[-1] += newline
        header = section.encode("ascii")
        lines += [b"[" + header + b"]" + newline, key.encode("ascii") + b"=" + encoded + newline]
    elif index is not None:
        line = lines[index]
        match = _OPTION.match(line.rstrip(b"\r\n"))
        assert match is not None
        lines[index] = line[: match.end()] + encoded + _line_end(line)
    else:
        if not _line_end(lines[start]):
            lines[start] += newline
        lines.insert(start + 1, key.encode("ascii") + b"=" + encoded + newline)
    return bom + b"".join(lines)


def _only_name_changed(before: list[bytes], after: list[bytes]) -> bool:
    """Whether *after* is *before* with one line changed, one line inserted or two appended.

    Line ends are ignored: adding a line may add the end the line before it lacked.
    """
    old = [line.rstrip(b"\r\n") for line in before]
    new = [line.rstrip(b"\r\n") for line in after]
    grow = len(new) - len(old)
    if grow == 0:
        return any(new[:i] == old[:i] and new[i + 1 :] == old[i + 1 :] for i in range(len(old)))
    if grow == 1:
        return any(new[:i] == old[:i] and new[i + 1 :] == old[i:] for i in range(len(old) + 1))
    return grow == 2 and new[: len(old)] == old


def _replace(path: Path, data: bytes) -> None:
    """Write *data* to a temporary file beside *path*, then move it over *path* in one step."""
    descriptor, staging = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, staging)
        os.replace(staging, path)
    except BaseException:
        with suppress(OSError):
            # copymode may have made it read-only, which Windows won't delete.
            os.chmod(staging, stat.S_IREAD | stat.S_IWRITE)
            os.unlink(staging)
        raise


def write_plc_name(path: str | Path, name: str) -> None:
    """Set the PLC name in a CLICK Project.ini file.

    Only the line holding the name changes, or is added if the project has no
    name; every other byte stays as it was. The name goes where ``read_plc_name``
    reads it; a CLICK 4 file with no name gets ``[Sec20] Key1=``, any other file
    ``[PLCName] PLCName=``. The name is checked with ``validate_click_name`` and
    written without surrounding whitespace. The new file goes to a temporary
    file in the same folder, which then replaces Project.ini in one step.

    Raises ValueError for an invalid name or malformed INI data, and OSError if
    the file can't be read or replaced. On an error the file is unchanged.
    """
    is_valid, error = validate_click_name(name)
    if not is_valid:
        raise ValueError(error)
    name = name.strip()
    path = Path(path)
    original = path.read_bytes()
    written = _parse_project(original, path, restore=False, strict=False)
    section, key, _, _ = _plc_name_line(_lines(original)[1], written)
    try:
        updated = _set_option(original, section, key, name)
    except ValueError as exc:
        raise ValueError(f"Cannot set the PLC name in {path}: {exc}") from exc

    # Check the edit before writing: only the name's line moved and the name reads back.
    after = _parse_project(updated, path, restore=False, strict=False)
    updated_lines = _lines(updated)[1]
    if (
        _lines(updated)[0] != _lines(original)[0]
        or not _only_name_changed(_lines(original)[1], updated_lines)
        or _plc_name(updated_lines, after) != name
    ):
        raise ValueError(f"Cannot set the PLC name in {path}")
    # Replace the file a symlink points to, not the link.
    _replace(path.resolve(), updated)


__all__ = [
    "Module",
    "Modules",
    "ChannelParameters",
    "ModuleIO",
    "read_modules",
    "read_channel_parameters",
    "read_io_layout",
    "read_plc_name",
    "write_plc_name",
]
