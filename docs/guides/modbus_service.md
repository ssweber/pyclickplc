# Modbus Service

`ModbusService` provides a synchronous API on top of `ClickClient` for UI and service callers that do not want to manage `asyncio` directly.

```python
from pyclickplc import ModbusService, ReconnectConfig

def on_values(values):
    # Runs on the service thread.
    # GUI apps should marshal this callback to the UI thread.
    print(values)

svc = ModbusService(
    poll_interval_s=0.5,
    reconnect=ReconnectConfig(delay_s=0.5, max_delay_s=5.0),  # optional
    on_values=on_values,
)
svc.connect("192.168.1.10", 502, device_id=1, timeout=1)

svc.set_poll_addresses(["DS1", "DF1", "Y1"])
latest = svc.read(["DS1", "DF1"])
write_results = svc.write({"DS1": 10, "Y1": True})

svc.close()  # same as disconnect()
```

## API Notes

- `set_poll_addresses(addresses)` replaces the active poll set.
- `clear_poll_addresses()` clears the set.
- `stop_polling()` pauses polling until `set_poll_addresses(...)` is called again.
- `read(...)` returns `ModbusResponse` keyed by canonical uppercase addresses.
- `write(...)` accepts either a mapping or iterable of `(address, value)` pairs and returns per-address results.
- `disconnect()` (or `close()`) fully stops the background service loop/thread.
- The next sync call (`connect`, `read`, `write`, etc.) will start the loop again.
- `reconnect=ReconnectConfig(...)` controls ClickClient auto-reconnect backoff.

## Error Semantics and Thread Safety

- Invalid addresses/values at write-time are returned per address with `ok=False`.
- Invalid addresses passed to `read(...)` raise `ValueError`.
- Transport/protocol errors raise `OSError` for reads and are reported per-address for writes.
- `on_state` and `on_values` callbacks run on the service thread.
- Do not call synchronous service methods (`connect`, `disconnect`, `read`, `write`, poll config methods) from these callbacks. Marshal work to another thread/UI loop.

## Related Guides

- Native value rules and write validation: [`guides/types.md`](types.md)
- Address parsing/normalization rules: [`guides/addressing.md`](addressing.md)
