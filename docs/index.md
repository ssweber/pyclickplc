# pyclickplc Docs

`pyclickplc` provides tools for AutomationDirect CLICK PLCs:

- Async Modbus TCP client (`ClickClient`)
- Sync + polling Modbus service (`ModbusService`)
- Modbus TCP simulator (`ClickServer`, `MemoryDataProvider`)
- Address parsing/normalization helpers
- CLICK nickname CSV and DataView CDV file I/O

## Start Here

- Use the `Core Usage` guides for task-oriented docs.
- Use `API Reference` for the versioned public API surface.
- `Advanced API` documents lower-level helpers that may evolve more quickly.

## v0.1 Stability Policy

- Stable core: client/service/server/file I/O/address/validation APIs.
- Evolving edges: low-level Modbus mapping helpers and bank metadata.

## Local Docs Commands

```bash
make docs-serve
make docs-build
```

