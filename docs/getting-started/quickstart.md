# Quickstart

Connect to a simulated PLC, read and write values, then generate CLICK project files — no hardware required.

## Install

```bash
# Requires Python 3.11+
uv add pyclickplc
```

## Connect and read/write

Start a simulated PLC with `ClickServer`, then read and write registers with `ClickClient`:

```python
import asyncio
from pyclickplc import ClickClient, ClickServer, MemoryDataProvider

async def main():
    provider = MemoryDataProvider()
    provider.bulk_set({"DS1": 100, "DS2": 200, "C1": True})

    async with ClickServer(provider, host="localhost", port=5020):
        async with ClickClient("localhost", 5020) as plc:
            # Read a single register
            ds1 = await plc.ds[1]
            print(f"DS1 = {ds1}")  # 100

            # Write a register
            await plc.ds.write(1, 999)
            print(f"DS1 = {await plc.ds[1]}")  # 999

            # Read a range
            values = await plc.ds.read(1, 2)
            print(values)  # {"DS1": 999, "DS2": 200}

            # Read/write by address string
            await plc.addr.write("C1", False)
            c1 = await plc.addr.read("C1")
            print(f"C1 = {c1}")  # False

asyncio.run(main())
```

`MemoryDataProvider` holds PLC values in memory. `ClickServer` exposes them over Modbus TCP. `ClickClient` talks Modbus TCP and returns native Python types — `bool` for coils, `int` for data registers, `float` for `DF`, `str` for `TXT`.

## Traffic light simulator

A more realistic example: a state machine that cycles a traffic light through red, green, and yellow.

```python
import asyncio
from pyclickplc import ClickClient, ClickServer, MemoryDataProvider

STATES = {
    "red":    {"C1": True,  "C2": False, "C3": False, "TXT1": "RED"},
    "green":  {"C1": False, "C2": False, "C3": True,  "TXT1": "GREEN"},
    "yellow": {"C1": False, "C2": True,  "C3": False, "TXT1": "YELLOW"},
}
CYCLE = ["red", "green", "yellow"]
DURATIONS = {"red": 3, "green": 3, "yellow": 1}

async def run_traffic_light(provider):
    """Cycle through states, updating the provider directly."""
    idx = 0
    while True:
        state = CYCLE[idx]
        provider.bulk_set(STATES[state])
        print(f"Light: {state}")
        await asyncio.sleep(DURATIONS[state])
        idx = (idx + 1) % len(CYCLE)

async def main():
    provider = MemoryDataProvider()
    provider.bulk_set(STATES["red"])

    # Run the state machine in the background
    asyncio.create_task(run_traffic_light(provider))

    async with ClickServer(provider, host="localhost", port=5020):
        async with ClickClient("localhost", 5020) as plc:
            for _ in range(5):
                await asyncio.sleep(2)
                txt = await plc.addr.read("TXT1")
                c1 = await plc.addr.read("C1")
                c2 = await plc.addr.read("C2")
                c3 = await plc.addr.read("C3")
                print(f"  Client sees: {txt}  (R={c1} Y={c2} G={c3})")

asyncio.run(main())
```

The server side updates `MemoryDataProvider` directly. The client reads over Modbus TCP and gets the current state — same as it would from a real PLC.

## Export to ClickNick

Generate nickname CSV and DataView CDV files that you can load in [ClickNick](https://github.com/ssweber/clicknick) or CLICK programming software:

```python
from pyclickplc import (
    DataViewFile,
    make_address_record,
    make_dataview_record,
    write_cdv,
    write_csv,
)

# Nickname CSV — maps addresses to human-readable names
nicknames = [
    make_address_record("C1", nickname="RedLight"),
    make_address_record("C2", nickname="YellowLight"),
    make_address_record("C3", nickname="GreenLight"),
    make_address_record("TXT1", nickname="TrafficState"),
]
write_csv("traffic_light_nicknames.csv", nicknames)

# DataView CDV — defines a monitoring view
dataview = DataViewFile(
    rows=[
        make_dataview_record("TXT1"),
        make_dataview_record("C1"),
        make_dataview_record("C2"),
        make_dataview_record("C3"),
    ]
)
write_cdv("traffic_light_dataview.cdv", dataview)
```

The CSV file uses the same format as CLICK programming software's nickname export. The CDV file is a UTF-16 LE CSV that CLICK's DataView feature reads directly.

## Next steps

- [Client guide](../guides/client.md) — bank accessors, string addresses, and tag-based access
- [Types & values](../guides/types.md) — what Python types each bank returns
- [Addressing](../guides/addressing.md) — normalization, sparse X/Y ranges, XD/YD display indexing
- [Examples](../guides/examples.md) — full runnable scripts
