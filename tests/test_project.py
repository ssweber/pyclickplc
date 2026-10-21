"""Channel parameters use installed hardware, not every DF token in the file."""

from dataclasses import FrozenInstanceError

import pytest

from pyclickplc import Module, ModuleIO, read_io_layout
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


# ==============================================================================
# read_io_layout
# ==============================================================================


def _layout(tmp_path, text):
    path = tmp_path / "Project.ini"
    path.write_text(text, encoding="utf-8-sig")
    return read_io_layout(path)


def _points(bank, *ranges):
    return tuple(f"{bank}{i:03d}" for lo, hi in ranges for i in range(lo, hi + 1))


def test_layout_standard_cpu_and_sparse_expansions(tmp_path):
    layout = _layout(
        tmp_path,
        "\n".join(
            [
                "[SystemConfig]",
                "Item0=1024",
                "Item1=192",
                "Item2=16",
                "Item3=166",
                "Item4=73",
                "Item9=45",
                "[CPUBuild]",
                "ID=192",
                "AD1=DF1,10,0",
                "AD2=",
                "AD3=DF3,10,0",
                "AD4=DF4,10,0",
                "DA1=DF5,10,0",
                "DA2=DF6,10,0",
                "[SystemConfigData]",
                "Item3=" + _channels("DF21", None, "DF23", "", "DF25", "DF26"),
            ]
        ),
    )
    assert layout == (
        ModuleIO(
            "cpu",
            0,
            Module(192, "C0-12DD1E-2-D", 4, 4, 4, 2),
            _points("X", (1, 4)),
            _points("Y", (1, 4)),
            ("DF1", None, "DF3", "DF4"),
            ("DF5", "DF6"),
        ),
        ModuleIO(
            "expansion",
            1,
            Module(16, "C0-16ND3", 16, 0, 0, 0),
            _points("X", (101, 116)),
            (),
            (),
            (),
        ),
        ModuleIO(
            "expansion",
            2,
            Module(166, "C0-4AD2DA-2", 0, 0, 4, 2),
            (),
            (),
            ("DF21", None, "DF23", None),
            ("DF25", "DF26"),
        ),
        ModuleIO(
            "expansion",
            3,
            Module(73, "C0-16CDD2", 8, 8, 0, 0),
            _points("X", (301, 308)),
            _points("Y", (301, 308)),
            (),
            (),
        ),
        ModuleIO(
            "expansion", 8, Module(45, "C0-08TR", 0, 8, 0, 0), (), _points("Y", (801, 808)), (), ()
        ),
    )


def test_layout_plus_cpu_slots(tmp_path):
    layout = _layout(
        tmp_path,
        "[SystemConfig]\nItem1=199\nItem2=11\nItem10=8193\nItem11=8217\n"
        "[CPUBuild]\nID=199\nAD1=DF1,5,0\n"
        "[SystemConfigData]\nItem11=" + _channels("DF41", "DF42", "DF43", "DF44", "DF45", ""),
    )
    assert [(io.location, io.position, io.module.model) for io in layout] == [
        ("cpu", 0, "C2-01CPU-2"),
        ("slot", 0, "C2-14D1"),
        ("slot", 1, "C2-08D2-6V"),
        ("expansion", 1, "C0-08NE3"),
    ]
    cpu, slot0, slot1, expansion = layout
    assert (cpu.inputs, cpu.outputs, cpu.analog_inputs, cpu.analog_outputs) == ((), (), (), ())
    assert slot0.inputs == _points("X", (1, 8))
    assert slot0.outputs == _points("Y", (1, 6))
    assert slot0.analog_inputs == slot0.analog_outputs == ()
    assert slot1.inputs == _points("X", (21, 24))
    assert slot1.outputs == _points("Y", (21, 24))
    assert slot1.analog_inputs == ("DF41", "DF42", "DF43", "DF44")
    assert slot1.analog_outputs == ("DF45", None)
    assert expansion.inputs == _points("X", (101, 108))


def test_layout_empty_slot_zero_keeps_slot_one_addresses(tmp_path):
    (cpu, slot1) = _layout(tmp_path, "[SystemConfig]\nItem1=200\nItem10=0\nItem11=8195\n")
    assert cpu.module.model == "C2-02CPU-2"
    assert (slot1.location, slot1.position) == ("slot", 1)
    assert slot1.inputs == _points("X", (21, 28))
    assert slot1.outputs == _points("Y", (21, 26))


def test_layout_analog_module_without_assignments(tmp_path):
    (expansion,) = _layout(tmp_path, "[SystemConfig]\nItem2=173\n")
    assert expansion.analog_inputs == (None,) * 16
    assert expansion.analog_outputs == ()


def test_layout_ignores_stale_slots_and_non_analog_channel_data(tmp_path):
    layout = _layout(
        tmp_path,
        "[SystemConfig]\nItem1=209\nItem2=8\nItem10=8219\n"
        "[SystemConfigData]\nItem2=leftover\nItem10=leftover\n",
    )
    assert [(io.location, io.module.model) for io in layout] == [
        ("cpu", "C0-10DD2E-D"),
        ("expansion", "C0-08ND3"),
    ]


def test_layout_agrees_with_channel_parameters(tmp_path):
    text = (
        "[SystemConfig]\nItem1=199\nItem2=165\nItem10=8219\n[CPUBuild]\nAD1=DF1,5,0\n"
        "[SystemConfigData]\nItem2="
        + _channels("DF11", "DF12", None, "DF14", "DF15", "DF16")
        + "\nItem10="
        + _channels("DF31", "DF32", "DF33", "DF34", "DF35", "DF36")
    )
    layout = _layout(tmp_path, text)
    parameters = read_channel_parameters(tmp_path / "Project.ini")
    assert parameters.inputs == {a for io in layout for a in io.analog_inputs if a}
    assert parameters.outputs == {a for io in layout for a in io.analog_outputs if a}


def test_layout_reads_click_4_placeholder_names(tmp_path):
    # CLICK 4 renames the sections and keys; the values are the same module IDs.
    text = "\n".join(
        [
            "[Sec21]",
            "Key1=1",
            "Key3_0=1024",
            "Key3_1=199",
            "Key3_2=42",
            "Key3_10=8219",
            "Key3_11=0",
            "Key4=0",
            "[Sec24]",
            "Key1=199",
            "[Sec23]",
            "Key1=199",
            "Key2=2",
            "Key3_1=1",
            "[Sec22]",
            "Key1_2=",
            "Key1_10=" + _channels("DF5", None, "DF7", "DF9", "DF10", "DF11"),
        ]
    )
    cpu, slot, expansion = _layout(tmp_path, text)

    assert (cpu.module.model, slot.module.model, expansion.module.model) == (
        "C2-01CPU-2",
        "C2-08AR-6V",
        "C0-08TD2",
    )
    assert (slot.position, expansion.position) == (0, 1)
    assert slot.analog_inputs == ("DF5", None, "DF7", "DF9")
    assert slot.analog_outputs == ("DF10", "DF11")


def test_click_4_cpu_analog_channels(tmp_path):
    text = "[Sec21]\nKey3_1=241\n[Sec23]\nKey1=241\nKey9=DF1,5,0\nKey10=DF2,5,0\nKey11=DF3,5,0"

    (cpu,) = _layout(tmp_path, text)

    assert cpu.analog_inputs == ("DF1", "DF2")
    assert cpu.analog_outputs == ("DF3", None)


@pytest.mark.parametrize("text", ["", "[SystemConfig]\nItem1=0\nItem2=0"])
def test_layout_without_modules(tmp_path, text):
    assert _layout(tmp_path, text) == ()


def test_layout_rejects_malformed_channel_data(tmp_path):
    with pytest.raises(ValueError, match="Invalid channel count"):
        _layout(tmp_path, "[SystemConfig]\nItem2=161\n[SystemConfigData]\nItem2=header\tshort")
    with pytest.raises(ValueError, match="Invalid channel address at CPUBuild.AD1"):
        _layout(tmp_path, "[SystemConfig]\nItem1=192\n[CPUBuild]\nAD1=DS1,10,0")


def test_layout_is_immutable(tmp_path):
    (cpu,) = _layout(tmp_path, "[SystemConfig]\nItem1=225\n")
    with pytest.raises(FrozenInstanceError):
        cpu.inputs = ()
