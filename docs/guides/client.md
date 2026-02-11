# Modbus Client

`ClickClient` is the primary runtime API for reading and writing PLC values.

```python
import asyncio
from pyclickplc import ClickClient

async def main():
    async with ClickClient("192.168.1.10", 502) as plc:
        await plc.ds.write(1, 100)
        one_value = await plc.ds[1]
        many_values = await plc.ds.read(1, 5)

        await plc.addr.write("df1", 3.14)
        df1 = await plc.addr.read("df1")

asyncio.run(main())
```

## Access Patterns

- Bank accessors: `plc.ds`, `plc.df`, `plc.y`, etc.
- String addresses: `plc.addr.read("DS1")`, `plc.addr.write("C1", True)`
- Tags (with `tag_filepath`): `plc.tag.read("Name")`, `plc.tag.write("Name", value)`

