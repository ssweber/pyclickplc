# pyclickplc

Talk to AutomationDirect CLICK PLCs from Python. Read and write registers over Modbus TCP, simulate a PLC for local development, and read and write CLICK's files: nicknames, DataViews, PLC data dumps and Project.ini.

It's the wire under [pyrung](https://pyrung.com/pyrung/) and [ClickNick](https://pyrung.com/clicknick/), and it stands on its own as a Modbus client for any CLICK.

## Start here

The [quickstart](getting-started/quickstart.md) connects to a simulated PLC, reads and writes values, and generates project files. No hardware needed.

## Guides

| | |
|---|---|
| [Client](guides/client.md) | Read and write PLC values with `ClickClient` |
| [Types & values](guides/types.md) | Native Python types per bank family |
| [Addressing](guides/addressing.md) | Normalization, sparse X/Y ranges, XD/YD words |
| [Modbus Service](guides/modbus_service.md) | Sync + polling API for UI applications |
| [Server & simulator](guides/server.md) | Simulate a CLICK PLC with `ClickServer` |
| [File I/O](guides/files.md) | Nickname CSV, DataView CDV, PLC data dumps, Project.ini |
| [Examples](guides/examples.md) | Runnable scripts |

## API Reference

Auto-generated from source. See [API Reference overview](reference/index.md) for the full list.

## API stability

The public API is stable: client, service, server, file I/O, address, and validation. The low-level Modbus mapping helpers and bank metadata (`ModbusMapping`, `plc_to_modbus`, `BANKS`) may still change between minor versions.
