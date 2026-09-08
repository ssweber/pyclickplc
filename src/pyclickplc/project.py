"""Read installed modules and channel parameters from a CLICK Project.ini file."""

from __future__ import annotations

from collections.abc import Mapping
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

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
    modules = _read_modules(parser)

    inputs: set[str] = set()
    outputs: set[str] = set()
    if modules.cpu is not None:
        for prefix, count, addresses in (
            ("AD", modules.cpu.analog_inputs, inputs),
            ("DA", modules.cpu.analog_outputs, outputs),
        ):
            for channel in range(1, count + 1):
                key = f"{prefix}{channel}"
                value = parser.get("CPUBuild", key, fallback="").strip()
                if value:
                    addresses.add(_df_address(value.split(",")[0], f"CPUBuild.{key}"))

    configured = [
        *((position + 1, module) for position, module in modules.expansions.items()),
        *((position + 10, module) for position, module in modules.slots.items()),
    ]
    for item, module in configured:
        key = f"Item{item}"
        count = module.analog_inputs + module.analog_outputs
        if not count:
            continue
        value = parser.get("SystemConfigData", key, fallback="").strip(" \r\n")
        if not value:
            continue
        records = value.split("\t")[1:]
        if len(records) < count or any(record.strip() for record in records[count:]):
            raise ValueError(f"Invalid channel count at SystemConfigData.{key} ({module.model})")
        for index, record in enumerate(records[:count]):
            if not record.strip():
                continue
            fields = record.split(",")
            location = f"SystemConfigData.{key} channel {index + 1}"
            if len(fields) < 7:
                raise ValueError(f"Invalid channel record at {location}")
            address = fields[6].strip()
            if address:
                target = inputs if index < module.analog_inputs else outputs
                target.add(_df_address(address, location))

    return ChannelParameters(frozenset(inputs), frozenset(outputs))


__all__ = ["Module", "Modules", "ChannelParameters", "read_modules", "read_channel_parameters"]
