"""Installed hardware uses CLICK positions and preserves unknown I/O counts."""

from dataclasses import FrozenInstanceError

import pytest

from pyclickplc import Module, Modules, read_modules
from pyclickplc.project import ChannelParameters, read_channel_parameters


def _project(tmp_path, text):
    path = tmp_path / "Project.ini"
    path.write_text(text, encoding="utf-8-sig")
    return path


def test_standard_cpu_and_sparse_expansions(tmp_path):
    modules = read_modules(
        _project(
            tmp_path,
            "[SystemConfig]\nItem0=1024\nItem1=192\nItem2=167\nItem3=166\n"
            "Item4=8\nItem9=165\nItem10=8219\nItem11=8217\n",
        )
    )
    assert modules.cpu == Module(192, "C0-12DD1E-2-D", 4, 4, 4, 2)
    assert set(modules.expansions) == {1, 2, 3, 8}
    assert modules.expansions[1] == Module(167, "C0-04THM", 0, 0, 4, 0)
    assert modules.expansions[2] == Module(166, "C0-4AD2DA-2", 0, 0, 4, 2)
    assert modules.expansions[3] == Module(8, "C0-08ND3", 8, 0, 0, 0)
    assert modules.expansions[8] == Module(165, "C0-4AD2DA-1", 0, 0, 4, 2)
    assert not modules.slots


def test_plus_cpu_slots_keep_zero_based_numbering(tmp_path):
    modules = read_modules(
        _project(tmp_path, "[SystemConfig]\nItem1=199\nItem2=16\nItem10=8219\nItem11=8217\n")
    )
    assert modules.cpu == Module(199, "C2-01CPU-2", 0, 0, 0, 0)
    assert modules.slots[0] == Module(8219, "C2-08AR-6V", 4, 4, 4, 2)
    assert modules.slots[1] == Module(8217, "C2-08D2-6V", 4, 4, 4, 2)
    assert modules.expansions[1].discrete_inputs == 16


@pytest.mark.parametrize("position", range(1, 9))
def test_each_expansion_position_is_preserved(tmp_path, position):
    modules = read_modules(
        _project(tmp_path, f"[SystemConfig]\nItem1=199\nItem{position + 1}=50\n")
    )
    assert dict(modules.expansions) == {position: Module(50, "C0-16TD2", 0, 16, 0, 0)}


def test_empty_slot_zero_does_not_renumber_slot_one(tmp_path):
    modules = read_modules(_project(tmp_path, "[SystemConfig]\nItem1=199\nItem10=0\nItem11=8193\n"))
    assert dict(modules.slots) == {1: Module(8193, "C2-14D1", 8, 6, 0, 0)}


@pytest.mark.parametrize("cpu_id", [196, 197, 198])
def test_single_slot_cpu_ignores_stale_slot_one(tmp_path, cpu_id):
    path = _project(
        tmp_path,
        f"[SystemConfig]\nItem1={cpu_id}\nItem10=8193\nItem11=9999\n"
        "[SystemConfigData]\nItem11=invalid leftover channel data\n",
    )
    assert set(read_modules(path).slots) == {0}
    assert read_channel_parameters(path) == ChannelParameters()


@pytest.mark.parametrize(
    "model,di,do,ai,ao",
    [
        (225, 8, 6, 0, 0),
        (241, 4, 4, 2, 2),
        (244, 4, 4, 2, 2),
        (216, 4, 4, 2, 2),
        (220, 4, 4, 4, 2),
    ],
)
def test_cpu_io_counts(tmp_path, model, di, do, ai, ao):
    module = read_modules(_project(tmp_path, f"[SystemConfig]\nItem1={model}")).cpu
    assert module is not None
    assert (
        module.discrete_inputs,
        module.discrete_outputs,
        module.analog_inputs,
        module.analog_outputs,
    ) == (di, do, ai, ao)


@pytest.mark.parametrize(
    "model,di,do,ai,ao",
    [
        (41, 0, 8, 0, 0),
        (44, 0, 8, 0, 0),
        (66, 4, 4, 0, 0),
        (73, 8, 8, 0, 0),
        (163, 0, 0, 0, 4),
        (173, 0, 0, 16, 0),
        (8208, 4, 4, 2, 2),
        (8224, 0, 0, 0, 0),
    ],
)
def test_module_io_counts(tmp_path, model, di, do, ai, ao):
    module = read_modules(_project(tmp_path, f"[SystemConfig]\nItem2={model}")).expansions[1]
    assert (
        module.discrete_inputs,
        module.discrete_outputs,
        module.analog_inputs,
        module.analog_outputs,
    ) == (di, do, ai, ao)


def test_result_is_deeply_immutable(tmp_path):
    modules = read_modules(_project(tmp_path, "[SystemConfig]\nItem1=199\nItem10=8193\nItem2=8"))
    with pytest.raises(FrozenInstanceError):
        modules.cpu = None  # ty: ignore[invalid-assignment]
    with pytest.raises(FrozenInstanceError):
        modules.slots[0].model = "changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        modules.slots[1] = modules.slots[0]  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        modules.expansions[2] = modules.expansions[1]  # ty: ignore[invalid-assignment]
    original = {0: modules.slots[0]}
    copied = Modules(slots=original)
    original.clear()
    assert copied.slots == modules.slots


def test_read_modules_does_not_require_valid_channel_parameters(tmp_path):
    path = _project(
        tmp_path,
        "[SystemConfig]\nItem1=199\nItem2=165\n[SystemConfigData]\nItem2=broken channel data",
    )
    assert read_modules(path).expansions[1].analog_inputs == 4
    with pytest.raises(ValueError, match="Invalid channel count"):
        read_channel_parameters(path)


@pytest.mark.parametrize("text", ["", "[SystemConfig]\nItem1=0\nItem2=0\nItem10=0"])
def test_no_modules(tmp_path, text):
    assert read_modules(_project(tmp_path, text)) == Modules()


def test_cpu_fallback_and_authoritative_selection(tmp_path):
    cpu = read_modules(_project(tmp_path, "[CPUBuild]\nID=199")).cpu
    assert cpu is not None
    assert cpu.module_id == 199
    path = _project(tmp_path, "[SystemConfig]\nItem1=0\n[CPUBuild]\nID=invalid")
    assert read_modules(path) == Modules()
    assert read_channel_parameters(path) == ChannelParameters()


@pytest.mark.parametrize("item", [1, 2, 9, 10, 11])
@pytest.mark.parametrize("bad_id", ["invalid", "-1", "9999"])
def test_bad_installed_module_ids_fail_in_both_readers(tmp_path, item, bad_id):
    prefix = "[SystemConfig]\n" + ("Item1=199\n" if item != 1 else "")
    path = _project(tmp_path, prefix + f"Item{item}={bad_id}")
    for read in (read_modules, read_channel_parameters):
        with pytest.raises(ValueError):
            read(path)


def test_file_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_modules(tmp_path / "missing.ini")
    with pytest.raises(ValueError, match="Invalid CLICK project"):
        read_modules(_project(tmp_path, "not an ini file"))
