# Modbus Client

`ClickClient` reads and writes PLC values over Modbus TCP using native Python types.

```python
import asyncio
from pyclickplc import ClickClient

async def main():
    async with ClickClient("192.168.1.10", 502) as plc:
        await plc.ds.write(1, 100)
        ds1 = await plc.ds[1]
        print(ds1)  # 100

asyncio.run(main())
```

## Bank accessors

Every PLC bank has a typed accessor on the client:

```python
await plc.ds.write(1, 100)       # int
await plc.df.write(1, 3.14)      # float
await plc.y.write(1, True)       # bool
await plc.txt.write(1, "HELLO")  # str

ds1 = await plc.ds[1]            # single value
values = await plc.ds.read(1, 5) # range → ModbusResponse
```

Range reads return a `ModbusResponse`, which is a dict keyed by canonical normalized addresses:

```python
values = await plc.ds.read(1, 3)
# {"DS1": 100, "DS2": 200, "DS3": 300}

values["ds1"]   # 100 — lookups are case-insensitive
```

## String address interface

Read and write by address string when the bank isn't known at code time:

```python
await plc.addr.write("DS1", 100)
await plc.addr.write("df1", 3.14)  # case-insensitive
value = await plc.addr.read("C1")
```

## Tag interface

Load a nickname CSV and access values by tag name instead of address:

```python
from pyclickplc import ClickClient, read_csv

tags = read_csv("nicknames.csv")

async with ClickClient("192.168.1.10", 502, tags=tags) as plc:
    await plc.tag.write("TankTemp", 72.5)
    temp = await plc.tag.read("TankTemp")   # case-insensitive
```

Tags resolve to addresses through the nickname CSV mapping. See [File I/O](files.md) for CSV details.

## Error handling

- Type mismatches and invalid addresses raise `ValueError`.
- Transport/protocol failures raise `OSError`.

```python
try:
    await plc.ds.write(1, "not an int")  # ValueError
except ValueError as e:
    print(e)

try:
    value = await plc.ds[1]  # OSError if connection lost
except OSError as e:
    print(e)
```

## See also

- [Types & values](types.md) — what Python type each bank returns
- [Addressing](addressing.md) — normalization rules and edge cases
- [Modbus Service](modbus_service.md) — sync wrapper for UI applications
