"""Tests for the public names that pyclickplc and each of its modules list in ``__all__``."""

import pkgutil
from importlib import import_module
from types import ModuleType

import pytest

import pyclickplc

TOP_LEVEL_NAMES = frozenset(
    {
        "AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE",
        "AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE",
        "AUTOMATIONDIRECT_SYSTEM_NICKNAMES",
        "AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON",
        "AddressRecord",
        "AddressRecordMap",
        "BANKS",
        "BankConfig",
        "ChannelParameters",
        "ClickClient",
        "ClickServer",
        "ConnectionState",
        "DataType",
        "DataViewFile",
        "DataViewRecord",
        "MemoryDataProvider",
        "ModbusMapping",
        "ModbusResponse",
        "ModbusService",
        "Module",
        "ModuleIO",
        "Modules",
        "PlcDataReadError",
        "ReconnectConfig",
        "SYSTEM_NICKNAME_TYPES",
        "ServerClientInfo",
        "SystemNicknameGuidance",
        "UnknownModule",
        "WriteResult",
        "canonical_system_nickname",
        "canonicalize_system_nickname",
        "check_cdv_file",
        "first_non_cp1252_char",
        "format_address_display",
        "format_csv",
        "get_data_type_for_address",
        "is_canonical_system_nickname",
        "iter_address_slots",
        "make_address_record",
        "make_dataview_record",
        "modbus_to_plc",
        "normalize_address",
        "pack_value",
        "parse_address",
        "plc_to_modbus",
        "read_cdv",
        "read_channel_parameters",
        "read_csv",
        "read_io_layout",
        "read_mdb_csv",
        "read_modules",
        "read_plc_data",
        "read_plc_name",
        "run_server_tui",
        "unpack_value",
        "validate_click_name",
        "validate_comment",
        "validate_initial_value",
        "validate_new_value",
        "validate_nickname",
        "verify_cdv",
        "write_cdv",
        "write_csv",
        "write_plc_data",
        "write_plc_name",
    }
)


def _public_modules() -> list[ModuleType]:
    """Return each submodule of pyclickplc whose dotted name has no part that starts with _."""
    return [
        import_module(info.name)
        for info in pkgutil.walk_packages(pyclickplc.__path__, prefix="pyclickplc.")
        if not any(part.startswith("_") for part in info.name.split("."))
    ]


PUBLIC_MODULES = _public_modules()


def test_top_level_all_is_unchanged():
    assert len(pyclickplc.__all__) == len(set(pyclickplc.__all__))
    assert set(pyclickplc.__all__) == TOP_LEVEL_NAMES


def test_every_public_module_is_found():
    assert {module.__name__ for module in PUBLIC_MODULES} == {
        "pyclickplc.addresses",
        "pyclickplc.banks",
        "pyclickplc.blocks",
        "pyclickplc.client",
        "pyclickplc.dataview",
        "pyclickplc.modbus",
        "pyclickplc.modbus_service",
        "pyclickplc.nicknames",
        "pyclickplc.plcdata",
        "pyclickplc.project",
        "pyclickplc.server",
        "pyclickplc.server_tui",
        "pyclickplc.system",
        "pyclickplc.validation",
    }


@pytest.mark.parametrize("module", PUBLIC_MODULES, ids=lambda module: module.__name__)
def test_module_all_names_exist(module: ModuleType):
    names = module.__all__
    assert len(names) == len(set(names))
    for name in names:
        assert not name.startswith("_")
        getattr(module, name)


@pytest.mark.parametrize("name", sorted(TOP_LEVEL_NAMES))
def test_top_level_name_is_public_in_a_module(name: str):
    """Each name in ``pyclickplc.__all__`` is also in the ``__all__`` of a public module."""
    homes = [
        module.__name__
        for module in PUBLIC_MODULES
        if name in module.__all__ and getattr(module, name) is getattr(pyclickplc, name)
    ]
    assert homes
