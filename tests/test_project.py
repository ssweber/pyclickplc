"""Channel parameters use installed hardware, not every DF token in the file."""

import io
import random
from configparser import ConfigParser, DuplicateOptionError, DuplicateSectionError
from configparser import Error as ConfigParserError
from contextlib import suppress
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pyclickplc import (
    Module,
    ModuleIO,
    read_io_layout,
    read_modules,
    read_plc_name,
    write_plc_name,
)
from pyclickplc.project import (
    ChannelParameters,
    _line_roles,
    _lines,
    _parse_project,
    _plc_name,
    _roles,
    read_channel_parameters,
)


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


# CLICK 4 renames the sections and keys; the values are the same module IDs.
CLICK_4_LAYOUT = "\n".join(
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


def test_layout_reads_click_4_placeholder_names(tmp_path):
    cpu, slot, expansion = _layout(tmp_path, CLICK_4_LAYOUT)

    assert (cpu.module.model, slot.module.model, expansion.module.model) == (
        "C2-01CPU-2",
        "C2-08AR-6V",
        "C0-08TD2",
    )
    assert (slot.position, expansion.position) == (0, 1)
    assert slot.analog_inputs == ("DF5", None, "DF7", "DF9")
    assert slot.analog_outputs == ("DF10", "DF11")


# CLICK 4 matches section and key names regardless of case and takes the first match.
# ClickNick's runner saw it for [Sec20] Key1 only; the other sections are inferred.
@pytest.mark.parametrize("spell", [str.lower, str.upper], ids=["lower", "upper"])
def test_readers_find_sections_and_keys_in_any_case(tmp_path, spell):
    lines = []
    for line in CLICK_4_LAYOUT.split("\n"):
        key, delimiter, value = line.partition("=")
        lines.append(spell(key) + delimiter + value)
    canonical, respelled = tmp_path / "canonical.ini", tmp_path / "respelled.ini"
    canonical.write_text(CLICK_4_LAYOUT)
    respelled.write_text("\n".join(lines))
    assert "[Sec21]" not in respelled.read_text()

    assert read_modules(respelled) == read_modules(canonical)
    assert read_io_layout(respelled) == read_io_layout(canonical)
    assert read_channel_parameters(respelled) == read_channel_parameters(canonical)
    assert read_channel_parameters(respelled).inputs == {"DF5", "DF7", "DF9"}


def test_click_3_sections_match_regardless_of_case(tmp_path):
    text = "[systemconfig]\nitem1=241\nITEM2=160\n[CPUBUILD]\nad1=DF1,5,0\n[systemConfigData]\n"
    cpu, expansion = _layout(tmp_path, text + "Item2=" + _channels("DF5", "DF6", "DF7", "DF8"))

    assert (cpu.module.model, expansion.module.model) == ("C0-02DD1-D", "C0-04AD")
    assert cpu.analog_inputs == ("DF1", None)
    assert expansion.analog_inputs == ("DF5", "DF6", "DF7", "DF8")


@pytest.mark.parametrize(
    "text,model",
    [
        ("[sec21]\nKey3_1=241\n[Sec21]\nKey3_1=199", "C0-02DD1-D"),
        ("[Sec21]\nKey3_1=199\n[SEC21]\nKey3_1=241", "C2-01CPU-2"),
        ("[systemconfig]\nItem1=241\n[SystemConfig]\nItem1=199", "C0-02DD1-D"),
        # [Sec23] decides the CPU when [Sec21] doesn't, and its first spelling wins.
        ("[Sec21]\n[sec23]\nKey1=241\n[Sec23]\nKey1=199", "C0-02DD1-D"),
        # The same spelling twice, and a key repeated in any case.
        ("[Sec21]\nKey3_1=241\n[Sec21]\nKey3_1=199", "C0-02DD1-D"),
        ("[SystemConfig]\nItem1=241\n[SystemConfig]\nItem1=199", "C0-02DD1-D"),
        ("[Sec21]\nKey3_1=241\nKey3_1=199", "C0-02DD1-D"),
        ("[Sec21]\nKey3_1=241\nKEY3_1=199", "C0-02DD1-D"),
        ("[Sec21]\n[Sec23]\nKey1=241\nkey1=199", "C0-02DD1-D"),
        # A repeat is not read, so its value is not checked.
        ("[Sec21]\nKey3_1=241\nKey3_1=x", "C0-02DD1-D"),
    ],
)
def test_the_first_section_and_key_in_any_case_win(tmp_path, text, model):
    (cpu,) = _layout(tmp_path, text)
    assert cpu.module.model == model


def test_a_later_section_and_key_are_dropped_whole(tmp_path):
    # The second [Sec21] adds no expansion; the second Key3_1 and the line continuing it
    # are dropped, and the Key3_2 after them is read.
    text = "[Sec21]\nKey3_1=241\nKey3_1=199\n  more\nKey3_2=160\n[sec21]\nKey3_3=160\n"
    cpu, expansion = _layout(tmp_path, text)
    assert (cpu.module.model, expansion.module.model, expansion.position) == (
        "C0-02DD1-D",
        "C0-04AD",
        1,
    )


def test_a_dropped_header_leaves_the_next_indented_header_a_header(tmp_path):
    # "  [Sec22]" follows a header, so it is one; dropping the repeated [sec21] must not put it
    # under Key3_2.
    text = "[Sec21]\nKey3_1=241\nKey3_2=160\n[sec21]\n  [Sec22]\nKey1_2="
    _, expansion = _layout(tmp_path, text + _channels("DF5", "DF6", "DF7", "DF8"))
    assert expansion.analog_inputs == ("DF5", "DF6", "DF7", "DF8")


def test_systemconfig_in_any_case_marks_a_click_3_file(tmp_path):
    # Its [Sec21] and [Sec20] are not CLICK 4's, for the hardware readers and the PLC name alike.
    path = _project(tmp_path, b"[SYSTEMCONFIG]\nItem1=241\n[Sec21]\nKey3_1=199\n[Sec20]\nKey1=A")
    assert [io.module.model for io in read_io_layout(path)] == ["C0-02DD1-D"]
    assert read_plc_name(path) is None


@pytest.mark.parametrize(
    "text,match",
    [
        ("[sec21]\nKey3_1=x", "invalid literal"),
        ("[sec21]\nKey3_1=7", "Unsupported module ID 7"),
        ("[sec21]\nKey3_2=160\n[SEC22]\nKey1_2=header\tshort", "Invalid channel count"),
        ("[sec21]\nKey3_1=241\n[sec23]\nkey9=DS1,5,0", "Invalid channel address at CPUBuild.AD1"),
        # A line that is not INI is refused, even in a section that a repeat drops.
        ("[sec21]\nKey3_1=241\n[Sec21]\nnot an option", "Invalid CLICK project"),
        # So is an option with no name.
        ("[Sec21]\nKey3_1=241\n[sec21]\n=7\n", "Invalid CLICK project"),
        ("[Sec21]\nKey3_1=241\n[sec21]\n:7\n", "Invalid CLICK project"),
        ("[Sec21]\nKey3_1=241\n[sec21]\n  = z\n", "Invalid CLICK project"),
    ],
)
def test_malformed_data_in_any_case_raises(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        _layout(tmp_path, text)


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
CLICK_4_HEAD = b"[Sec21]\r\nKey3_1=199\r\n"
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
    # An option with no name, even in a repeated section that is not read.
    with pytest.raises(ValueError, match="Invalid CLICK project"):
        read_plc_name(_project(tmp_path, CLICK_4_HEAD + b"[Sec20]\r\nKey1=A\r\n[sec20]\r\n=x\r\n"))


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
    assert modules.cpu is not None
    assert (modules.cpu.model, modules.expansions[1].model) == ("C0-02DD1-D", "C0-04AD")
    assert read_channel_parameters(path) == ChannelParameters(
        frozenset({"DF1", "DF2", "DF5", "DF6", "DF7", "DF8"}), frozenset({"DF3", "DF4"})
    )
    cpu, expansion = read_io_layout(path)
    assert (cpu.analog_inputs, cpu.analog_outputs) == (("DF1", "DF2"), ("DF3", "DF4"))
    assert expansion.analog_inputs == ("DF5", "DF6", "DF7", "DF8")
    assert read_plc_name(path) == "Line 1"


@pytest.mark.parametrize("cpubuild", ["CPUBuild", "cpubuild"])
def test_readers_ignore_every_key_of_a_stray_named_section(tmp_path, cpubuild):
    # [Sec23] has no AD2 and [Sec22] no Item2, so a stray section's keys must not fill them.
    text = "\n".join(
        [
            "[Sec21]",
            "Key3_1=241",
            "Key3_2=160",
            "[Sec23]",
            "Key1=241",
            "Key9=DF1,5,0",
            f"[{cpubuild}]",
            "ID=241",
            "AD2=DF102,5,0",
            "DA1=DF103,5,0",
            "[Sec22]",
            "Key1_3=",
            "[SystemConfigData]",
            "Item2=" + _channels("DF105", "DF106", "DF107", "DF108"),
        ]
    )
    cpu, expansion = _layout(tmp_path, text)

    assert (cpu.analog_inputs, cpu.analog_outputs) == (("DF1", None), (None, None))
    assert expansion.analog_inputs == (None, None, None, None)
    assert read_channel_parameters(tmp_path / "Project.ini") == ChannelParameters(
        frozenset({"DF1"}), frozenset()
    )


def test_write_sets_the_placeholder_when_both_sections_exist(tmp_path):
    assert _write(tmp_path, BOTH_NAMES, "Mixer") == BOTH_NAMES.replace(
        b"Key1=Line 1\r\n", b"Key1=Mixer\r\n"
    )


# Project.ini files CLICK wrote, with the name line as CLICK wrote it (empty for a project with
# no name) and the modules [SystemConfig] or [Sec21] lists. Credential-like values are blanked
# in the CLICK 3 files (14 in [wsnc], [emsnc] and [rpsnc]), and long hex values in the CLICK 4
# files ([Sec55] Key1, [Sec52] Key3_1, and Key4_1 in the named one). Every other byte is as
# CLICK wrote it.
CLICK_FIXTURES = [
    pytest.param("Project_click3.ini", b"[PLCName]\r\nPLCName=", "V3PLC", [], id="click3"),
    pytest.param(
        "Project_click3_noname.ini", b"[PLCName]\r\nPLCName=", None, [], id="click3-noname"
    ),
    pytest.param(
        "Project_click4.ini",
        b"[Sec20]\r\nKey1=",
        "Conformance",
        [("cpu", 0, "C2-03CPU"), ("slot", 0, "C2-14D2")],
        id="click4",
    ),
    pytest.param(
        "Project_click4_noname.ini",
        b"[Sec20]\r\nKey1=",
        None,
        [("cpu", 0, "C0-00DD1-D")],
        id="click4-noname",
    ),
]


@pytest.mark.parametrize("filename,name_line,name,layout", CLICK_FIXTURES)
def test_click_fixture_readers(filename, name_line, name, layout):
    path = Path(__file__).parent / "fixtures" / filename
    assert read_plc_name(path) == name
    modules = read_modules(path)
    installed = [modules.cpu, *modules.slots.values(), *modules.expansions.values()]
    assert [module.model for module in installed if module] == [model for *_, model in layout]
    assert read_channel_parameters(path) == ChannelParameters()
    assert [(io.location, io.position, io.module.model) for io in read_io_layout(path)] == layout


@pytest.mark.parametrize("filename,name_line,name,layout", CLICK_FIXTURES)
def test_click_fixture_write_changes_only_the_name(tmp_path, filename, name_line, name, layout):
    original = (Path(__file__).parent / "fixtures" / filename).read_bytes()
    line = name_line + (name or "").encode("ascii") + b"\r\n"
    assert original.count(line) == 1

    # CLICK writes the name line even with no name, so the write fills it in place.
    expected = original.replace(line, name_line + b"Mixer 2\r\n")
    assert _write(tmp_path, original, "Mixer 2") == expected


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


# CLICK 4.00's System Configuration, run on the real program (ClickNick's
# buildbot/jobs/runner-jobs/RESULTS-C.md, section C2, live-p3 to p10 and p12): it shows the
# PLC name from [Sec20] Key1 whatever the case of the section and key, and takes the
# first of two matching sections or two matching keys.
C2_CASES = [
    pytest.param(b"[Sec20]\r\nKey1=UpperCase\r\n", "UpperCase", id="p3-Sec20-Key1"),
    pytest.param(b"[sec20]\r\nkey1=LowerCase\r\n", "LowerCase", id="p4-lower"),
    pytest.param(b"[SEC20]\r\nKEY1=AllCaps\r\n", "AllCaps", id="p5-upper"),
    pytest.param(b"[Sec20]\r\nkey1=MixedKey\r\n", "MixedKey", id="p6-lower-key"),
    pytest.param(b"[sec20]\r\nKey1=MixedSection\r\n", "MixedSection", id="p7-lower-section"),
    pytest.param(
        b"[Sec20]\r\nKey1=Upper\r\n[sec20]\r\nkey1=Lower\r\n", "Upper", id="p8-two-sections"
    ),
    pytest.param(
        b"[sec20]\r\nkey1=Lower\r\n[Sec20]\r\nKey1=Upper\r\n", "Lower", id="p9-two-sections"
    ),
    pytest.param(b"[Sec20]\r\nKey1=FirstKey\r\nKEY1=SecondKey\r\n", "FirstKey", id="p10-two-keys"),
    pytest.param(
        b"[Sec20]\r\nKey1=First\r\n[Sec20]\r\nKey1=Second\r\n", "First", id="same-spelling-twice"
    ),
    # A stray [PLCName] does not outrank [Sec20] (p12).
    pytest.param(
        b"[PLCName]\r\nPLCName=Legacy\r\n[Sec20]\r\nKey1=Placeholder\r\n",
        "Placeholder",
        id="p12-with-PLCName",
    ),
]


@pytest.mark.parametrize("data,name", C2_CASES)
def test_read_plc_name_matches_click_4_case_rules(tmp_path, data, name):
    assert read_plc_name(_project(tmp_path, CLICK_4_HEAD + data)) == name


@pytest.mark.parametrize("data,name", C2_CASES)
def test_write_plc_name_changes_the_name_click_4_reads(tmp_path, data, name):
    original = CLICK_4_HEAD + data
    expected = original.replace(b"=" + name.encode(), b"=Mixer", 1)
    assert expected != original
    assert _write(tmp_path, original, "Mixer") == expected


def test_write_keeps_the_files_spelling_when_adding_a_key(tmp_path):
    before = CLICK_4_HEAD + b"[SEC20]\r\nKey2=x\r\n"
    assert (
        _write(tmp_path, before, "Mixer") == CLICK_4_HEAD + b"[SEC20]\r\nKey1=Mixer\r\nKey2=x\r\n"
    )


# configparser reads a line indented under an option as part of the option's value; Windows'
# INI functions likely trim the indent and read a line of its own (inferred). Reads follow
# configparser, and a write to such a file is refused. CLICK writes no such line.
def _refused(tmp_path, data, line):
    path = _project(tmp_path, data)
    with pytest.raises(ValueError, match=f"line {line} is indented under the line above it, "):
        write_plc_name(path, "Mixer")
    assert path.read_bytes() == data


def test_a_continuation_line_is_not_an_option(tmp_path):
    data = CLICK_4_HEAD + b"[Sec20]\r\nOther=a\r\n   Key1=b\r\nKey1=Real\r\n"
    assert read_plc_name(_project(tmp_path, data)) == "Real"
    _refused(tmp_path, data, 5)


CONTINUED_HEADERS = [
    # "  [Next]" continues Key2, so Key1 is still in [Sec20].
    pytest.param(CLICK_4_HEAD + b"[Sec20]\r\nKey2=x\r\n  [Next]\r\nKey1=Real\r\n", "Real", 5),
    # "  [Sec20]" continues [Other]'s A, so the file has no [Sec20] and no name.
    pytest.param(CLICK_4_HEAD + b"[Other]\r\nA=1\r\n  [Sec20]\r\nKey1=Old\r\n", None, 5),
    # A comment or blank line between keeps it under the option.
    pytest.param(CLICK_4_HEAD + b"[Sec20]\r\nKey1=A\r\nKey2=x\r\n;c\r\n\r\n\t[Next]\r\n", "A", 8),
]


@pytest.mark.parametrize("data,name,line", CONTINUED_HEADERS)
def test_an_indented_header_under_an_option_continues_it(tmp_path, data, name, line):
    assert read_plc_name(_project(tmp_path, data)) == name
    _refused(tmp_path, data, line)


def test_an_indented_header_after_a_header_is_a_header(tmp_path):
    # No option comes before it, so configparser reads a section header, as Windows' INI
    # functions likely do (inferred).
    data = CLICK_4_HEAD + b"[Other]\r\n  [Sec20]\r\nKey1=Old\r\n"
    assert read_plc_name(_project(tmp_path, data)) == "Old"
    assert _write(tmp_path, data, "Mixer") == data.replace(b"=Old", b"=Mixer")


def test_the_click_4_marker_matches_regardless_of_case(tmp_path):
    data = b"[sec21]\r\nKey3_1=199\r\n[sec20]\r\nKey1=A\r\n"
    assert read_plc_name(_project(tmp_path, data)) == "A"
    assert _write(tmp_path, data, "Mixer") == data.replace(b"=A", b"=Mixer")
    # [SYSTEMCONFIG] marks a CLICK 3 file, where [Sec20] is not the name.
    assert read_plc_name(_project(tmp_path, b"[SYSTEMCONFIG]\r\n" + data)) is None


def test_only_the_first_matching_section_is_searched_for_the_key(tmp_path):
    # Inferred from Windows' INI functions, not tested in CLICK.
    data = CLICK_4_HEAD + b"[Sec20]\r\nKey2=x\r\n[sec20]\r\nKey1=A\r\n"
    assert read_plc_name(_project(tmp_path, data)) is None


def test_click_4_with_only_plcname_reads_it(tmp_path):
    # C2 p11: CLICK 4.00 shows no name for [PLCName] alone. pyclickplc reads it, as a
    # CLICK 3 file has the name there.
    data = CLICK_4_HEAD + b"[PLCName]\r\nPLCName=Legacy\r\n"
    assert read_plc_name(_project(tmp_path, data)) == "Legacy"


def test_read_and_write_match_case_in_a_click_3_file(tmp_path):
    data = b"[plcname]\r\nPLCNAME=Old\r\n"
    assert read_plc_name(_project(tmp_path, data)) == "Old"
    assert _write(tmp_path, data, "Mixer") == b"[plcname]\r\nPLCNAME=Mixer\r\n"


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
        # The name's value goes on to a second line.
        (b"[PLCName]\r\nPLCName=Old\r\n  more\r\n", "Mixer", "line 3 is indented under the"),
        # An option with no name is malformed, even in a repeated section that is not read.
        (CLICK_4_HEAD + b"[Sec20]\r\nKey1=A\r\n[sec20]\r\n=x\r\n", "Mixer", "Invalid CLICK"),
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


# ==============================================================================
# The line reading against configparser
# ==============================================================================
#
# pyclickplc classes each line itself (_roles) to take the first of repeated sections and keys
# and to find the PLC name's line. These checks compare it with configparser on random files.


class _HeaderRecorder:
    """A SECTCRE stand-in that records every line configparser tries as a section header.

    configparser tries every line that is not blank, a comment or a continuation, so the
    lines it never tries are its continuations. SECTCRE is documented for overriding.
    """

    def __init__(self):
        self.tried = []

    def match(self, value):
        self.tried.append(value)
        return ConfigParser.SECTCRE.match(value)


def _configparser_roles(lines):
    """Each line's role and lowercase name, as configparser reads the file."""
    parser = ConfigParser(interpolation=None, strict=False)
    recorder = parser.SECTCRE = _HeaderRecorder()  # ty: ignore[invalid-assignment]
    with suppress(ConfigParserError):  # A parsing error is raised after every line is read.
        parser.read_file(lines)
    tried = set(recorder.tried)
    assert len(tried) == len(recorder.tried), "the lines tried must be unique"
    roles = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            roles.append(("blank", ""))
        elif stripped not in tried:
            roles.append(("continuation", ""))
        elif (match := ConfigParser.SECTCRE.match(stripped)) is not None:
            roles.append(("section", match["header"].lower()))
        else:
            # Whether a tried line is an option depends on the line alone.
            alone = ConfigParser(interpolation=None)
            try:
                alone.read_string("[s]\n" + stripped)
            except ConfigParserError:
                roles.append(("other", ""))
            else:
                roles.append(("option", alone.options("s")[0]))
    return roles


def _first_wins(lines, roles):
    """The sections and values with the first of each repeat, from configparser's roles."""
    if any(role == "other" for role, _ in roles):
        return None
    sections = {}
    current = None
    for index, (role, name) in enumerate(roles):
        if role == "section":
            current = None if name in sections else sections.setdefault(name, {})
        elif role == "option" and current is not None and name not in current:
            end = index + 1
            while end < len(roles) and roles[end][0] in ("continuation", "blank"):
                end += 1
            alone = ConfigParser(interpolation=None)
            alone.read_string("[s]\n" + "".join(lines[index:end]))
            current[name] = alone.get("s", name)
    return sections


def _sections(parser):
    return {section.lower(): dict(parser.items(section, raw=True)) for section in parser.sections()}


def _random_project(rng):
    """A CLICK 4 file of a few lines. Each line that is not blank is unique, so the lines
    configparser tries can be told apart."""
    lines = ["[Sec21]"]
    for number in range(rng.randint(1, 9)):
        indent = rng.choice(["", "", "", " ", "  ", "\t"])
        kind = rng.random()
        if kind < 0.25:
            line = rng.choice(["[Sec20]", "[sec20]", "[SEC20]", "[A]", "[a]"]) + f" h{number}"
        elif kind < 0.7:
            names = ["Key1=", "KEY1 = ", "key1:", "Key2=", "k=", "=", ":", " = ", "[x]="]
            line = rng.choice(names) + f"v{number}"
        elif kind < 0.8:
            line = rng.choice(["junk", "[", "[]"]) + str(number)
        else:
            line = rng.choice(["", " ", ";c", "#c"])
        lines.append(indent + line)
    return "".join(line + rng.choice(["\n", "\r\n", "\r"]) for line in lines)


def test_line_reading_matches_configparser(tmp_path):
    rng = random.Random(0)
    path = tmp_path / "Project.ini"
    for number in range(2000):
        text = _random_project(rng)
        data = text.encode()
        lines = io.StringIO(text, newline=None).readlines()
        roles = _configparser_roles(lines)

        # Each line is classed as configparser reads it, from text and from bytes.
        assert _roles(lines) == roles, text
        assert _line_roles(_lines(data)[1]) == roles, text

        # The first of each repeat is read, and a file configparser refuses is refused.
        expected = _first_wins(lines, roles)
        try:
            actual = _sections(_parse_project(data, path, restore=False))
        except ValueError:
            actual = None
        assert actual == expected, text

        # Without repeats, configparser's own reading is unchanged.
        plain = ConfigParser(interpolation=None)
        try:
            plain.read_file(lines)
        except (DuplicateSectionError, DuplicateOptionError):
            pass
        except ConfigParserError:
            assert actual is None, text
        else:
            if len(_sections(plain)) == len(plain.sections()):
                assert actual == _sections(plain), text

        # read_plc_name gives configparser's first [Sec20] Key1. Its body is called on the
        # bytes, as opening thousands of files is slow on Windows.
        if expected is None:
            continue
        value = expected.get("sec20", {}).get("key1")
        name = _plc_name(_lines(data)[1], _parse_project(data, path, restore=False))
        assert name == (value.strip() or None if value is not None else None), text

        # write_plc_name refuses a continuation line, and otherwise sets the name read back.
        if number % 8:
            continue
        path.write_bytes(data)
        assert read_plc_name(path) == name
        if any(role == "continuation" for role, _ in roles):
            with pytest.raises(ValueError, match="is indented under the line above it"):
                write_plc_name(path, "Mixer")
            continue
        try:
            write_plc_name(path, "Mixer")
        except ValueError:
            # A line added at the margin can put an indented line after it under it; the
            # check after the edit refuses that, and the file is unchanged.
            indented = [
                line
                for line, (role, _) in zip(lines, roles, strict=True)
                if role in ("section", "option") and line[:1].isspace()
            ]
            assert indented and path.read_bytes() == data, text
            continue
        after = io.StringIO(path.read_bytes().decode(), newline=None).readlines()
        assert _first_wins(after, _configparser_roles(after))["sec20"]["key1"] == "Mixer", text
