# Handoff: pyclickplc Implementation Order

See `ARCHITECTURE.md` for full module layout, dependency graph, and design decisions.

---

## Starting Point

- pyclickplc: empty `src/pyclickplc/__init__.py`, no code yet
- ClickNick: working app, Phase 0 (unique block names) done
- Specs written: `CLICKDEVICE_SPEC.md` (client), `CLICKSERVER_SPEC.md` (server)

## Step 1: `banks.py` + `addresses.py` in pyclickplc

Build the foundation directly in pyclickplc — don't fix ClickNick first.

- `BankConfig` frozen dataclass with `valid_ranges` for sparse X/Y
- `DataType` enum (canonical, from ClickNick's existing `DataType`)
- All bank definitions (`BANKS` dict)
- Address parsing/formatting functions (one parser, shared by all consumers)
- Sparse address validation using `valid_ranges`
- `AddressRecord` frozen dataclass
- `validation.py` (nickname/comment/initial value rules)

Test thoroughly — this is the foundation everything else builds on.

## Step 2: Wire ClickNick to pyclickplc

- Replace `from ..models.constants import ADDRESS_RANGES, DataType, ...` with pyclickplc imports
- Update ClickNick's X/Y display to filter using `BankConfig.valid_ranges`
- Delete moved code from ClickNick's `constants.py` and `address_row.py`
- Run ClickNick's existing tests to verify nothing broke

## Step 3: `blocks.py` + `nicknames.py` + `dataview.py`

Extract remaining ClickNick shared code into pyclickplc:

- BlockTag system → `blocks.py`
- CSV read/write → `nicknames.py`
- CDV file I/O → `dataview.py`
- Update ClickNick imports, delete moved code

## Step 4: `modbus.py`

New code — Modbus protocol mapping layer:

- `ModbusMapping` definitions for all banks (XD/YD pending hardware testing)
- Forward/reverse address mapping
- Register packing/unpacking
- Sparse coil offset calculation (reads `valid_ranges` from `BankConfig`)

Can be developed in parallel with Step 3.

## Step 5: `client.py` + `server.py`

New code per the existing specs:

- `ClickDriver` (Modbus TCP client) per `CLICKDEVICE_SPEC.md`
- `ClickServer` (Modbus TCP server) per `CLICKSERVER_SPEC.md`
- Integration tests: driver ↔ server round-trips
