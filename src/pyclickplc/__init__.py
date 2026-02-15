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
    DataviewFile,
    DataviewRow,
    check_cdv_file,
    get_data_type_for_address,
    read_cdv,
    validate_new_value,
    verify_cdv,
    write_cdv,
)
from .modbus import (
    ModbusMapping,
    modbus_to_plc,
    pack_value,
    plc_to_modbus,
    unpack_value,
)
from .modbus_service import ConnectionState, ModbusService, WriteResult
from .nicknames import read_csv, write_csv
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
    "ModbusService",
    "ConnectionState",
    "WriteResult",
    "ClickServer",
    "MemoryDataProvider",
    "DataviewFile",
    "DataviewRow",
    "check_cdv_file",
    "get_data_type_for_address",
    "validate_new_value",
    "read_cdv",
    "write_cdv",
    "verify_cdv",
    "read_csv",
    "write_csv",
    "validate_nickname",
    "validate_comment",
    "validate_initial_value",
]
