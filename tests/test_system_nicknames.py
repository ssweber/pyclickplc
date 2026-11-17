"""Tests for maintained vendor system-nickname guidance."""

from datetime import date
from pathlib import Path

from pyclickplc import canonical_system_nickname as root_canonical_system_nickname
from pyclickplc.nicknames import read_csv
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

FIXTURES = Path(__file__).parent / "fixtures"


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
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAME_REVIEWED_ON == date(2026, 11, 16)
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


def test_names_are_the_ones_clicks_plctype_ini_gives():
    expected = {
        ("SC", 19): "_PLC Error",
        ("SC", 20): "_I/O Module Error",
        ("SC", 21): "_System Config Error",
        ("SC", 22): "_I/O Config Error",
        ("SC", 23): "_Memory Check Error",
        ("SC", 24): "_Project File Error",
        ("SC", 25): "_Firmware Version Error",
        ("SC", 26): "_Watchdog Timer Error",
        ("SC", 27): "_Lost SDRAM Data",
        ("SC", 28): "_Battery Low Voltage",
        ("SC", 29): "_Battery Replacement",
        ("SC", 64): "_RemotePLC_Enabled",
        ("SC", 332): "_S1INT_DHCP_Enabled",
        ("SD", 19): "_RTC_Year(4 digits)",
        ("SD", 20): "_RTC_Year(2 digits)",
        ("SD", 21): "_RTC_Month",
        ("SD", 22): "_RTC_Day",
        ("SD", 23): "_RTC_Day_of_The_Week",
        ("SD", 24): "_RTC_Hour",
        ("SD", 25): "_RTC_Minute",
        ("SD", 26): "_RTC_Second",
        ("SD", 214): "_WLAN_No_Comm_Time",
    }
    for (memory_type, address), name in expected.items():
        assert canonical_system_nickname(memory_type, address) == name


def test_help_page_forms_are_not_repaired():
    # No CLICK version wrote these, so a project holding one is left alone.
    assert canonicalize_system_nickname("SD", 21, "_RTC_Month (1-12)") == "_RTC_Month (1-12)"
    assert canonicalize_system_nickname("SD", 23, "_RTC_Day_of_the_Week") == "_RTC_Day_of_the_Week"
    assert not is_canonical_system_nickname("SD", 21, "_RTC_Month (1-12)")


def test_catalog_agrees_with_clicks_own_csv_exports():
    # The user named the first and last SC and SD rows, so those rows do not hold CLICK's names.
    user_set = {("SC", 1), ("SC", 1000), ("SD", 1), ("SD", 1000)}
    checked = 0
    for name in ("NicknameExport.csv", "NicknameExportTxtSpecials.csv"):
        for record in read_csv(FIXTURES / name).values():
            key = (record.memory_type, record.address)
            if key in user_set or key not in AUTOMATIONDIRECT_SYSTEM_NICKNAMES:
                continue
            assert record.nickname == canonical_system_nickname(*key), (name, key)
            checked += 1
    assert checked > 100


def test_names_missing_from_plctype_ini_keep_the_help_page_source():
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAMES[("SD", 71)].source.endswith("/110.htm")
    assert AUTOMATIONDIRECT_SYSTEM_NICKNAMES[("SD", 21)].source == (
        "CLICK 4.00 PLCType.ini [SYSTEM0]"
    )
