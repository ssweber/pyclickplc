# pyclickplc

Talk to AutomationDirect CLICK PLCs from Python. Read and write registers over Modbus TCP, simulate a PLC for local development, and manage CLICK nickname and DataView files.

## Start here

New to pyclickplc? The [quickstart](getting-started/quickstart.md) walks through connecting to a simulated PLC, reading and writing values, and generating project files — no hardware needed.

## Guides

| | |
|---|---|
| [Client](guides/client.md) | Read and write PLC values with `ClickClient` |
| [Types & values](guides/types.md) | Native Python types per bank family |
| [Addressing](guides/addressing.md) | Normalization, sparse X/Y ranges, XD/YD display indexing |
| [Modbus Service](guides/modbus_service.md) | Sync + polling API for UI applications |
| [Server & simulator](guides/server.md) | Simulate a CLICK PLC with `ClickServer` |
| [File I/O](guides/files.md) | Nickname CSV and DataView CDV read/write |
| [Examples](guides/examples.md) | Runnable scripts |

## API Reference

Auto-generated from source. See [API Reference overview](reference/index.md) for the full list.

## v0.1 Stability

- **Stable:** client, service, server, file I/O, address, and validation APIs.
- **Evolving:** low-level Modbus mapping helpers and bank metadata (`ModbusMapping`, `plc_to_modbus`, `BANKS`).
