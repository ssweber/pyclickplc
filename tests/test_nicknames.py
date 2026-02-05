"""Tests for pyclickplc.nicknames — CSV read/write for address data."""

from pyclickplc.addresses import AddressRecord
from pyclickplc.banks import DataType
from pyclickplc.nicknames import (
    CSV_COLUMNS,
    DATA_TYPE_CODE_TO_STR,
    DATA_TYPE_STR_TO_CODE,
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

    def test_read_empty_rows_skipped(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            ",BIT,,0,No,\n"
            'X001,BIT,"Input1",0,No,""\n',
            encoding="utf-8",
        )

        records = read_csv(csv_path)
        assert len(records) == 1

    def test_read_invalid_address_skipped(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "Address,Data Type,Nickname,Initial Value,Retentive,Address Comment\n"
            'INVALID,BIT,"Bad",0,No,""\n'
            'X001,BIT,"Good",0,No,""\n',
            encoding="utf-8",
        )

        records = read_csv(csv_path)
        assert len(records) == 1


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


class TestReadMdbCsv:
    """Tests for read_mdb_csv function."""

    def test_read_basic(self, tmp_path):
        csv_path = tmp_path / "Address.csv"
        csv_path.write_text(
            "AddrKey,MemoryType,Address,DataType,Nickname,Use,InitialValue,Retentive,Comment\n"
            "1,X,1,0,Input1,1,0,0,First input\n"
            "100663297,DS,1,1,Temp,1,100,1,Temperature\n",
            encoding="utf-8",
        )

        records = read_mdb_csv(csv_path)
        assert len(records) == 2

        x_records = [r for r in records.values() if r.memory_type == "X"]
        assert len(x_records) == 1
        assert x_records[0].nickname == "Input1"
        assert x_records[0].comment == "First input"

    def test_read_skips_empty_nicknames(self, tmp_path):
        csv_path = tmp_path / "Address.csv"
        csv_path.write_text(
            "AddrKey,MemoryType,Address,DataType,Nickname,Use,InitialValue,Retentive,Comment\n"
            "1,X,1,0,,,0,0,\n"
            "2,X,2,0,Input2,1,0,0,Second\n",
            encoding="utf-8",
        )

        records = read_mdb_csv(csv_path)
        assert len(records) == 1


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
