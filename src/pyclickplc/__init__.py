"""pyclickplc - Utilities for AutomationDirect CLICK PLCs."""

from .addresses import (
    AddressRecord,
    format_address_display,
    make_address_record,
    normalize_address,
    parse_address,
)
from .banks import (
    BANKS,
    BankConfig,
    DataType,
)
from .client import ClickClient, ModbusResponse
from .dataview import (
    DataViewFile,
    DataViewRecord,
    check_cdv_file,
    get_data_type_for_address,
    make_dataview_record,
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
from .modbus_service import ConnectionState, ModbusService, ReconnectConfig, WriteResult
from .nicknames import AddressRecordMap, read_csv, write_csv
from .plcdata import read_plc_data, write_plc_data
from .server import ClickServer, MemoryDataProvider, ServerClientInfo
from .server_tui import run_server_tui
from .system import (
    AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE,
    AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE,
    AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON,
    AUTOMATIONDIRECT_SYSTEM_NICKNAMES,
    SystemNicknameGuidance,
    canonical_system_nickname,
    canonicalize_system_nickname,
    is_canonical_system_nickname,
)
from .validation import (
    SYSTEM_NICKNAME_TYPES,
    validate_comment,
    validate_initial_value,
    validate_nickname,
)

__all__ = [
    "BankConfig",
    "BANKS",
    "DataType",
    "AddressRecord",
    "make_address_record",
    "format_address_display",
    "parse_address",
    "normalize_address",
    "ClickClient",
    "ModbusResponse",
    "ModbusMapping",
    "plc_to_modbus",
    "modbus_to_plc",
    "pack_value",
    "unpack_value",
    "ModbusService",
    "ReconnectConfig",
    "ConnectionState",
    "WriteResult",
    "ClickServer",
    "MemoryDataProvider",
    "ServerClientInfo",
    "run_server_tui",
    "DataViewFile",
    "DataViewRecord",
    "make_dataview_record",
    "check_cdv_file",
    "get_data_type_for_address",
    "validate_new_value",
    "read_cdv",
    "write_cdv",
    "verify_cdv",
    "read_csv",
    "read_plc_data",
    "write_plc_data",
    "AddressRecordMap",
    "write_csv",
    "AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE",
    "AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE",
    "AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON",
    "AUTOMATIONDIRECT_SYSTEM_NICKNAMES",
    "SystemNicknameGuidance",
    "canonical_system_nickname",
    "canonicalize_system_nickname",
    "is_canonical_system_nickname",
    "SYSTEM_NICKNAME_TYPES",
    "validate_nickname",
    "validate_comment",
    "validate_initial_value",
]
