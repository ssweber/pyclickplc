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
        # A file can hold both, such as a [PLCName] another tool added. CLICK 4 writes
        # the placeholder, so its values win over the named section's.
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in parser.items(placeholder):
            name = _placeholder_key(key, names)
            if name is not None:
                parser.set(section, name, value)


def _parse_project(data: bytes, path: str | Path, *, restore: bool = True) -> ConfigParser:
    """Parse Project.ini bytes; with *restore*, CLICK 4's placeholder names are mapped back."""
    parser = ConfigParser(interpolation=None)
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


def _plc_name(parser: ConfigParser) -> str | None:
    return parser.get(*_PLC_NAME, fallback="").strip() or None


def _plc_name_option(written: ConfigParser) -> tuple[str, str]:
    """The section and key ``read_plc_name`` reads the name from, in the file as written."""
    if not _uses_placeholder_names(written):
        return _PLC_NAME
    placeholder = _placeholder_option(*_PLC_NAME)
    if written.has_option(*placeholder):
        return placeholder
    if written.has_option(*_PLC_NAME):
        return _PLC_NAME
    # No name yet: use [PLCName] only if it is there and the placeholder section isn't.
    if written.has_section(_PLC_NAME[0]) and not written.has_section(placeholder[0]):
        return _PLC_NAME
    return placeholder


def read_plc_name(path: str | Path) -> str | None:
    """Read the PLC name from a CLICK Project.ini file.

    The name is ``[PLCName] PLCName=``, which CLICK 4 writes as ``[Sec20] Key1=``.
    If a CLICK 4 file has both, ``[Sec20]`` wins. Returns None if the project has
    no PLC name.

    Raises OSError for unreadable files and ValueError for malformed INI data.
    No CLICK installation is required.
    """
    return _plc_name(_read_project(path))


def _line_end(line: bytes) -> bytes:
    return line[len(line.rstrip(b"\r\n")) :]


def _set_option(data: bytes, section: str, key: str, value: str) -> bytes:
    """Set one option in INI bytes, changing only its line, or add it if it's missing.

    The value replaces whatever follows the option's delimiter, and the line keeps
    its own line end. A missing option goes right after its section header; a
    missing section goes at the end, with the line end the file already uses.
    """
    bom = codecs.BOM_UTF8 if data.startswith(codecs.BOM_UTF8) else b""
    lines = data[len(bom) :].splitlines(keepends=True)
    newline = next((_line_end(line) for line in lines if _line_end(line)), b"\r\n")
    header = section.encode("ascii")
    option = key.lower().encode("ascii")
    encoded = value.encode("ascii")

    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        match = _SECTION.match(line.strip())
        if match is None:
            continue
        if start is not None and end == len(lines):
            end = index
        if match["header"] == header:
            start = index
        elif match["header"].lower() == header.lower():
            # configparser tells these apart, but Windows' INI functions don't.
            spelling = match["header"].decode("ascii", "replace")
            raise ValueError(f"Section [{spelling}] differs from [{section}] only in case")

    if start is None:
        if lines and not _line_end(lines[-1]):
            lines[-1] += newline
        lines += [b"[" + header + b"]" + newline, key.encode("ascii") + b"=" + encoded + newline]
        return bom + b"".join(lines)

    for index in range(start + 1, end):
        line = lines[index]
        if line.strip().startswith(_COMMENT_PREFIXES):
            continue
        match = _OPTION.match(line.rstrip(b"\r\n"))
        if match is not None and match["option"].lower() == option:
            lines[index] = line[: match.end()] + encoded + _line_end(line)
            break
    else:
        if not _line_end(lines[start]):
            lines[start] += newline
        lines.insert(start + 1, key.encode("ascii") + b"=" + encoded + newline)
    return bom + b"".join(lines)


def _options(parser: ConfigParser) -> dict[str, dict[str, str]]:
    return {section: dict(parser.items(section)) for section in parser.sections()}


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

    Raises ValueError for an invalid name, malformed INI data, or a section
    header that differs from the name's section only in case, and OSError if
    the file can't be read or replaced. On an error the file is unchanged.
    """
    is_valid, error = validate_click_name(name)
    if not is_valid:
        raise ValueError(error)
    name = name.strip()
    path = Path(path)
    original = path.read_bytes()
    written = _parse_project(original, path, restore=False)
    section, key = _plc_name_option(written)
    try:
        updated = _set_option(original, section, key, name)
    except ValueError as exc:
        raise ValueError(f"Cannot set the PLC name in {path}: {exc}") from exc

    # Check the edit before writing: the name reads back and no other value moved.
    expected = _options(written)
    expected.setdefault(section, dict(written.items(written.default_section)))[key.lower()] = name
    if (
        _options(_parse_project(updated, path, restore=False)) != expected
        or _plc_name(_parse_project(updated, path)) != name
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
