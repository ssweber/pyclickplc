"""Tests for plcdata — Click PLC 'Read Data from PLC' CSV parser."""

from __future__ import annotations

import math
import struct
from fractions import Fraction
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from pyclickplc.plcdata import _SECTION_ORDER, read_plc_data, write_plc_data


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "data.csv"
    p.write_text(dedent(text).lstrip())
    return p


# ── Bit banks (X, Y, C, T, CT) ──────────────────────────────────────


class TestBitBanks:
    def test_x_sparse_first_slot(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <X=START>
            Address,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,
            X1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
            </X=END>
            """,
        )
        data = read_plc_data(p)
        assert data["X001"] is True
        assert data["X002"] is True
        assert data["X003"] is False
        assert data["X016"] is False
        assert data["X021"] is False
        assert data["X036"] is False

    def test_x_sparse_expansion_slot(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <X=START>
            Address,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,
            X101,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
            </X=END>
            """,
        )
        data = read_plc_data(p)
        assert data["X101"] is False
        assert data["X102"] is True

    def test_y_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <Y=START>
            Address,1,2,3,4,
            Y1,0,0,1,0,
            </Y=END>
            """,
        )
        data = read_plc_data(p)
        assert data["Y003"] is True
        assert data["Y001"] is False

    def test_c_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <C=START>
            Address,1,2,3,
            C1,1,1,0,
            </C=END>
            """,
        )
        data = read_plc_data(p)
        assert data["C1"] is True
        assert data["C2"] is True
        assert data["C3"] is False

    def test_t_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <T=START>
            Address,1,2,3,
            T1,1,0,1,
            </T=END>
            """,
        )
        data = read_plc_data(p)
        assert data["T1"] is True
        assert data["T2"] is False
        assert data["T3"] is True

    def test_ct_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <CT=START>
            Address,1,2,
            CT1,0,1,
            </CT=END>
            """,
        )
        data = read_plc_data(p)
        assert data["CT1"] is False
        assert data["CT2"] is True


# ── Integer banks (DS, TD, DD, CTD) ─────────────────────────────────


class TestIntBanks:
    def test_ds_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DS=START>
            Address,1,2,3,
            DS1,0,0,42,
            </DS=END>
            """,
        )
        data = read_plc_data(p)
        assert data["DS1"] == 0
        assert data["DS3"] == 42

    def test_ds_multiple_rows(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DS=START>
            Address,1,2,
            DS1,10,20,
            DS11,30,40,
            </DS=END>
            """,
        )
        data = read_plc_data(p)
        assert data["DS1"] == 10
        assert data["DS2"] == 20
        assert data["DS11"] == 30
        assert data["DS12"] == 40

    def test_td_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <TD=START>
            Address,1,2,3,
            TD1,6,364,21874,
            </TD=END>
            """,
        )
        data = read_plc_data(p)
        assert data["TD1"] == 6
        assert data["TD2"] == 364
        assert data["TD3"] == 21874

    def test_dd_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DD=START>
            Address,1,2,
            DD1,100000,200000,
            </DD=END>
            """,
        )
        data = read_plc_data(p)
        assert data["DD1"] == 100000
        assert data["DD2"] == 200000

    def test_ctd_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <CTD=START>
            Address,1,2,
            CTD1,99,0,
            </CTD=END>
            """,
        )
        data = read_plc_data(p)
        assert data["CTD1"] == 99
        assert data["CTD2"] == 0


# ── Hex bank (DH) ───────────────────────────────────────────────────


class TestHexBank:
    def test_dh_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DH=START>
            Address,1,2,3,
            DH1,37f,37e,0,
            </DH=END>
            """,
        )
        data = read_plc_data(p)
        assert data["DH1"] == 0x37F
        assert data["DH2"] == 0x37E
        assert data["DH3"] == 0


# ── Float bank (DF) ─────────────────────────────────────────────────


class TestFloatBank:
    def test_df_bank(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DF=START>
            Address,1,2,
            DF1,0.00000000,63.50000000,
            </DF=END>
            """,
        )
        data = read_plc_data(p)
        assert data["DF1"] == 0.0
        assert data["DF2"] == pytest.approx(63.5)


# ── Text bank (TXT) ─────────────────────────────────────────────────


class TestTxtBank:
    def test_txt_empty(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <TXT=START>
            Address,1,2,3,
            TXT1,,,,
            </TXT=END>
            """,
        )
        data = read_plc_data(p)
        assert data["TXT1"] == ""
        assert data["TXT2"] == ""
        assert data["TXT3"] == ""

    def test_txt_with_values(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <TXT=START>
            Address,1,2,3,
            TXT1,H,i,,
            </TXT=END>
            """,
        )
        data = read_plc_data(p)
        assert data["TXT1"] == "H"
        assert data["TXT2"] == "i"
        assert data["TXT3"] == ""


# ── skip_default ─────────────────────────────────────────────────────


class TestSkipDefault:
    def test_skips_false_bits(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <C=START>
            Address,1,2,3,
            C1,1,0,1,
            </C=END>
            """,
        )
        data = read_plc_data(p, skip_default=True)
        assert data == {"C1": True, "C3": True}

    def test_skips_zero_ints(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DS=START>
            Address,1,2,3,
            DS1,0,42,0,
            </DS=END>
            """,
        )
        data = read_plc_data(p, skip_default=True)
        assert data == {"DS2": 42}

    def test_skips_zero_hex(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DH=START>
            Address,1,2,
            DH1,0,ff,
            </DH=END>
            """,
        )
        data = read_plc_data(p, skip_default=True)
        assert data == {"DH2": 0xFF}

    def test_skips_zero_floats(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DF=START>
            Address,1,2,
            DF1,0.00000000,3.14000000,
            </DF=END>
            """,
        )
        data = read_plc_data(p, skip_default=True)
        assert data == {"DF2": pytest.approx(3.14)}

    def test_skips_empty_txt(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <TXT=START>
            Address,1,2,
            TXT1,,A,
            </TXT=END>
            """,
        )
        data = read_plc_data(p, skip_default=True)
        assert data == {"TXT2": "A"}


# ── Multi-section ────────────────────────────────────────────────────


class TestMultiSection:
    def test_multiple_banks(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <C=START>
            Address,1,2,
            C1,1,0,
            </C=END>

            <DS=START>
            Address,1,2,
            DS1,7,8,
            </DS=END>
            """,
        )
        data = read_plc_data(p)
        assert data["C1"] is True
        assert data["C2"] is False
        assert data["DS1"] == 7
        assert data["DS2"] == 8

    def test_unknown_bank_ignored(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <FAKE=START>
            Address,1,2,
            FAKE1,9,9,
            </FAKE=END>

            <C=START>
            Address,1,
            C1,1,
            </C=END>
            """,
        )
        data = read_plc_data(p)
        assert "FAKE1" not in data
        assert data["C1"] is True


# ── write_plc_data ───────────────────────────────────────────────────


class TestWriteBasic:
    def test_write_single_bit_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"C1": True, "C3": True}, banks=["C"])
        data = read_plc_data(out)
        assert data["C1"] is True
        assert data["C2"] is False
        assert data["C3"] is True

    def test_write_ds_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DS1": 10, "DS22": 4}, banks=["DS"])
        data = read_plc_data(out)
        assert data["DS1"] == 10
        assert data["DS2"] == 0
        assert data["DS22"] == 4

    def test_write_dh_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DH1": 0x37F, "DH5": 0xFF}, banks=["DH"])
        data = read_plc_data(out)
        assert data["DH1"] == 0x37F
        assert data["DH5"] == 0xFF
        assert data["DH2"] == 0

    def test_write_df_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DF11": 63.5}, banks=["DF"])
        data = read_plc_data(out)
        assert data["DF11"] == pytest.approx(63.5)
        assert data["DF1"] == 0.0

    def test_write_txt_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"TXT1": "H", "TXT2": "i"}, banks=["TXT"])
        data = read_plc_data(out)
        assert data["TXT1"] == "H"
        assert data["TXT2"] == "i"
        assert data["TXT3"] == ""

    def test_write_dd_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DD1": 100000}, banks=["DD"])
        data = read_plc_data(out)
        assert data["DD1"] == 100000

    def test_write_ctd_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"CTD1": 99}, banks=["CTD"])
        data = read_plc_data(out)
        assert data["CTD1"] == 99


class TestWriteXY:
    def test_write_x_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"X001": True, "X002": True, "X021": True}, banks=["X"])
        data = read_plc_data(out)
        assert data["X001"] is True
        assert data["X002"] is True
        assert data["X003"] is False
        assert data["X021"] is True
        assert data["X101"] is False

    def test_write_y_bank(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"Y003": True}, banks=["Y"])
        data = read_plc_data(out)
        assert data["Y003"] is True
        assert data["Y001"] is False


class TestWriteInferBanks:
    def test_infers_banks_from_data(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"C1": True, "DS5": 42})
        text = out.read_text()
        assert "<C=START>" in text
        assert "<DS=START>" in text
        # Banks not in data should not appear
        assert "<X=START>" not in text
        assert "<DH=START>" not in text

    def test_inferred_order_matches_canonical(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        # Provide data in non-canonical order
        write_plc_data(out, {"DS1": 1, "C1": True, "X001": True})
        text = out.read_text()
        x_pos = text.index("<X=START>")
        c_pos = text.index("<C=START>")
        ds_pos = text.index("<DS=START>")
        assert x_pos < c_pos < ds_pos

    def test_skips_keys_that_are_not_click_addresses(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DS1": 1, "DH١": 2, "DF1u": 3.0, "FAKE1": 4})
        text = out.read_text()
        assert "<DS=START>" in text
        assert "<DH=START>" not in text
        assert "<DF=START>" not in text


class TestReadAddresses:
    def test_row_label_that_is_not_a_click_address_is_skipped(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <DS=START>
            Address,1,2,
            DS0,7,8,
            DS1u,5,6,
            DS11,3,4,
            </DS=END>
            """,
        )
        assert read_plc_data(p) == {"DS11": 3, "DS12": 4}

    def test_header_columns_past_the_bank_take_no_cell(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <X=START>
            Address,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,
            X801,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,
            </X=END>

            <DS=START>
            Address,1,2,3,
            DS4499,1,2,
            </DS=END>
            """,
        )
        data = read_plc_data(p)
        assert data["X816"] is True
        assert "X817" not in data
        assert data["DS4500"] == 2
        assert "DS4501" not in data

    @pytest.mark.parametrize(
        ("rows", "message"),
        [
            ("<X=START>\nAddress,1,2,17,\nX801,0,0,1,\n", r"^X801 row has 3 cells, not 2\.$"),
            ("<DS=START>\nAddress,1,2,3,\nDS1,7,8,\n", r"^DS1 row has 2 cells, not 3\.$"),
            ("<TXT=START>\nAddress,1,2,3,\nTXT11,A,B,\n", r"^TXT11 row has 2 cells, not 3\.$"),
        ],
    )
    def test_row_whose_cells_do_not_match_its_addresses_raises(
        self, tmp_path: Path, rows: str, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            read_plc_data(_write(tmp_path, rows))


class TestWriteMultipleBanks:
    def test_explicit_bank_list(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"DS1": 7}, banks=["DS", "DF"])
        text = out.read_text()
        assert "<DS=START>" in text
        assert "<DF=START>" in text
        data = read_plc_data(out)
        assert data["DS1"] == 7
        assert data["DF1"] == 0.0

    def test_all_banks(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {}, banks=_SECTION_ORDER)
        text = out.read_text()
        for bank in _SECTION_ORDER:
            assert f"<{bank}=START>" in text


class TestRoundTrip:
    def test_round_trip_sparse(self, tmp_path: Path) -> None:
        original = {
            "C1": True,
            "C2": True,
            "DS3": 1,
            "DS21": 1,
            "DS22": 4,
            "DH1": 0x37F,
            "DF11": 63.5,
            "TD1": 6,
            "X001": True,
            "X002": True,
        }
        out = tmp_path / "out.csv"
        write_plc_data(out, original)
        reread = read_plc_data(out, skip_default=True)
        for addr, val in original.items():
            if isinstance(val, float):
                assert reread[addr] == pytest.approx(val), addr
            else:
                assert reread[addr] == val, addr

    def test_round_trip_all_banks(self, tmp_path: Path) -> None:
        """Write all banks, read back, verify every non-default value survives."""
        original = {
            "X001": True,
            "X002": True,
            "Y003": True,
            "C1": True,
            "C2": True,
            "T1": True,
            "T14": True,
            "CT2": True,
            "DS3": 1,
            "DS21": 1,
            "DS22": 4,
            "DS101": 1,
            "DS121": 3139,
            "DS123": 233,
            "DS124": 300,
            "DD1": 100000,
            "DH1": 0x37F,
            "DH2": 0x37E,
            "DH51": 1,
            "DH52": 0x37A,
            "DF11": 63.5,
            "TD1": 6,
            "TD2": 364,
            "TD3": 21874,
            "TD14": 6,
            "CTD1": 99,
            "TXT1": "H",
            "TXT2": "i",
        }
        out = tmp_path / "full.csv"
        write_plc_data(out, original, banks=_SECTION_ORDER)
        reread = read_plc_data(out, skip_default=True)
        for addr, val in original.items():
            if isinstance(val, float):
                assert reread[addr] == pytest.approx(val), addr
            else:
                assert reread[addr] == val, addr
        # Defaults should have been stripped by skip_default
        assert "X003" not in reread
        assert "DS1" not in reread


# ── A dump CLICK wrote ───────────────────────────────────────────────

CLICK_DUMP = Path(__file__).parent / "fixtures" / "PlcDataDump.csv"


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _first_cell(tmp_path: Path, data: dict[str, bool | int | float | str], bank: str) -> str:
    """Write *data* as a one-bank file and return the first cell of its first data row."""
    out = tmp_path / "out.csv"
    write_plc_data(out, data, banks=[bank])
    return out.read_bytes().decode("ascii").split("\r\n")[2].split(",")[1]


class TestClickDump:
    def test_reads_err_format_as_nan(self) -> None:
        data = read_plc_data(CLICK_DUMP)
        nan = {a for a, v in data.items() if isinstance(v, float) and math.isnan(v)}
        assert len(nan) == 46
        assert {"DF31", "DF32", "DF42", "DF43", "DF122", "DF498"} <= nan

    def test_reads_escaped_txt(self) -> None:
        data = read_plc_data(CLICK_DUMP)
        assert data["TXT12"] == " "
        assert data["TXT64"] == "\r"
        assert data["TXT95"] == "\xc8"
        assert data["TXT833"] == " "
        assert data["TXT81"] == "H"
        assert data["TXT13"] == ""

    def test_reads_large_df_values(self) -> None:
        data = read_plc_data(CLICK_DUMP)
        assert data["DF40"] == _float32(3e38)
        assert data["DF482"] == _float32(3e37)
        assert data["DF82"] == _float32(1e30)
        assert data["DF84"] == _float32(-1e30)
        assert data["DF26"] == 123456.703125

    def test_xy_expansion_rows_hold_16_cells(self) -> None:
        lines = CLICK_DUMP.read_bytes().decode("ascii").split("\r\n")
        for bank in ("X", "Y"):
            rows = {line.split(",")[0]: line for line in lines if line.startswith(bank)}
            assert rows[f"{bank}1"].count(",") == 33
            for start in range(101, 802, 100):
                assert rows[f"{bank}{start}"].count(",") == 17, (bank, start)

    def test_skip_default_keeps_err_format(self) -> None:
        data = read_plc_data(CLICK_DUMP, skip_default=True)
        value = data["DF31"]
        assert isinstance(value, float) and math.isnan(value)

    def test_write_matches_click_bytes_apart_from_err_format(self, tmp_path: Path) -> None:
        """With each NaN set to 0.0, the write is the dump with Err-Format as 0.00000000."""
        data = read_plc_data(CLICK_DUMP)
        data = {a: 0.0 if isinstance(v, float) and math.isnan(v) else v for a, v in data.items()}
        out = tmp_path / "out.csv"
        write_plc_data(out, data, banks=_SECTION_ORDER)
        assert out.read_bytes() == CLICK_DUMP.read_bytes().replace(b"Err-Format", b"0.00000000")

    def test_write_back_raises_on_err_format(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        with pytest.raises(ValueError, match="DF31"):
            write_plc_data(out, read_plc_data(CLICK_DUMP))
        assert not out.exists()


# CLICK's DF and TXT forms: rows DF251 and TXT961..TXT991 of a dump CLICK v4.00 wrote,
# with their sections' start, header and end lines.
CLICK_FORMS = Path(__file__).parent / "fixtures" / "PlcDataDumpForms.csv"
# CLICK writes TXT972's comma unquoted, so its row has 11 cells.
COMMA_ROW = "TXT971,*,,,/,:,;,<,=,>,?,@,"
# The values the PLC held: DF251..DF260, and TXT961..TXT970 and TXT981..TXT1000.
FORMS_DF = [1.8e30, 1.9e30, 2e30, 1.5e30, 1e35, -3e38, -0.0, 0.001953125, 0.0, 0.0]
FORMS_TXT = {
    961: [" ", "!", '"', "#", "$", "%", "&", "'", "(", ")"],
    981: ["[", "\\", "]", "^", "_", "`", "{", "|", "}", "~"],
    991: ["\x01", "\x7f", "\xff", "Z", "1", ".", "5", "0", "0", "0"],
}


def _forms_df() -> dict[str, float]:
    return {f"DF{251 + i}": value for i, value in enumerate(FORMS_DF)}


def _forms_txt() -> dict[str, str]:
    return {f"TXT{s + i}": c for s, chars in FORMS_TXT.items() for i, c in enumerate(chars)}


def _forms_lines_without_comma_row() -> list[str]:
    lines = CLICK_FORMS.read_bytes().decode("ascii").split("\r\n")
    lines.remove(COMMA_ROW)
    return lines


class TestClickForms:
    def test_comma_row_raises(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"^TXT971 row has 11 cells, not 10: CLICK writes a TXT comma unquoted",
        ):
            read_plc_data(CLICK_FORMS)

    def test_reads_the_other_rows(self, tmp_path: Path) -> None:
        p = tmp_path / "forms.csv"
        p.write_bytes("\r\n".join(_forms_lines_without_comma_row()).encode("ascii"))
        data = read_plc_data(p)
        df = {a: _float32(v) for a, v in _forms_df().items()}
        # CLICK keeps 8 decimals of 0.001953125, so it reads back as 0.00195312.
        df["DF258"] = 0.00195312
        assert data == {**df, **_forms_txt()}
        assert str(data["DF257"]) == "-0.0"

    def test_write_matches_click_cells_of_comma_row(self, tmp_path: Path) -> None:
        """The comma row's other nine marks are written as CLICK writes them."""
        marks = ["*", "/", ":", ";", "<", "=", ">", "?", "@"]
        addrs = ["TXT971"] + [f"TXT{n}" for n in range(973, 981)]
        out = tmp_path / "out.csv"
        write_plc_data(out, dict(zip(addrs, marks, strict=True)), banks=["TXT"])
        lines = out.read_bytes().decode("ascii").split("\r\n")
        (row,) = [line for line in lines if line.startswith("TXT971,")]
        cells = row.split(",")[1:-1]
        click = COMMA_ROW.split(",")[1:-1]
        assert len(click) == 11
        assert [cells[0], *cells[2:]] == [click[0], *click[3:]]
        assert cells[1] == ""

    def test_write_matches_click_bytes(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {**_forms_df(), **_forms_txt()}, banks=["DF", "TXT"])
        written = out.read_bytes().split(b"\r\n")
        for line in _forms_lines_without_comma_row():
            assert line.encode("ascii") in written, line


class TestWriteDfForm:
    @pytest.mark.parametrize(
        ("value", "cell"),
        [
            (0.0, "0.00000000"),
            (66.7, "66.69999695"),
            (-1.6, "-1.60000002"),
            (0.1, "0.10000000"),
            (123456.7, "123456.70312500"),
            (16777221.0, "16777220.00000000"),
            (1e10, "10000000000.00000000"),
            (1e30, "1000000015047466219900000000000.00000000"),
            (-1e30, "-1000000015047466219900000000000.00000000"),
            (3e37, "30000001069098037760000000000000000000.00"),
            (3e38, "300000000549775575800000000000000000000.0"),
            # From CLICK_FORMS
            (1.8e30, "1800000027085439196000000000000.00000000"),
            (1.9e30, "1899999953032322092000000000000.00000000"),
            (2e30, "2000000030094932440000000000000.00000000"),
            (1.5e30, "1499999947013335604000000000000.00000000"),
            (1e35, "100000004091847875960000000000000000.0000"),
            (-3e38, "-300000000549775575800000000000000000000.0"),
            (-0.0, "-0.00000000"),
            (0.001953125, "0.00195312"),
        ],
    )
    def test_writes_click_float_form(self, tmp_path: Path, value: float, cell: str) -> None:
        """The cell matches CLICK's cell for this value."""
        assert _first_cell(tmp_path, {"DF1": value}, "DF") == cell

    # Neighbouring float32 values CLICK wrote with 20 and 19 digits in ClickNick's run D2
    # (runner-jobs/d2/live-r8 DF251 and live-r6 DF258).
    @pytest.mark.parametrize(
        ("bits", "cell"),
        [
            (0x7154FFFF, "1054724837913280268300000000000.00000000"),
            (0x71550000, "1054724913471143994000000000000.00000000"),
        ],
    )
    def test_writes_click_cell_either_side_of_the_limit(
        self, tmp_path: Path, bits: int, cell: str
    ) -> None:
        """The cell matches CLICK's cell for this value."""
        (value,) = struct.unpack("<f", struct.pack("<I", bits))
        assert _first_cell(tmp_path, {"DF1": value}, "DF") == cell

    # Cells CLICK wrote in ClickNick's run D2 (runner-jobs/d2/live-r2, live-r6 and live-r8),
    # with the float32 values written. pyclickplc writes some of them with other last digits.
    @pytest.mark.parametrize(
        ("bits", "cell"),
        [
            (0x7154FFFF, "1054724837913280268300000000000.00000000"),  # r8 DF251
            (0x71550000, "1054724913471143994000000000000.00000000"),  # r6 DF258
            (0x715815B4, "1069999993433429738000000000000.00000000"),  # r2 DF254
            (0x690B933D, "10546000128175236840000000.00000000"),  # r8 DF254
            (0x79A28486, "105479998215512625970000000000000000.0000"),  # r8 DF253
            (0x7E9EB56B, "105479999641619551220000000000000000000.0"),  # r8 DF257
        ],
    )
    def test_reads_click_large_cell_as_float32_written(
        self, tmp_path: Path, bits: int, cell: str
    ) -> None:
        p = tmp_path / "data.csv"
        p.write_bytes(f"<DF=START>\r\nAddress,1,\r\nDF1,{cell},\r\n</DF=END>\r\n".encode("ascii"))
        (written,) = struct.unpack("<f", struct.pack("<I", bits))
        assert read_plc_data(p)["DF1"] == written

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_raises(self, tmp_path: Path, value: float) -> None:
        with pytest.raises(ValueError, match="DF7"):
            write_plc_data(tmp_path / "out.csv", {"DF7": value})

    def test_past_float32_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="DF7.*float32"):
            write_plc_data(tmp_path / "out.csv", {"DF7": 1e39})

    @pytest.mark.parametrize(
        "value",
        [
            10**400,
            10**5000,
            2**1024 - 1,
            -(2**1024 - 1),
            Fraction(10**400),
            Fraction(10**5000),
        ],
        ids=["1e400", "1e5000", "max-int", "min-int", "fraction-1e400", "fraction-1e5000"],
    )
    def test_huge_number_raises_a_short_message_with_the_address(
        self, tmp_path: Path, value: Any
    ) -> None:
        with pytest.raises(ValueError, match="DF7") as info:
            write_plc_data(tmp_path / "out.csv", {"DF7": value})
        assert len(str(info.value)) < 200

    def test_huge_int_past_float32_says_so(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="DF7.*outside the float32 range"):
            write_plc_data(tmp_path / "out.csv", {"DF7": 10**5000})

    @pytest.mark.parametrize(
        "value",
        [10**300, 10**5000, Fraction(10**5000), "a" * 3000],
        ids=["1e300", "1e5000", "fraction", "long-str"],
    )
    def test_huge_txt_value_raises_a_short_message_with_the_address(
        self, tmp_path: Path, value: Any
    ) -> None:
        with pytest.raises(ValueError, match="TXT7.*single character") as info:
            write_plc_data(tmp_path / "out.csv", {"TXT7": value})
        assert len(str(info.value)) < 200

    @pytest.mark.parametrize("value", ["abc", None])
    def test_not_a_number_raises_with_the_address(self, tmp_path: Path, value: Any) -> None:
        with pytest.raises(ValueError, match="DF7"):
            write_plc_data(tmp_path / "out.csv", {"DF7": value})


class TestTxtForm:
    def test_reads_escaped_cells(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            """\
            <TXT=START>
            Address,1,2,3,4,5,
            TXT1,$20,$D,$C8,$,A,
            </TXT=END>
            """,
        )
        data = read_plc_data(p)
        assert [data[f"TXT{i}"] for i in range(1, 6)] == [" ", "\r", "\xc8", "$", "A"]

    @pytest.mark.parametrize(
        ("value", "cell"),
        [
            ("A", "A"),
            ("z", "z"),
            ("7", "7"),
            ("+", "+"),
            ("-", "-"),
            (".", "."),
            ("", ""),
            ("\x00", ""),
            (" ", "$20"),
            ("\r", "$D"),
            ("\x01", "$1"),
            ("\x7f", "$7F"),
            ("\xc8", "$C8"),
            ("\xff", "$FF"),
            ('"', '"'),
            ("$", "$"),
            ("!", "!"),
            ("_", "_"),
        ],
    )
    def test_writes_click_text_form(self, tmp_path: Path, value: str, cell: str) -> None:
        assert _first_cell(tmp_path, {"TXT1": value}, "TXT") == cell

    def test_comma_raises(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        with pytest.raises(ValueError, match=r"^TXT3 value ',': CLICK writes a TXT comma unquoted"):
            write_plc_data(out, {"TXT3": ","})
        assert not out.exists()

    def test_punctuation_round_trips(self, tmp_path: Path) -> None:
        """The 28 marks among CLICK_FORMS's test values, all written plain.

        They are all ASCII punctuation but ``+ , - .``.
        """
        punctuation = [
            chr(c) for c in range(0x21, 0x7F) if not chr(c).isalnum() and chr(c) not in "+,-."
        ]
        assert len(punctuation) == 28
        original = {f"TXT{i}": c for i, c in enumerate(punctuation, start=1)}
        out = tmp_path / "out.csv"
        write_plc_data(out, original)
        data = read_plc_data(out)
        assert {a: data[a] for a in original} == original

    @pytest.mark.parametrize("value", ["AB", "Ā", 5])
    def test_not_one_byte_raises(self, tmp_path: Path, value: str | int) -> None:
        with pytest.raises(ValueError, match="TXT3"):
            write_plc_data(tmp_path / "out.csv", {"TXT3": value})

    def test_round_trip(self, tmp_path: Path) -> None:
        original = {"TXT1": " ", "TXT2": "\r", "TXT3": "\xc8", "TXT4": "Q", "TXT5": ""}
        out = tmp_path / "out.csv"
        write_plc_data(out, original)
        data = read_plc_data(out)
        assert {a: data[a] for a in original} == original


class TestWriteBytes:
    def test_crlf_and_a_blank_line_after_every_section(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        write_plc_data(out, {"CT1": True, "CTD1": 5})
        text = out.read_bytes().decode("ascii")
        assert "\n" not in text.replace("\r\n", "")
        assert "</CT=END>\r\n\r\n<CTD=START>\r\n" in text
        assert text.endswith("</CTD=END>\r\n\r\n")
