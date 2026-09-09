"""Channel parameters use installed hardware, not every DF token in the file."""

from dataclasses import FrozenInstanceError

import pytest

from pyclickplc.project import ChannelParameters, read_channel_parameters


def _channels(*addresses):
    return (
        "12,1,DF499,1,DF498,6,0,0,0,0,1\t"
        + "\t".join(
            f"3,1,10.0,0.0,100.0,0.0,{address},0.0122085215,0.0000000000,"
            if address is not None
            else ""
            for address in addresses
        )
        + "\t\t"
    )


def _read(tmp_path, text):
    path = tmp_path / "Project.ini"
    path.write_text(text, encoding="utf-8-sig")
    return read_channel_parameters(path)


def test_standard_cpu_and_eighth_expansion(tmp_path):
    result = _read(
        tmp_path,
        "\n".join(
            [
                "[SystemConfig]",
                "Item1=192",
                "Item2=167",
                "Item3=166",
                "Item9=165",
                "[CPUBuild]",
                "ID=192",
                "AD1=DF1,10,0",
                "AD2=DF2,10,0",
                "AD3=DF3,10,0",
                "AD4=DF4,10,0",
                "DA1=DF5,10,0",
                "DA2=DF6,10,0",
                "[SystemConfigData]",
                "Item2=" + _channels("DF11", "DF12", "DF13", "DF14"),
                "Item3=" + _channels("DF21", "DF22", "DF23", "DF24", "DF25", "DF26"),
                "Item9=" + _channels("DF31", "DF32", "DF33", "DF34", "DF35", "DF36"),
            ]
        ),
    )
    assert result.inputs == frozenset(
        f"DF{i}" for i in [1, 2, 3, 4, 11, 12, 13, 14, 21, 22, 23, 24, 31, 32, 33, 34]
    )
    assert result.outputs == frozenset({"DF5", "DF6", "DF25", "DF26", "DF35", "DF36"})


@pytest.mark.parametrize("item", range(2, 12))
def test_every_expansion_and_cpu_slot(tmp_path, item):
    result = _read(
        tmp_path,
        f"[SystemConfig]\nItem1=199\nItem{item}=166\n"
        f"[SystemConfigData]\nItem{item}="
        + _channels("DF31", "DF32", "DF33", "DF34", "DF35", "DF36"),
    )
    assert result == ChannelParameters(
        frozenset({"DF31", "DF32", "DF33", "DF34"}), frozenset({"DF35", "DF36"})
    )


def test_plus_slots_and_stale_cpu_and_expansion_data(tmp_path):
    result = _read(
        tmp_path,
        "[SystemConfig]\nItem1=199\nItem4=0\nItem5=8\nItem10=8219\nItem11=8217\n"
        "[CPUBuild]\nID=199\nAD1=DF1,5,0\nDA1=DF3,5,0\n"
        "[SystemConfigData]\nItem4="
        + _channels("DF11", "DF12", "DF13", "DF14")
        + "\nItem5="
        + _channels("DF11", "DF12", "DF13", "DF14")
        + "\nItem10="
        + _channels("DF31", "DF32", "DF33", "DF34", "DF35", "DF36")
        + "\nItem11="
        + _channels("DF41", "DF42", "DF43", "DF44", "DF45", "DF46"),
    )
    assert result.inputs == frozenset(
        {"DF31", "DF32", "DF33", "DF34", "DF41", "DF42", "DF43", "DF44"}
    )
    assert result.outputs == frozenset({"DF35", "DF36", "DF45", "DF46"})


def test_standard_cpu_ignores_stale_plus_slots(tmp_path):
    result = _read(
        tmp_path,
        "[SystemConfig]\nItem1=209\nItem10=8219\n[CPUBuild]\nAD1=DF1,5,0\n"
        "[SystemConfigData]\nItem10=" + _channels("DF31", "DF32", "DF33", "DF34", "DF35", "DF36"),
    )
    assert result == ChannelParameters()


@pytest.mark.parametrize(
    "module,inputs,outputs",
    [
        (161, 4, 0),
        (163, 0, 4),
        (167, 4, 0),
        (168, 4, 0),
        (169, 8, 0),
        (171, 0, 8),
        (173, 16, 0),
        (175, 0, 16),
        (8208, 2, 2),
        (8219, 4, 2),
    ],
)
def test_module_channel_directions(tmp_path, module, inputs, outputs):
    addresses = [f"DF{i}" for i in range(1, inputs + outputs + 1)]
    result = _read(
        tmp_path,
        f"[SystemConfig]\nItem1=199\nItem10={module}\n[SystemConfigData]\nItem10="
        + _channels(*addresses),
    )
    assert result.inputs == frozenset(addresses[:inputs])
    assert result.outputs == frozenset(addresses[inputs:])


def test_normalizes_deduplicates_and_preserves_empty_channel_positions(tmp_path):
    result = _read(
        tmp_path,
        "[SystemConfig]\nItem1=241\nItem2=165\n[CPUBuild]\nAD1=df001,5,0\nAD2=\nAD3=DF499,5,0\n"
        "[SystemConfigData]\nItem2=" + _channels("df001", None, "", " DF004 ", "df005", "DF006"),
    )
    assert result == ChannelParameters(frozenset({"DF1", "DF4"}), frozenset({"DF5", "DF6"}))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[SystemConfig]\nItem1=199",
        "[SystemConfig]\nItem1=192\nItem2=165\n[SystemConfigData]\nItem2=",
    ],
)
def test_no_assigned_channels(tmp_path, text):
    assert _read(tmp_path, text) == ChannelParameters()


@pytest.mark.parametrize("address", ["DS1", "DF0", "DF1000", "not-an-address"])
def test_invalid_channel_address_raises(tmp_path, address):
    with pytest.raises(ValueError, match="Invalid channel address"):
        _read(tmp_path, f"[SystemConfig]\nItem1=192\n[CPUBuild]\nAD1={address},10,0")


@pytest.mark.parametrize(
    "record", ["header\tshort\t\t\t\t", "header\t", _channels("DF1", "DF2", "DF3", "DF4", "DF5")]
)
def test_malformed_active_channel_data_raises(tmp_path, record):
    with pytest.raises(ValueError, match="Invalid channel"):
        _read(tmp_path, "[SystemConfig]\nItem2=161\n[SystemConfigData]\nItem2=" + record)


def test_unknown_hardware_raises_instead_of_guessing(tmp_path):
    with pytest.raises(ValueError, match="Unsupported module ID 9999"):
        _read(tmp_path, "[SystemConfig]\nItem2=9999")


def test_missing_and_invalid_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_channel_parameters(tmp_path / "missing.ini")
    with pytest.raises(ValueError, match="Invalid CLICK project"):
        _read(tmp_path, "not an ini file")


def test_result_is_immutable():
    with pytest.raises(FrozenInstanceError):
        ChannelParameters().inputs = frozenset({"DF1"})  # ty: ignore[invalid-assignment]
