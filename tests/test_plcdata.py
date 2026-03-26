"""Tests for plcdata — Click PLC 'Read Data from PLC' CSV parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

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
            TXT1,,,
            </TXT=END>
            """,
        )
        data = read_plc_data(p)
        assert data["TXT1"] == ""
        assert data["TXT2"] == ""

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
