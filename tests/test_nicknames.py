"""Tests for pyclickplc.nicknames — CSV read/write for address data."""

from pathlib import Path
from typing import Any, cast

import pytest

from pyclickplc.addresses import AddressRecord, get_addr_key
from pyclickplc.banks import DataType
from pyclickplc.nicknames import (
    CSV_COLUMNS,
    CSV_ENCODING,
    DATA_TYPE_CODE_TO_STR,
    DATA_TYPE_STR_TO_CODE,
    AddressRecordMap,
    first_non_cp1252_char,
    format_csv,
    read_csv,
    read_mdb_csv,
    write_csv,
)


class TestConstants:
    """Tests for CSV constants."""

    def test_csv_columns(self):
        assert CSV_COLUMNS == [
            "Address",
            "Data Type",
            "Nickname",
            "Initial Value",
            "Retentive",
            "Address Comment",
        ]

    def test_data_type_str_to_code(self):
        assert DATA_TYPE_STR_TO_CODE["BIT"] == 0
        assert DATA_TYPE_STR_TO_CODE["INT"] == 1
        assert DATA_TYPE_STR_TO_CODE["TEXT"] == 6
        assert DATA_TYPE_STR_TO_CODE["TXT"] == 6

    def test_data_type_code_to_str(self):
        assert DATA_TYPE_CODE_TO_STR[0] == "BIT"
        assert DATA_TYPE_CODE_TO_STR[1] == "INT"
        assert DATA_TYPE_CODE_TO_STR[6] == "TEXT"


class TestReadCsv:
    """Tests for read_csv function."""

    def test_read_basic(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"Input1",0,No,"First input"\n'
            'DS1,INT,"Temp",100,Yes,"Temperature"\n',
            encoding="utf-8",
        )

        records = read_csv(csv_path)
        assert isinstance(records, AddressRecordMap)
        assert len(records) == 2

        # Find the X001 record
        x_records = [r for r in records.values() if r.memory_type == "X"]
        assert len(x_records) == 1
        assert x_records[0].nickname == "Input1"
        assert x_records[0].comment == "First input"
        assert x_records[0].data_type == DataType.BIT
        assert x_records[0].retentive is False

        # Find the DS1 record
        ds_records = [r for r in records.values() if r.memory_type == "DS"]
        assert len(ds_records) == 1
        assert ds_records[0].nickname == "Temp"
        assert ds_records[0].retentive is True

        # The map also accepts the integer key from get_addr_key
        assert records[get_addr_key("X", 1)].nickname == "Input1"
        assert records[get_addr_key("DS", 1)].nickname == "Temp"

    def test_read_addr_lookup_normalized(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"Input1",0,No,""\n'
            'DS1,INT,"Temp",0,Yes,""\n',
            encoding="utf-8",
        )
        records = read_csv(csv_path)
        assert records.addr["x1"].nickname == "Input1"
        assert records.addr["X001"].nickname == "Input1"
        assert records.addr["ds1"].nickname == "Temp"

    def test_read_tag_lookup_case_insensitive(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"MyTag",0,No,""\n',
            encoding="utf-8",
        )
        records = read_csv(csv_path)
        assert records.tag["MyTag"].display_address == "X001"
        assert records.tag["mytag"].display_address == "X001"

    def test_read_tag_lookup_excludes_empty_nickname(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"",0,No,""\n',
            encoding="utf-8",
        )
        records = read_csv(csv_path)
        with pytest.raises(KeyError):
            _ = records.tag[""]

    def test_read_blank_rows_skipped(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            ",,,,,\n"
            'X001,BIT,"Input1",0,No,""\n'
            ",,  ,,,\n",
            encoding="utf-8",
        )

        records = read_csv(csv_path)
        assert len(records) == 1

    @pytest.mark.parametrize("address", ["", "INVALID", "X017", "DS1u"])
    def test_read_bad_address_raises_with_line(self, tmp_path, address):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"Good",0,No,""\n'
            f'{address},BIT,"Bad",0,No,""\n',
            encoding="utf-8",
        )

        with pytest.raises(
            ValueError, match=r"test\.csv line 3: Address .* is not a CLICK address"
        ):
            read_csv(csv_path)

    def test_read_duplicate_nickname_loads_and_tag_lookup_raises(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT,"Pump",0,No,""\n'
            'X002,BIT,"pump",0,No,""\n',
            encoding="utf-8",
        )

        csv_path.write_text(
            csv_path.read_text(encoding="utf-8") + 'X003,BIT,"Other",0,No,""\n', encoding="utf-8"
        )

        records = read_csv(csv_path)

        assert [r.nickname for r in records.values()] == ["Pump", "pump", "Other"]
        assert records.addr["X003"].nickname == "Other"
        # While a nickname repeats, every .tag lookup raises, including a lookup of a unique nickname.
        with pytest.raises(ValueError, match="duplicate tag nickname.*'pump'"):
            _ = records.tag["pump"]
        with pytest.raises(ValueError, match="duplicate tag nickname"):
            _ = records.tag["Other"]
        with pytest.raises(ValueError, match="duplicate tag nickname"):
            _ = "Other" in records.tag

    def test_read_keeps_nickname_and_comment_as_written(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'X001,BIT," Pump ",0,No,"  spaced  "\n',
            encoding="utf-8",
        )

        record = read_csv(csv_path).addr["X001"]

        assert (record.nickname, record.comment) == (" Pump ", "  spaced  ")

    @pytest.mark.parametrize(
        ("cell", "expected"),
        [("Yes", True), ("yes", True), ("TRUE", True), ("1", True), ("No", False), ("0", False)],
    )
    def test_read_retentive_spellings(self, tmp_path, cell, expected):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            f'C1,BIT,"Flag",0,{cell},""\n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr["C1"].retentive is expected

    def test_read_reports_columns_and_takes_fewer_required(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("Address,Address Comment\nDS1,Speed\n", encoding="utf-8")

        with pytest.raises(ValueError, match="missing required column.*Nickname"):
            read_csv(csv_path)
        records = read_csv(csv_path, required=["Address"])

        assert records.columns == ("Address", "Address Comment")
        assert records.addr["DS1"].comment == "Speed"
        assert records.addr["DS1"].retentive is True  # the bank's default

    def test_read_unknown_data_type_raises_with_line(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'DS1,INT,"Speed",0,Yes,""\n'
            'SD1,SINT,"SysFlag",0,No,""\n',
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match=r"test\.csv line 3: Data Type 'SINT'"):
            read_csv(csv_path)

    def test_read_blank_data_type_is_the_banks(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'DF1,,"Flow",0,Yes,""\n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr["DF1"].data_type is DataType.FLOAT

    @pytest.mark.parametrize(
        ("address", "cell", "expected"),
        [
            ("TXT1", "text", DataType.TXT),
            ("TXT1", "Text", DataType.TXT),
            ("DD1", "int2", DataType.INT2),
            ("XD1", "hex", DataType.HEX),
        ],
    )
    def test_read_data_type_any_case(self, tmp_path, address, cell, expected):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            f'{address},{cell},"Name",,No,""\n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr[address].data_type is expected

    @pytest.mark.parametrize("cell", ["TXT", "txt", "STRING", "WORD"])
    def test_read_data_type_alias_raises_with_line(self, tmp_path, cell):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            f'TXT1,{cell},"Msg",A,Yes,""\n',
            encoding="utf-8",
        )

        with pytest.raises(
            ValueError, match=rf"test\.csv line 2: Data Type '{cell}' is not a CLICK data type"
        ):
            read_csv(csv_path)

    @pytest.mark.parametrize(
        ("address", "cell", "bank_type"),
        [("DS1", "TEXT", "INT"), ("X001", "INT", "BIT"), ("DD1", "INT", "INT2")],
    )
    def test_read_data_type_not_the_banks_raises_with_line(
        self, tmp_path, address, cell, bank_type
    ):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'C1,BIT,"Flag",0,No,""\n'
            f'{address},{cell},"Name",0,No,""\n',
            encoding="utf-8",
        )

        with pytest.raises(
            ValueError,
            match=rf"test\.csv line 3: Data Type '{cell}' is not the type of {address} "
            rf"\({bank_type}\)",
        ):
            read_csv(csv_path)

    @pytest.mark.parametrize(
        ("cell", "expected"),
        [("true", True), ("False", False), ("no", False), ("garbage", False), ("", True)],
    )
    def test_read_retentive_on_a_retentive_bank(self, tmp_path, cell, expected):
        """DS is retentive by default. A blank cell keeps that default. Otherwise only Yes, True or 1 keeps it on."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            f'DS1,INT,"Speed",0,{cell},""\n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr["DS1"].retentive is expected

    def test_read_address_with_nbsp_around_it(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            ' DS1 ,INT,"Speed",0,Yes,""\n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr["DS1"].nickname == "Speed"

    def test_read_address_with_leading_zeros(self, tmp_path):
        # CLICK's import stores each of these rows under the address without its leading zeros,
        # whether or not the address is quoted
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'DS030,INT,"Zero One",1,No,""\n'
            '"DS0032",INT,"Zero Two",3,No,""\n'
            'X0001,BIT,"X Zero",0,No,""\n',
            encoding="utf-8",
        )

        records = read_csv(csv_path)
        assert records.addr["DS30"].nickname == "Zero One"
        assert records.addr["DS32"].nickname == "Zero Two"
        assert records.addr["X1"].nickname == "X Zero"

    def test_read_required_as_one_column_name(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("Address,Address Comment\nDS1,Speed\n", encoding="utf-8")

        records = read_csv(csv_path, required="Address")

        assert records.addr["DS1"].comment == "Speed"
        with pytest.raises(ValueError, match=r"missing required column\(s\): Nickname$"):
            read_csv(csv_path, required="Nickname")

    @pytest.mark.parametrize(
        "row",
        [
            'DF1,FLOAT,"Flow",1,5,No,"note"',  # an unquoted comma in a numeric initial value
            'DS1,INT,"Speed",0,Yes,"",extra',
        ],
    )
    def test_read_extra_cells_raise_with_line(self, tmp_path, row):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'C1,BIT,"Flag",0,No,""\n'
            f"{row}\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match=r"test\.csv line 3: more cells than the header"):
            read_csv(csv_path)

    def test_read_blank_extra_cells_are_ignored(self, tmp_path):
        """A spreadsheet may pad rows with empty cells past the header."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'DS1,INT,"Speed",0,Yes,"",, \n',
            encoding="utf-8",
        )

        assert read_csv(csv_path).addr["DS1"].nickname == "Speed"

    def test_read_data_type_is_enum(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'DS1,INT,"Speed",0,Yes,""\n',
            encoding="utf-8",
        )

        assert type(read_csv(csv_path).addr["DS1"].data_type) is DataType

    def test_read_cp1252(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_bytes(
            b"Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\r\n"
            b'X001,BIT,"Caf\xe9",0,No,"\x80 5"\r\n'
        )

        record = read_csv(csv_path).addr["X001"]
        assert (record.nickname, record.comment) == ("Café", "€ 5")

    def test_read_utf8_without_bom(self, tmp_path):
        """pyclickplc 0.10.0 and older wrote UTF-8 without a byte order mark."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_bytes(
            b"Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\r\n"
            + 'X001,BIT,"Café",0,No,"€ 5"\r\n'.encode()
        )

        record = read_csv(csv_path).addr["X001"]
        assert (record.nickname, record.comment) == ("Café", "€ 5")

    def test_read_neither_utf8_nor_cp1252_raises(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_bytes(
            b"Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\r\n"
            b'X001,BIT,"Caf\x81",0,No,""\r\n'
        )

        with pytest.raises(ValueError, match=r"test\.csv is neither UTF-8 nor cp1252"):
            read_csv(csv_path)

    def test_read_bom_then_not_utf8_raises(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_bytes(
            b"\xef\xbb\xbfAddress,Data Type,Nickname,Initial Value,Retentive,Address Comment\r\n"
            b'X001,BIT,"Caf\xe9",0,No,""\r\n'
        )

        with pytest.raises(ValueError, match=r"test\.csv starts with a UTF-8 byte order mark"):
            read_csv(csv_path)

    def test_tag_lookup_rejects_case_collisions_after_mutation(self):
        records = AddressRecordMap(
            {
                1: AddressRecord(memory_type="X", address=1, nickname="Pump"),
                2: AddressRecord(memory_type="X", address=2, nickname="pump"),
            }
        )
        with pytest.raises(ValueError, match="duplicate tag nickname"):
            _ = records.tag["pump"]


class TestWriteCsv:
    """Tests for write_csv function."""

    def test_write_basic(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        records = {
            1: AddressRecord(memory_type="X", address=1, nickname="Input1", comment="First input"),
        }

        count = write_csv(csv_path, records)
        assert count == 1

        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert lines[0] == ",".join(CSV_COLUMNS)
        assert '"Input1"' in lines[1]
        assert '"First input"' in lines[1]

    def test_write_skips_empty_records(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        records = {
            1: AddressRecord(memory_type="X", address=1),  # No content
            2: AddressRecord(memory_type="X", address=2, nickname="HasNick"),
        }

        count = write_csv(csv_path, records)
        assert count == 1  # Only one record has content

    def test_write_sorted_by_memory_type(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        # DS comes after X in MEMORY_TYPE_BASES ordering
        records = {
            100_000_001: AddressRecord(memory_type="DS", address=1, nickname="DS_Nick"),
            1: AddressRecord(memory_type="X", address=1, nickname="X_Nick"),
        }

        write_csv(csv_path, records)

        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        # X should come before DS
        assert "X001" in lines[1]
        assert "DS1" in lines[2]

    def test_write_accepts_record_iterable(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        records = [
            AddressRecord(memory_type="DS", address=1, nickname="DS_Nick"),
            AddressRecord(memory_type="X", address=1, nickname="X_Nick"),
        ]

        count = write_csv(csv_path, records)
        assert count == 2

        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert "X001" in lines[1]
        assert "DS1" in lines[2]

    def test_format_csv_is_the_text_write_csv_writes(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        records = [
            AddressRecord(
                memory_type="TXT",
                address=1,
                nickname="Msg",
                initial_value=",",
                data_type=DataType.TXT,
            ),
            AddressRecord(memory_type="X", address=1, nickname="X_Nick"),
        ]

        write_csv(csv_path, records)

        assert format_csv(records).encode(CSV_ENCODING) == csv_path.read_bytes()

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("", None), ("Café €", None), ("Ohm_Ω 中", "Ω"), ("\x80", "\x80")],
    )
    def test_first_non_cp1252_char(self, text, expected):
        assert first_non_cp1252_char(text) == expected

    def test_write_cp1252(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        record = AddressRecord(memory_type="C", address=1, nickname="Café", comment="€")

        write_csv(csv_path, [record])

        assert csv_path.read_bytes().splitlines()[1] == b'C1,BIT,"Caf\xe9",0,No,"\x80"'

    @pytest.mark.parametrize(
        ("record", "column"),
        [
            (AddressRecord(memory_type="DS", address=2, nickname="Han_中"), "Nickname"),
            (AddressRecord(memory_type="DS", address=2, comment="Han_中"), "Address Comment"),
        ],
    )
    def test_write_character_outside_cp1252_raises(self, tmp_path, record, column):
        csv_path = tmp_path / "test.csv"

        with pytest.raises(ValueError, match=f"DS2 {column} 'Han_中' has '中'"):
            write_csv(csv_path, [record])
        assert not csv_path.exists()
        with pytest.raises(ValueError, match=f"DS2 {column}"):
            format_csv([record])

    def test_write_none_nickname_and_comment_as_empty(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        records = [
            AddressRecord(memory_type="C", address=1, nickname="a", comment=cast(Any, None)),
            AddressRecord(memory_type="C", address=2, nickname=cast(Any, None), comment="b"),
            AddressRecord(memory_type="C", address=3, nickname=cast(Any, 7), comment="c"),
        ]

        write_csv(csv_path, records)

        assert csv_path.read_bytes().splitlines()[1:] == [
            b'C1,BIT,"a",0,No,""',
            b'C2,BIT,"",0,No,"b"',
            b'C3,BIT,"7",0,No,"c"',
        ]

    @pytest.mark.parametrize("initial", ["1,5", 'a"b', "1\r\n2"])
    def test_write_quotes_a_numeric_initial_value_that_needs_it(self, tmp_path, initial):
        """write_csv quotes a numeric initial value with a comma, double quote or line break.

        read_csv reads it back as one value. CLICK never writes such a value.
        """
        csv_path = tmp_path / "test.csv"
        record = AddressRecord(
            memory_type="DF",
            address=1,
            nickname="Flow",
            initial_value=initial,
            data_type=DataType.FLOAT,
            retentive=True,
            comment="note",
        )

        write_csv(csv_path, [record])
        loaded = read_csv(csv_path).addr["DF1"]

        assert '"' + initial.replace('"', '""') + '"' in csv_path.read_bytes().decode("utf-8")
        assert (loaded.initial_value, loaded.retentive, loaded.comment) == (initial, True, "note")


class TestReadMdbCsv:
    """Tests for read_mdb_csv, which reads CLICK's Address.csv.

    That file has the columns and addresses of CLICK's project database, in UTF-8 with a BOM.
    """

    HEADER = "AddrKey,MemoryType,Address,DataType,Nickname,Use,InitialValue,Retentive,Comment"

    def write(self, tmp_path, *rows: str) -> Path:
        csv_path = tmp_path / "Address.csv"
        csv_path.write_bytes(
            "".join(f"{line}\r\n" for line in (self.HEADER, *rows)).encode("utf-8-sig")
        )
        return csv_path

    def test_reads_fields(self, tmp_path):
        csv_path = self.write(tmp_path, '100663297,DS,1,1,Temp,1,100,1,"  spaced  "')

        record = read_mdb_csv(csv_path).addr["DS1"]

        assert record.nickname == "Temp"
        assert record.comment == "  spaced  "
        assert record.initial_value == "100"
        assert record.retentive is True
        assert record.used is True
        assert record.data_type is DataType.INT

    def test_xd_address_is_mdb(self, tmp_path):
        csv_path = self.write(
            tmp_path, "167772162,XD,2,4,Inputs1,0,0,0,", "167772161,XD,1,4,Upper,,0,0,"
        )

        records = read_mdb_csv(csv_path)

        assert records.addr["XD1"].nickname == "Inputs1"
        assert records.addr["XD1"].used is False
        assert records.addr["XD0u"].used is None

    def test_keeps_only_rows_with_content(self, tmp_path):
        csv_path = self.write(
            tmp_path,
            "33554433,C,1,0,,0,1,0,",
            "33554434,C,2,0,,0,0,1,",
            "33554435,C,3,0,,1,0,0,",
        )

        records = read_mdb_csv(csv_path)

        assert sorted((r.address, r.initial_value, r.retentive) for r in records.values()) == [
            (1, "1", False),
            (2, "0", True),
        ]

    def test_skips_unknown_rows(self, tmp_path):
        csv_path = self.write(
            tmp_path,
            "1,ZZ,1,0,BadType,1,0,0,Bad",
            "2,X,NotInt,0,BadAddr,1,0,0,Bad",
            "17,X,17,0,NoSlot,1,0,0,Bad",
            "3,DS,1,1,Good,1,123,1,Good row",
        )

        records = read_mdb_csv(csv_path)

        assert [r.display_address for r in records.values()] == ["DS1"]

    def test_data_type_is_the_banks(self, tmp_path):
        """read_mdb_csv ignores the DataType column and gives each record its bank's type.

        read_csv then reads back the text that format_csv writes, with the same types.
        """
        csv_path = self.write(
            tmp_path,
            "100663297,DS,1,4,Speed,1,5,1,",
            "201326593,TXT,1,1,Msg,1,A,1,",
            "100663298,DS,2,,Blank,1,0,1,",
        )

        records = read_mdb_csv(csv_path)
        out = tmp_path / "Nicknames.csv"
        out.write_bytes(format_csv(records).encode("utf-8"))
        loaded = read_csv(out)

        expected = [("DS1", DataType.INT), ("DS2", DataType.INT), ("TXT1", DataType.TXT)]
        assert sorted((r.display_address, r.data_type) for r in records.values()) == expected
        assert sorted((r.display_address, r.data_type) for r in loaded.values()) == expected

    def test_skips_xd_hidden_slots(self, tmp_path):
        """read_mdb_csv skips the XD and YD slots that CLICK does not show.

        Here they are XD3 and YD15 in the database's numbering. XD3 would display as XD1, beside
        the real XD1.
        """
        csv_path = self.write(
            tmp_path,
            "167772163,XD,3,4,Hidden,0,0,0,",
            "167772162,XD,2,4,Real,0,0,0,",
            "201326595,YD,15,4,HiddenY,0,0,0,",
        )

        records = read_mdb_csv(csv_path)

        assert [(r.display_address, r.nickname) for r in records.values()] == [("XD1", "Real")]
        assert format_csv(records).count("XD1,") == 1

    def test_not_utf8_raises(self, tmp_path):
        csv_path = tmp_path / "Address.csv"
        csv_path.write_bytes((self.HEADER + "\r\n").encode() + b"3,DS,1,1,Caf\xe9,1,0,1,\r\n")

        with pytest.raises(ValueError, match=r"Address\.csv is not UTF-8"):
            read_mdb_csv(csv_path)

    def test_malformed_csv_raises(self, tmp_path):
        csv_path = self.write(tmp_path, '3,DS,1,1,"' + "x" * 200_000 + '",1,0,1,')

        with pytest.raises(ValueError, match=r"Address\.csv line \d+: field larger"):
            read_mdb_csv(csv_path)


class TestRoundTrip:
    """Tests for write then read round-trip."""

    def test_roundtrip(self, tmp_path):
        csv_path = tmp_path / "roundtrip.csv"
        original = {
            1: AddressRecord(
                memory_type="X",
                address=1,
                nickname="Motor1",
                comment="Main motor",
                data_type=DataType.BIT,
                retentive=False,
            ),
            100_663_297: AddressRecord(
                memory_type="DS",
                address=1,
                nickname="Speed",
                comment="Motor speed",
                initial_value="500",
                data_type=DataType.INT,
                retentive=True,
            ),
        }

        write_csv(csv_path, original)
        loaded = read_csv(csv_path)

        assert len(loaded) == 2

        # Check X001
        x_records = [r for r in loaded.values() if r.memory_type == "X"]
        assert len(x_records) == 1
        assert x_records[0].nickname == "Motor1"
        assert x_records[0].comment == "Main motor"

        # Check DS1
        ds_records = [r for r in loaded.values() if r.memory_type == "DS"]
        assert len(ds_records) == 1
        assert ds_records[0].nickname == "Speed"
        assert ds_records[0].comment == "Motor speed"
        assert ds_records[0].retentive is True


class TestCsvFormat:
    """Tests that read_csv and write_csv handle the bytes of the file as CLICK does."""

    HEADER = "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment"

    def test_read_accepts_utf8_bom(self, tmp_path):
        csv_path = tmp_path / "bom.csv"
        csv_path.write_bytes(
            b"\xef\xbb\xbf" + (self.HEADER + '\r\nDS1,INT,"Temp",100,Yes,""\r\n').encode()
        )
        records = read_csv(csv_path)
        assert records[get_addr_key("DS", 1)].nickname == "Temp"

    @pytest.mark.parametrize(
        "header",
        [
            "Address,Data Type,Initial Value,Retentive,Address Comment",
            "Data Type,Nickname,Initial Value,Retentive,Address Comment",
            "DS1,INT,100",
        ],
    )
    def test_read_missing_required_column_raises(self, tmp_path, header):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text(header + "\nDS1,INT,100\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required column"):
            read_csv(csv_path)

    def test_write_uses_crlf(self, tmp_path):
        csv_path = tmp_path / "out.csv"
        record = AddressRecord(memory_type="DS", address=1, nickname="Temp", data_type=DataType.INT)
        write_csv(csv_path, [record])
        raw = csv_path.read_bytes()
        assert raw.count(b"\r\n") == 2
        assert raw.count(b"\n") == 2

    @pytest.mark.parametrize("initial", [",", '"', 'a,"b"', "a b", " ", "\t", "\x0b", "\x0c"])
    def test_txt_initial_value_round_trips(self, tmp_path, initial):
        csv_path = tmp_path / "txt.csv"
        record = AddressRecord(
            memory_type="TXT",
            address=5,
            nickname="Msg",
            initial_value=initial,
            data_type=DataType.TXT,
        )
        write_csv(csv_path, [record])
        loaded = read_csv(csv_path)[get_addr_key("TXT", 5)]
        assert loaded.initial_value == initial
        assert loaded.nickname == "Msg"

    @pytest.mark.parametrize(
        ("initial", "cell"),
        [
            ("A", b"A"),
            (" ", b'" "'),
            ("\t", b'"\t"'),
            ("\x0b", b'"\x0b"'),
            ("\x0c", b'"\x0c"'),
            ("\x01", b'"\x01"'),
            ("", b""),
            (",", b'","'),
            ('"', b'""""'),
            ("!", b"!"),
        ],
    )
    def test_txt_initial_value_bare_unless_whitespace_comma_or_quote(self, tmp_path, initial, cell):
        """write_csv quotes a Text initial value only where CLICK needs the quotes to import it.

        CLICK writes a Text value unquoted. It imports a comma or a double quote only in quotes.
        It strips a space, tab, VT or FF at either end of an unquoted value, so a value of one of
        these would import as empty. write_csv also quotes any other character up to 0x20, on the
        assumption that CLICK strips those too.
        """
        csv_path = tmp_path / "txt.csv"
        record = AddressRecord(
            memory_type="TXT",
            address=1,
            nickname="Msg",
            initial_value=initial,
            data_type=DataType.TXT,
            retentive=True,
        )
        write_csv(csv_path, [record])
        assert csv_path.read_bytes().splitlines()[1] == b'TXT1,TEXT,"Msg",' + cell + b',Yes,""'

    @pytest.mark.parametrize(
        ("initial", "data_type", "memory_type"),
        [
            (" 5", DataType.INT, "DS"),
            ("5 ", DataType.INT, "DS"),
            ("\t5", DataType.INT, "DS"),
            (" 1.5", DataType.FLOAT, "DF"),
        ],
    )
    def test_number_with_edge_whitespace_is_written_bare(
        self, tmp_path, initial, data_type, memory_type
    ):
        """write_csv writes a number with a space or tab at either end unquoted.

        CLICK refuses such a number in quotes. Unquoted, CLICK strips the space.
        """
        csv_path = tmp_path / "num.csv"
        record = AddressRecord(
            memory_type=memory_type,
            address=1,
            nickname="Num",
            initial_value=initial,
            data_type=data_type,
        )
        write_csv(csv_path, [record])
        cell = csv_path.read_bytes().decode("utf-8").splitlines()[1].split(",")[3]
        assert cell == initial

    @pytest.mark.parametrize(
        ("memory_type", "address", "data_type"),
        [("X", 1, DataType.BIT), ("DS", 1, DataType.INT), ("TXT", 1, DataType.TXT)],
    )
    def test_address_is_never_quoted(self, memory_type, address, data_type):
        """format_csv writes the Address cell without quotes.

        It does so even when the nickname, initial value and comment are a space.

        CLICK refuses a quoted address that has a space at either end. It does not store that row.
        It writes the row's nickname, initial value, Retentive and comment over the row before it.
        """
        record = AddressRecord(
            memory_type=memory_type,
            address=address,
            nickname=" ",
            initial_value=" ",
            data_type=data_type,
            comment=" ",
        )
        row = format_csv([record]).splitlines()[1]
        assert row.startswith(record.display_address + ",")

    def test_every_text_character_round_trips(self, tmp_path):
        csv_path = tmp_path / "txt.csv"
        # cp1252 has no U+0080 to U+009F.
        chars = [chr(code) for code in range(1, 256) if not 0x80 <= code <= 0x9F]
        records = [
            AddressRecord(
                memory_type="TXT",
                address=i,
                nickname=f"T{i}",
                initial_value=char,
                data_type=DataType.TXT,
            )
            for i, char in enumerate(chars, 1)
        ]
        write_csv(csv_path, records)
        loaded = read_csv(csv_path)
        assert [
            loaded[get_addr_key("TXT", i)].initial_value for i in range(1, len(chars) + 1)
        ] == chars


FIXTURES = Path(__file__).parent / "fixtures"


class TestClickExports:
    """Real CSV files exported by CLICK."""

    def test_click_export_rewrites_to_the_same_bytes(self, tmp_path):
        """read_csv and write_csv reproduce a CLICK export byte for byte.

        The export has every bank and every column type.
        """
        fixture = FIXTURES / "NicknameExport.csv"
        out = tmp_path / "out.csv"
        write_csv(out, read_csv(fixture))
        assert out.read_bytes() == fixture.read_bytes()

    def test_reads_clicks_bare_comma_and_quote(self):
        """CLICK exports these Text values unquoted, even a comma or a double quote.

        read_csv still reads every value, and no cell moves to the wrong column.
        """
        records = read_csv(FIXTURES / "NicknameExportTxtSpecials.csv")
        txt = [records[get_addr_key("TXT", i)] for i in range(1, 6)]
        assert [(r.nickname, r.initial_value, r.retentive, r.comment) for r in txt] == [
            ("Msg_Plain", "A", True, ""),
            ("Msg_Comma", ",", False, ""),
            ("Msg_Quote", '"', True, ""),
            ("Msg_Space", " ", True, ""),
            ("Msg_Empty", "", True, ""),
        ]
        assert records[get_addr_key("DF", 1)].comment == "Degrees, F"

    def test_click_export_rewrites_with_comma_and_quote_importable(self, tmp_path):
        """write_csv changes only TXT2, TXT3 and TXT4, and it quotes their values.

        CLICK cannot import its own unquoted form of these values.
        """
        fixture = FIXTURES / "NicknameExportTxtSpecials.csv"
        out = tmp_path / "out.csv"
        write_csv(out, read_csv(fixture))
        expected = (
            fixture.read_bytes()
            .replace(b'TXT2,TEXT,"Msg_Comma",,,No,""', b'TXT2,TEXT,"Msg_Comma",",",No,""')
            .replace(b'TXT3,TEXT,"Msg_Quote",",Yes,""', b'TXT3,TEXT,"Msg_Quote","""",Yes,""')
            .replace(b'TXT4,TEXT,"Msg_Space", ,Yes,""', b'TXT4,TEXT,"Msg_Space"," ",Yes,""')
        )
        assert expected != fixture.read_bytes()
        assert out.read_bytes() == expected

    @pytest.mark.parametrize("fixture", ["NicknameExportCp1252.csv", "NicknameExportBestFit.csv"])
    def test_cp1252_export_rewrites_to_the_same_bytes(self, tmp_path, fixture):
        """CLICK exports these files as cp1252. They hold the system SC and SD nicknames."""
        out = tmp_path / "out.csv"
        write_csv(out, read_csv(FIXTURES / fixture))
        assert out.read_bytes() == (FIXTURES / fixture).read_bytes()

    def test_reads_cp1252_export(self):
        records = read_csv(FIXTURES / "NicknameExportCp1252.csv")
        assert [(records.addr[a].nickname, records.addr[a].comment) for a in ("C1", "DS1")] == [
            ("Motor_é", "naïve résumé"),
            ("Price_€", "café counter"),
        ]
