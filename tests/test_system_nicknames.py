"""Tests for maintained vendor system-nickname guidance."""

from datetime import date

from pyclickplc import canonical_system_nickname as root_canonical_system_nickname
from pyclickplc.system import (
    AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE,
    AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE,
    AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON,
    AUTOMATIONDIRECT_SYSTEM_NICKNAMES,
    canonical_system_nickname,
    canonicalize_system_nickname,
    is_canonical_system_nickname,
)
from pyclickplc.validation import validate_nickname


def test_known_stale_and_blank_values_have_documented_repairs():
    assert (
        canonicalize_system_nickname("SD", 132, "_Port1_AL_Denied_Count")
        == "_Port1_AL_Denied_No1_Cnt"
    )
    assert (
        canonicalize_system_nickname("SD", 133, "_WLAN_AL_Denied_Count")
        == "_WLAN_AL_Denied_No1_Cnt"
    )
    assert canonicalize_system_nickname("SD", 134, "") == "_Port1_AL_Denied_Count"
    assert canonicalize_system_nickname("SD", 135, "") == "_WLAN_AL_Denied_Count"


def test_unknown_vendor_value_is_preserved():
    assert canonicalize_system_nickname("SD", 132, "_Future_Vendor_Name") == "_Future_Vendor_Name"


def test_informational_entries_do_not_fill_blank_values_automatically():
    assert canonical_system_nickname("SC", 1) == "_Always_ON"
    assert canonical_system_nickname("SD", 1) == "_PLC_Error_Code"
    assert canonicalize_system_nickname("SC", 1, "") == ""
    assert canonicalize_system_nickname("SD", 1, "") == ""


def test_only_incident_addresses_repair_blank_values():
    blank_repairs = {
        key
        for key, guidance in AUTOMATIONDIRECT_SYSTEM_NICKNAMES.items()
        if "" in guidance.repair_from
    }
    assert blank_repairs == {("SD", 132), ("SD", 133), ("SD", 134), ("SD", 135)}


def test_canonical_lookup_and_check_are_address_based():
    assert canonical_system_nickname("sd", 132) == "_Port1_AL_Denied_No1_Cnt"
    assert is_canonical_system_nickname("SD", 132, "_Port1_AL_Denied_No1_Cnt")
    assert not is_canonical_system_nickname("SD", 132, "_Port1_AL_Denied_Count")
    assert canonical_system_nickname("DS", 132) is None


def test_catalog_covers_current_sc_and_sd_vendor_tables_with_provenance():
    assert len(AUTOMATIONDIRECT_SYSTEM_NICKNAMES) >= 250
    assert canonical_system_nickname("SC", 335) == "_S1INT_Application_Flag"
    assert canonical_system_nickname("SD", 453) == "_S1_DataUpdateCycleTime"
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON == date(2026, 9, 2)
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAMES[("SC", 335)].source == (
        AUTOMATIONDIRECT_SYSTEM_CONTROL_RELAY_SOURCE
    )
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAMES[("SD", 453)].source == (
        AUTOMATIONDIRECT_SYSTEM_DATA_REGISTER_SOURCE
    )


def test_catalog_values_are_valid_system_names_and_root_api_reexports_lookup():
    assert root_canonical_system_nickname("SC", 1) == "_Always_ON"
    for (memory_type, _address), guidance in AUTOMATIONDIRECT_SYSTEM_NICKNAMES.items():
        assert guidance.nickname.startswith("_")
        assert validate_nickname(guidance.nickname, system_bank=memory_type) == (True, "")


def test_model_dependent_or_internally_inconsistent_rows_are_not_guessed():
    assert canonical_system_nickname("SD", 73) is None
    assert canonical_system_nickname("SD", 74) is None
    assert canonical_system_nickname("SD", 150) is None
