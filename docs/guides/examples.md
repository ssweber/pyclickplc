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

## Going further: ladder logic with pyrung

The traffic light above uses `asyncio.sleep` for timing — Python drives the state machine. A real CLICK PLC runs timer instructions in ladder logic. [pyrung](https://github.com/ssweber/pyrung) lets you write that logic in Python and simulate it scan-by-scan:

```python
from pyrung import Bool, Char, Int, Rung, on_delay, copy, program, Tms

State = Char("State")
GreenDone, GreenAcc = Bool("GreenDone"), Int("GreenAcc")

@program
def logic():
    with Rung(State == "g"):
        on_delay(GreenDone, GreenAcc, preset=3000, unit=Tms)
    with Rung(GreenDone):
        copy("y", State)
    # ... yellow → red → green
```

Under the hood, pyrung provides its own `DataProvider` that bridges ladder state to `ClickServer` — so any `ClickClient` or Modbus tool sees live, scan-driven values instead of Python-controlled ones.

See pyrung's [traffic light example](https://github.com/ssweber/pyrung/blob/main/examples/traffic_light.py) for the full version with timers, car counters, and deterministic scan stepping.
