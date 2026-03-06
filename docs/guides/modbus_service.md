# Modbus Service

`ModbusService` wraps `ClickClient` for applications that don't want to manage an async loop — GUI apps, services, or anything that needs synchronous reads and background polling.

```python
from pyclickplc import ModbusService, ReconnectConfig

def on_values(values):
    print(values)  # ModbusResponse keyed by canonical addresses

svc = ModbusService(
    poll_interval_s=0.5,
    reconnect=ReconnectConfig(delay_s=0.5, max_delay_s=5.0),
    on_values=on_values,
)
svc.connect("192.168.1.10", 502, device_id=1, timeout=1)

svc.set_poll_addresses(["DS1", "DF1", "Y1"])
print(svc.read(["DS1", "DF1"]))
print(svc.write({"DS1": 10, "Y1": True}))

svc.disconnect()
```

## Polling lifecycle

- `set_poll_addresses(addresses)` — start polling these addresses. Replaces any previous set.
- `clear_poll_addresses()` — stop polling, clear the set.
- `stop_polling()` — pause polling. Resumes when you call `set_poll_addresses` again.
- `disconnect()` (or `close()`) — fully stop the background loop and thread.

The next sync call (`connect`, `read`, `write`, etc.) restarts the loop automatically.

## Read and write

- `read(addresses)` returns a `ModbusResponse` keyed by canonical normalized addresses.
- `write(values)` accepts a mapping or iterable of `(address, value)` pairs. Returns per-address `WriteResult` entries with `ok` and `error` fields — non-writable or invalid addresses get an error result instead of raising.

## Callbacks and threading

`on_values` and `on_state` callbacks run on the service thread, not the main thread. GUI apps should marshal callback data to the UI thread before updating widgets.

Do not call `connect`, `disconnect`, `read`, `write`, or poll config methods from inside a callback — this will deadlock.

## Error handling

- Invalid addresses passed to `read(...)` raise `ValueError`.
- Transport/protocol errors raise `OSError` for reads.
- Write errors are reported per-address in the `WriteResult` (no exception raised).

## See also

- [Client guide](client.md) — async API for direct `asyncio` use
- [Types & values](types.md) — native types and validation rules
- [Addressing](addressing.md) — normalization and sparse ranges
