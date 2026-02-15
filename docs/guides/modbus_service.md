# Modbus Service

`ModbusService` provides a synchronous API on top of `ClickClient` for UI and service callers that do not want to manage `asyncio` directly.

```python
from pyclickplc import ModbusService

def on_values(values):
    # Runs on the service thread.
    # GUI apps should marshal this callback to the UI thread.
    print(values)

svc = ModbusService(poll_interval_s=0.5, on_values=on_values)
svc.connect("192.168.1.10", 502, device_id=1, timeout=1)

svc.set_poll_addresses(["DS1", "DF1", "Y1"])
latest = svc.read(["DS1", "DF1"])
write_results = svc.write({"DS1": 10, "Y1": True})

svc.disconnect()
```

## API Notes

- `set_poll_addresses(addresses)` replaces the active poll set.
- `clear_poll_addresses()` clears the set.
- `stop_polling()` pauses polling until `set_poll_addresses(...)` is called again.
- `read(...)` returns `ModbusResponse` keyed by canonical uppercase addresses.
- `write(...)` accepts either a mapping or iterable of `(address, value)` pairs and returns per-address results.

## Error Semantics

- Invalid addresses/values at write-time are returned per address with `ok=False`.
- Invalid addresses passed to `read(...)` raise `ValueError`.
- Transport/protocol errors raise `OSError` for reads and are reported per-address for writes.
- `on_state` and `on_values` callbacks run on the service thread.
