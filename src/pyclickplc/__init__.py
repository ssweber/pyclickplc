"""pyclickplc - Utilities for AutomationDirect CLICK PLCs."""

from .addresses import (
    AddressRecord,
    format_address_display,
    normalize_address,
    parse_address,
)
from .banks import (
    BANKS,
    BankConfig,
    DataType,
)
from .capabilities import (
    CLICK_HARDWARE_PROFILE,
    COMPARE_COMPATIBILITY,
    COMPARE_CONSTANT_COMPATIBILITY,
    COPY_COMPATIBILITY,
    INSTRUCTION_ROLE_COMPATIBILITY,
    LADDER_BANK_CAPABILITIES,
    LADDER_WRITABLE_SC,
    LADDER_WRITABLE_SD,
    BankCapability,
    ClickHardwareProfile,
    CompareConstantKind,
    CopyOperation,
    InstructionRole,
)
from .client import ClickClient, ModbusResponse
from .dataview import (
    DataviewRow,
    check_cdv_file,
    check_cdv_files,
    export_cdv,
    get_dataview_folder,
    list_cdv_files,
    load_cdv,
    save_cdv,
)
from .modbus import (
    ModbusMapping,
    modbus_to_plc,
    pack_value,
    plc_to_modbus,
    unpack_value,
)
from .nicknames import read_csv, read_mdb_csv, write_csv
from .server import ClickServer, MemoryDataProvider
from .validation import validate_comment, validate_initial_value, validate_nickname

__all__ = [
    "BankConfig",
    "BANKS",
    "DataType",
    "AddressRecord",
    "format_address_display",
    "parse_address",
    "normalize_address",
    "ClickClient",
    "ModbusResponse",
    "InstructionRole",
    "CopyOperation",
    "CompareConstantKind",
    "BankCapability",
    "ClickHardwareProfile",
    "CLICK_HARDWARE_PROFILE",
    "LADDER_WRITABLE_SC",
    "LADDER_WRITABLE_SD",
    "LADDER_BANK_CAPABILITIES",
    "INSTRUCTION_ROLE_COMPATIBILITY",
    "COPY_COMPATIBILITY",
    "COMPARE_COMPATIBILITY",
    "COMPARE_CONSTANT_COMPATIBILITY",
    "ModbusMapping",
    "plc_to_modbus",
    "modbus_to_plc",
    "pack_value",
    "unpack_value",
    "ClickServer",
    "MemoryDataProvider",
    "DataviewRow",
    "check_cdv_file",
    "check_cdv_files",
    "export_cdv",
    "load_cdv",
    "save_cdv",
    "get_dataview_folder",
    "list_cdv_files",
    "read_csv",
    "write_csv",
    "read_mdb_csv",
    "validate_nickname",
    "validate_comment",
    "validate_initial_value",
]
