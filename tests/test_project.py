"""Channel parameters use installed hardware, not every DF token in the file."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pyclickplc import (
    Module,
    ModuleIO,
    Modules,
    read_io_layout,
    read_modules,
    read_plc_name,
    write_plc_name,
)
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


# ==============================================================================
# read_plc_name / write_plc_name
# ==============================================================================

# CLICK 4 writes [PLCName] PLCName= as [Sec20] Key1=; Sec21 marks a CLICK 4 file.
CLICK_3 = b"[SystemConfig]\r\nItem1=199\r\n[PLCName]\r\nPLCName=Line 1\r\n[Other]\r\nValue=1\r\n"
CLICK_4 = b"[Sec21]\r\nKey3_1=199\r\n[Sec20]\r\nKey1=Line 1\r\n[Sec22]\r\nKey1_2=\r\n"


def _project(tmp_path, data):
    path = tmp_path / "Project.ini"
    path.write_bytes(data)
    return path


def _write(tmp_path, data, name):
    path = _project(tmp_path, data)
    write_plc_name(path, name)
    assert read_plc_name(path) == name.strip()
    return path.read_bytes()


@pytest.mark.parametrize(
    "data,name",
    [
        (CLICK_3, "Line 1"),
        (CLICK_4, "Line 1"),
        (b"\xef\xbb\xbf" + CLICK_3, "Line 1"),
        (b"[PLCName]\nplcname =  Mixer 2  \n", "Mixer 2"),
        (b"[PLCName]\r\nPLCName=\r\n", None),
        (b"[SystemConfig]\r\nItem1=199\r\n", None),
        (b"", None),
        # Without Sec21 the file uses CLICK 3's names, so Sec20 is not the PLC name.
        (b"[Sec20]\r\nKey1=Line 1\r\n", None),
    ],
)
def test_read_plc_name(tmp_path, data, name):
    assert read_plc_name(_project(tmp_path, data)) == name


def test_read_plc_name_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_plc_name(tmp_path / "missing.ini")
    with pytest.raises(ValueError, match="Invalid CLICK project"):
        read_plc_name(_project(tmp_path, b"not an ini file"))
    with pytest.raises(ValueError, match="Invalid CLICK project"):
        read_plc_name(_project(tmp_path, b"[PLCName]\r\nPLCName=\xff\r\n"))


def test_placeholder_plc_name_leaves_hardware_readers_alone(tmp_path):
    path = _project(tmp_path, CLICK_4)
    write_plc_name(path, "Mixer")
    assert [io.module.model for io in read_io_layout(path)] == ["C2-01CPU-2"]


# A CLICK 4 file that also has the named sections, as another tool may have added them.
# CLICK 4 writes the placeholders, so their values win.
BOTH_NAMES = "\r\n".join(
    [
        "[Sec20]",
        "Key1=Line 1",
        "[PLCName]",
        "PLCName=Other",
        "[Sec21]",
        "Key3_1=241",
        "Key3_2=160",
        "[Sec22]",
        "Key1_2=" + _channels("DF5", "DF6", "DF7", "DF8"),
        "[SystemConfigData]",
        "Item2=" + _channels("DF105", "DF106", "DF107", "DF108"),
        "[Sec23]",
        "Key1=241",
        "Key9=DF1,5,0",
        "Key10=DF2,5,0",
        "Key11=DF3,5,0",
        "Key12=DF4,5,0",
        "[CPUBuild]",
        "ID=241",
        "AD1=DF101,5,0",
        "AD2=DF102,5,0",
        "DA1=DF103,5,0",
        "DA2=DF104,5,0",
        "",
    ]
).encode("ascii")


def test_readers_take_the_placeholder_when_both_sections_exist(tmp_path):
    path = _project(tmp_path, BOTH_NAMES)

    modules = read_modules(path)
    assert (modules.cpu.model, modules.expansions[1].model) == ("C0-02DD1-D", "C0-04AD")
    assert read_channel_parameters(path) == ChannelParameters(
        frozenset({"DF1", "DF2", "DF5", "DF6", "DF7", "DF8"}), frozenset({"DF3", "DF4"})
    )
    cpu, expansion = read_io_layout(path)
    assert (cpu.analog_inputs, cpu.analog_outputs) == (("DF1", "DF2"), ("DF3", "DF4"))
    assert expansion.analog_inputs == ("DF5", "DF6", "DF7", "DF8")
    assert read_plc_name(path) == "Line 1"


def test_write_sets_the_placeholder_when_both_sections_exist(tmp_path):
    assert _write(tmp_path, BOTH_NAMES, "Mixer") == BOTH_NAMES.replace(
        b"Key1=Line 1\r\n", b"Key1=Mixer\r\n"
    )


# As CLICK 4 wrote it, except three long hex values in [Sec55] and [Sec52] are blanked.
CLICK_4_FIXTURE = Path(__file__).parent / "fixtures" / "Project_click4.ini"


def test_click_4_fixture_readers():
    path = CLICK_4_FIXTURE
    assert read_plc_name(path) == "Conformance"
    # [Sec21] Key3_1=198 is the CPU and Key3_10=8194 its slot 0; every other item is 0.
    modules = read_modules(path)
    assert modules.cpu.model == "C2-03CPU"
    assert {p: m.model for p, m in modules.slots.items()} == {0: "C2-14D2"}
    assert dict(modules.expansions) == {}
    assert read_channel_parameters(path) == ChannelParameters()
    cpu, slot = read_io_layout(path)
    assert (cpu.module.model, cpu.inputs, cpu.outputs) == ("C2-03CPU", (), ())
    assert (slot.location, slot.position) == ("slot", 0)
    assert slot.inputs == tuple(f"X{n:03}" for n in range(1, 9))
    assert slot.outputs == tuple(f"Y{n:03}" for n in range(1, 7))


def test_click_4_fixture_write_changes_only_the_name(tmp_path):
    original = CLICK_4_FIXTURE.read_bytes()
    assert original.count(b"Conformance") == 1
    assert original.startswith(b"[Sec20]\r\nKey1=Conformance\r\n")

    assert _write(tmp_path, original, "Mixer 2") == original.replace(b"Conformance", b"Mixer 2")


# A project with no name, as CLICK 4 wrote it, except two long hex values in [Sec55] and
# [Sec52] are blanked. CLICK 4 still writes [Sec20] with an empty Key1=.
CLICK_4_NONAME_FIXTURE = Path(__file__).parent / "fixtures" / "Project_click4_noname.ini"


def test_click_4_noname_fixture_readers():
    path = CLICK_4_NONAME_FIXTURE
    assert read_plc_name(path) is None
    # [Sec21] Key3_1=225 is the CPU; every other item is 0.
    modules = read_modules(path)
    assert modules.cpu.model == "C0-00DD1-D"
    assert (dict(modules.slots), dict(modules.expansions)) == ({}, {})
    assert read_channel_parameters(path) == ChannelParameters()
    (cpu,) = read_io_layout(path)
    assert cpu.inputs == tuple(f"X{n:03}" for n in range(1, 9))
    assert cpu.outputs == tuple(f"Y{n:03}" for n in range(1, 7))


def test_click_4_noname_fixture_write_fills_the_empty_name(tmp_path):
    original = CLICK_4_NONAME_FIXTURE.read_bytes()
    empty = b"\r\n[Sec20]\r\nKey1=\r\n"
    assert original.count(empty) == 1

    assert _write(tmp_path, original, "Mixer 2") == original.replace(
        empty, b"\r\n[Sec20]\r\nKey1=Mixer 2\r\n"
    )


# As CLICK 3 wrote it, except 14 credential-like values in [wsnc], [emsnc] and [rpsnc]
# are blanked.
CLICK_3_FIXTURE = Path(__file__).parent / "fixtures" / "Project_click3.ini"


def test_click_3_fixture_readers():
    path = CLICK_3_FIXTURE
    assert read_plc_name(path) == "V3PLC"
    # [SystemConfig] Item0 to Item11 are all 0: no CPU and no modules.
    assert read_modules(path) == Modules()
    assert read_channel_parameters(path) == ChannelParameters()
    assert read_io_layout(path) == ()


def test_click_3_fixture_write_changes_only_the_name(tmp_path):
    original = CLICK_3_FIXTURE.read_bytes()
    assert original.count(b"V3PLC") == 1
    assert b"\r\n[PLCName]\r\nPLCName=V3PLC\r\n[SystemConfig]\r\n" in original

    assert _write(tmp_path, original, "Mixer 2") == original.replace(b"V3PLC", b"Mixer 2")


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_write_changes_only_the_name_line(tmp_path, bom):
    assert _write(tmp_path, bom + CLICK_3, "Mixer 2") == bom + CLICK_3.replace(
        b"PLCName=Line 1\r\n", b"PLCName=Mixer 2\r\n"
    )


def test_write_click_4_name(tmp_path):
    assert _write(tmp_path, CLICK_4, "Mixer 2") == CLICK_4.replace(
        b"Key1=Line 1\r\n", b"Key1=Mixer 2\r\n"
    )


@pytest.mark.parametrize(
    "line,expected",
    [
        (b"PLCName=\r\n", b"PLCName=Mixer\r\n"),
        (b"plcname = Old  \n", b"plcname = Mixer\n"),
        (b"PLCName: Old\r", b"PLCName: Mixer\r"),
        (b"PLCName=Old", b"PLCName=Mixer"),
    ],
)
def test_write_keeps_the_name_line_as_written(tmp_path, line, expected):
    before = b"[PLCName]\r\n;PLCName=comment\r\nOther=keep\r\n"
    after = b"[Next]\r\nValue=1\r\n" if line.endswith((b"\r", b"\n")) else b""
    assert _write(tmp_path, before + line + after, "Mixer") == before + expected + after


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"[Other]\r\nValue=1\r\n", b"[Other]\r\nValue=1\r\n[PLCName]\r\nPLCName=Mixer\r\n"),
        (b"[Other]\nValue=1", b"[Other]\nValue=1\n[PLCName]\nPLCName=Mixer\n"),
        (b"[Other]\rValue=1\r", b"[Other]\rValue=1\r[PLCName]\rPLCName=Mixer\r"),
        (b"", b"[PLCName]\r\nPLCName=Mixer\r\n"),
        (b"[PLCName]\r\nOther=keep\r\n", b"[PLCName]\r\nPLCName=Mixer\r\nOther=keep\r\n"),
        (b"[A]\r\n[PLCName]", b"[A]\r\n[PLCName]\r\nPLCName=Mixer\r\n"),
        # A CLICK 4 file gets the placeholder name.
        (b"[Sec21]\r\nKey3_1=199\r\n", b"[Sec21]\r\nKey3_1=199\r\n[Sec20]\r\nKey1=Mixer\r\n"),
        (b"[Sec21]\r\n[Sec20]\r\nKey2=x\r\n", b"[Sec21]\r\n[Sec20]\r\nKey1=Mixer\r\nKey2=x\r\n"),
        # A CLICK 4 file that already has [PLCName] keeps the name there, where it is read.
        (b"[Sec21]\r\n[PLCName]\r\nPLCName=A\r\n", b"[Sec21]\r\n[PLCName]\r\nPLCName=Mixer\r\n"),
        # With both sections the name goes where it was read: [Sec20] unless only [PLCName] has it.
        (
            b"[Sec21]\r\n[Sec20]\r\nKey2=x\r\n[PLCName]\r\nPLCName=A\r\n",
            b"[Sec21]\r\n[Sec20]\r\nKey2=x\r\n[PLCName]\r\nPLCName=Mixer\r\n",
        ),
        (
            b"[Sec21]\r\n[Sec20]\r\nKey2=x\r\n[PLCName]\r\n",
            b"[Sec21]\r\n[Sec20]\r\nKey1=Mixer\r\nKey2=x\r\n[PLCName]\r\n",
        ),
    ],
)
def test_write_adds_a_missing_name(tmp_path, data, expected):
    assert _write(tmp_path, data, "Mixer") == expected


def test_write_strips_the_name(tmp_path):
    assert _write(tmp_path, CLICK_3, "  Mixer 2\t") == CLICK_3.replace(b"Line 1", b"Mixer 2")


@pytest.mark.parametrize(
    "data,name,match",
    [
        (CLICK_3, "", "Name is required"),
        (CLICK_3, "A" * 25, "Name is too long"),
        (CLICK_3, "Line/1", "Use only letters"),
        (CLICK_3, "Línea", "Use only letters"),
        (b"not an ini file", "Mixer", "Invalid CLICK project"),
        (b"\xff[PLCName]\r\n", "Mixer", "Invalid CLICK project"),
        # The edited line would not read back as the name alone.
        (b"[PLCName]\r\nPLCName=Old\r\n  more\r\n", "Mixer", "Cannot set the PLC name"),
        # A header that matches the name's section only in case: Windows reads either.
        (b"[plcname]\r\nplcname=Old\r\n", "Mixer", r"\[plcname\] differs from \[PLCName\]"),
        (b"[PLCName]\r\nPLCName=A\r\n[PLCNAME]\r\n", "Mixer", "only in case"),
        (b"[Sec21]\r\n[sec20]\r\nKey1=A\r\n", "Mixer", r"\[sec20\] differs from \[Sec20\]"),
    ],
)
def test_write_refuses_and_leaves_the_file(tmp_path, data, name, match):
    path = _project(tmp_path, data)
    with pytest.raises(ValueError, match=match):
        write_plc_name(path, name)
    assert path.read_bytes() == data
    assert [p.name for p in tmp_path.iterdir()] == ["Project.ini"]


def test_write_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        write_plc_name(tmp_path / "Project.ini", "Mixer")
    assert list(tmp_path.iterdir()) == []


def test_write_through_a_symlink_keeps_the_link(tmp_path):
    target = tmp_path / "target.ini"
    target.write_bytes(CLICK_3)
    link = tmp_path / "Project.ini"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("cannot create symlinks here")

    write_plc_name(link, "Mixer")

    assert link.is_symlink()
    assert target.read_bytes() == CLICK_3.replace(b"Line 1", b"Mixer")


def test_write_replaces_in_one_step(tmp_path, monkeypatch):
    path = _project(tmp_path, CLICK_3)
    replaced = []

    def replace(source, destination):
        replaced.append((Path(source).parent, Path(source).read_bytes(), Path(destination)))
        raise PermissionError("locked")

    monkeypatch.setattr("pyclickplc.project.os.replace", replace)
    with pytest.raises(PermissionError):
        write_plc_name(path, "Mixer")

    assert replaced == [(tmp_path, CLICK_3.replace(b"Line 1", b"Mixer"), path)]
    assert path.read_bytes() == CLICK_3
    assert [p.name for p in tmp_path.iterdir()] == ["Project.ini"]
