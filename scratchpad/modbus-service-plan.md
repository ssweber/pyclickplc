# ModbusService Plan (pyclickplc)

## Goal

Add a `pyclickplc`-owned `ModbusService` that gives synchronous/UI callers a simple API for:

- live polling of a dynamic address set
- bulk writes of address/value pairs
- automatic batching and Modbus-efficient execution

This service must match existing `pyclickplc` ergonomics and error semantics used by `ClickClient` and `ClickServer`.

## Ergonomics Contract

Use the same conventions already established by `ClickClient`:

- Address inputs accept normal display strings and are canonicalized (`normalize_address`).
- Invalid addresses / invalid values / non-writable writes fail with `ValueError`.
- Modbus transport/protocol failures fail with `OSError`.
- Read results are normalized mappings keyed by canonical uppercase addresses.
- API names stay action-oriented and explicit (`read`, `write`, `connect`, `disconnect`).

## Public API

New module: `src/pyclickplc/modbus_service.py`

```python
from collections.abc import Callable, Iterable, Mapping
from enum import Enum

PlcValue = bool | int | float | str

class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class WriteResult(TypedDict):
    address: str
    ok: bool
    error: str | None

class ModbusService:
    def __init__(
        self,
        poll_interval_s: float = 1.5,
        on_state: Callable[[ConnectionState, Exception | None], None] | None = None,
        on_values: Callable[[ModbusResponse[PlcValue]], None] | None = None,
    ) -> None: ...

    # Lifecycle
    def connect(self, host: str, port: int = 502, *, device_id: int = 1, timeout: int = 1) -> None: ...
    def disconnect(self) -> None: ...

    # Poll configuration (replace semantics)
    def set_poll_addresses(self, addresses: Iterable[str]) -> None: ...
    def clear_poll_addresses(self) -> None: ...
    def stop_polling(self) -> None: ...

    # Sync convenience operations
    def read(self, addresses: Iterable[str]) -> ModbusResponse[PlcValue]: ...
    def write(self, values: Mapping[str, PlcValue] | Iterable[tuple[str, PlcValue]]) -> list[WriteResult]: ...
```

Notes:

- `set_poll_addresses(...)` means "replace current poll set", not incremental subscribe.
- `write(...)` accepts either mapping or iterable for ergonomic parity with existing APIs.
- `write(...)` returns per-address outcomes to support partial success reporting in UIs.

## Internal Design

1. Thread + event loop bridge
- One background daemon thread owns one asyncio event loop.
- A readiness event gates scheduling work until loop is initialized.
- `connect()`/`disconnect()`/`set_poll_addresses()`/`read()`/`write()` schedule coroutines with thread-safe submission and wait only when required (`read`, `write`).

2. Client ownership
- Service owns one `ClickClient` instance while connected.
- Use async context lifecycle semantics equivalent to `ClickClient.__aenter__/__aexit__`.

3. Polling model
- Poll loop runs only when connected and poll set is non-empty.
- Each cycle reads current poll set, performs bank-batched reads, emits one merged `ModbusResponse`.
- `set_poll_addresses(...)` is atomic replacement and takes effect next poll cycle.

4. Batch planning
- Parse/normalize addresses once per plan update.
- Group by bank.
- Build contiguous spans where efficient and legal.
- Respect sparse bank behavior (`X`/`Y`) and width-2 banks (`DD`/`DF`/`CTD`).
- Respect Modbus limits per call (max coil/register count).

5. Write execution
- Normalize/validate each address and value using existing `ClickClient` semantics.
- Coalesce consecutive writes by bank/type where safe; fallback to per-address writes when needed.
- Return `WriteResult` per requested address in original input order.

6. Callback delivery
- `on_state` and `on_values` are invoked from the service thread.
- GUI consumers must marshal to UI thread (`widget.after(...)` in Tk).

## Integration Points

1. Exports
- Add `ModbusService`, `ConnectionState`, and `WriteResult` to `src/pyclickplc/__init__.py`.

2. Docs
- Update `README.md` quickstart with one `ModbusService` polling/write example.
- Add `docs/guides/modbus_service.md`.
- Link from `docs/index.md` and include error semantics.

## Tests

New test file: `tests/test_modbus_service.py`

1. Lifecycle/state
- DISCONNECTED -> CONNECTING -> CONNECTED -> DISCONNECTED.
- connection failure -> ERROR with callback payload.

2. Poll configuration
- `set_poll_addresses(...)` replaces set.
- `clear_poll_addresses()` empties set.
- polling stops when no addresses.

3. Read behavior
- `read([...])` returns `ModbusResponse` with canonical keys.
- invalid addresses raise `ValueError`.
- transport errors raise `OSError`.

4. Write behavior
- accepts mapping and iterable inputs.
- non-writable address result marked failed (`ok=False`, error message).
- invalid value gives failed result and does not crash service.
- transport failure produces failed result with error text.

5. Batching heuristics
- group-by-bank and contiguous range choices are deterministic.
- sparse bank handling does not bridge invalid gaps incorrectly.
- width-2 banks honor register width when building spans.

6. Thread safety
- concurrent `set_poll_addresses(...)` during poll does not crash.
- `disconnect()` during active poll exits cleanly.

## Acceptance Criteria

- `ModbusService` API is stable and documented in `pyclickplc`.
- Read/write behavior matches `ClickClient` conventions (normalization + exceptions).
- Poll set replacement via `set_poll_addresses(...)` works without reconnecting.
- Write results provide per-address outcome for UI-level reporting.
- New tests pass under `make test`.
