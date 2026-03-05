from __future__ import annotations

from pyclickplc import read_cdv, read_csv

from ._traffic_light_loader import load_traffic_light_example


def test_generate_project_files_writes_expected_outputs(tmp_path):
    module = load_traffic_light_example()

    nickname_path, dataview_path = module.generate_project_files(output_dir=tmp_path)

    assert nickname_path == tmp_path / module.NICKNAMES_FILENAME
    assert dataview_path == tmp_path / module.DATAVIEW_FILENAME
    assert nickname_path.exists()
    assert dataview_path.exists()

    nicknames = read_csv(nickname_path)
    assert nicknames.addr["C1"].nickname == "RedLight"
    assert nicknames.addr["C2"].nickname == "YellowLight"
    assert nicknames.addr["C3"].nickname == "GreenLight"
    assert nicknames.addr["TXT1"].nickname == "TrafficState"

    dataview = read_cdv(dataview_path)
    assert dataview.rows[0].address == "TXT1"
    assert dataview.rows[1].address == "C1"
    assert dataview.rows[2].address == "C2"
    assert dataview.rows[3].address == "C3"
    assert dataview.rows[0].new_value is None
    assert dataview.rows[1].new_value is None
    assert dataview.rows[2].new_value is None
    assert dataview.rows[3].new_value is None
