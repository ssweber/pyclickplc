"""Read installed modules and channel parameters from a CLICK Project.ini file."""

from __future__ import annotations

from collections.abc import Mapping
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from ._module_catalog import _MODULE_CATALOG, Module
from .addresses import format_address_display, parse_address


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


def _read_project(path: str | Path) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            parser.read_file(stream)
    except (ConfigParserError, UnicodeError) as exc:
        raise ValueError(f"Invalid CLICK project configuration: {path}") from exc
    return parser


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


__all__ = [
    "Module",
    "Modules",
    "ChannelParameters",
    "ModuleIO",
    "read_modules",
    "read_channel_parameters",
    "read_io_layout",
]
