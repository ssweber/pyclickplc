# Examples

Runnable scripts live in the repository `examples/` directory.

## Traffic Light Simulator

Source: [`examples/traffic_light.py`](https://github.com/ssweber/pyclickplc/blob/main/examples/traffic_light.py)

What it demonstrates:

- `ClickServer` + `MemoryDataProvider` simulation loop
- State transitions (`RED -> GREEN -> YELLOW`) via `bulk_set`
- Generating CLICK files:
  - `traffic_light_nicknames.csv`
  - `traffic_light_dataview.cdv`

Run:

```bash
uv run python examples/traffic_light.py
```

## Sync PLC Date/Time

Source: [`examples/sync_clickplc_datetime.py`](https://github.com/ssweber/pyclickplc/blob/main/examples/sync_clickplc_datetime.py)

What it demonstrates:

- Multi-PLC concurrent updates with `asyncio.gather`
- System register writes for date/time:
  - Date: `SD29`, `SD31`, `SD32`
  - Time: `SD34`, `SD35`, `SD36`
- SC trigger/error handshake:
  - Date apply: `SC53` trigger, `SC54` error
  - Time apply: `SC55` trigger, `SC56` error

Run:

```bash
uv run python examples/sync_clickplc_datetime.py
```

Set targets and datetime directly in the script footer:

```python
dt_now = datetime.now()
plc_ip_addresses = [
    # "192.168.1.10",
    # Add more IP addresses as needed.
]
```
