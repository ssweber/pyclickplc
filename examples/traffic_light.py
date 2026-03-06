#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyclickplc",
# ]
# ///

import asyncio
from pathlib import Path

from pyclickplc import (
    ClickServer,
    MemoryDataProvider,
    make_address_record,
    make_dataview_record,
    write_cdv,
    write_csv,
)

EXAMPLE_DIR = Path(__file__).resolve().parent
NICKNAMES_FILENAME = "traffic_light_nicknames.csv"
DATAVIEW_FILENAME = "traffic_light_dataview.cdv"

RED_STATE = {"TXT1": "R", "C1": True, "C2": False, "C3": False}
GREEN_STATE = {"TXT1": "G", "C1": False, "C2": False, "C3": True}
YELLOW_STATE = {"TXT1": "Y", "C1": False, "C2": True, "C3": False}

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5020


def generate_project_files(output_dir: str | Path = EXAMPLE_DIR) -> tuple[Path, Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    print("Generating project files...")

    nicknames = [
        make_address_record("C1", nickname="RedLight"),
        make_address_record("C2", nickname="YellowLight"),
        make_address_record("C3", nickname="GreenLight"),
        make_address_record("TXT1", nickname="TrafficState"),
    ]

    nickname_path = target_dir / NICKNAMES_FILENAME
    dataview_path = target_dir / DATAVIEW_FILENAME

    write_csv(nickname_path, nicknames)
    write_cdv(dataview_path, [make_dataview_record(r.display_address) for r in nicknames])
    print("Done.\n")

    return nickname_path, dataview_path


async def run_traffic_light(provider: MemoryDataProvider) -> None:
    print("Starting traffic light sequence...")
    while True:
        print("[STATE] RED")
        provider.bulk_set(RED_STATE)
        await asyncio.sleep(4.0)

        print("[STATE] GREEN")
        provider.bulk_set(GREEN_STATE)
        await asyncio.sleep(4.0)

        print("[STATE] YELLOW")
        provider.bulk_set(YELLOW_STATE)
        await asyncio.sleep(1.5)


async def main() -> None:
    generate_project_files()

    provider = MemoryDataProvider()
    provider.bulk_set(RED_STATE)

    asyncio.create_task(run_traffic_light(provider))

    print(f"Starting ClickServer on {SERVER_HOST}:{SERVER_PORT}...")
    async with ClickServer(provider, host=SERVER_HOST, port=SERVER_PORT):
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTraffic light server stopped.")
