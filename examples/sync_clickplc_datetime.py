#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyclickplc",
# ]
# ///

from __future__ import annotations

import asyncio
from datetime import datetime

from pyclickplc import ClickClient


async def sync_click_datetime(
    plc_ip: str,
    dt: datetime,
    *,
    settle_seconds: float = 1.0,
) -> None:
    try:
        # Extract components from the provided datetime object.
        year = dt.year
        month = dt.month
        day = dt.day
        hour = dt.hour
        minute = dt.minute
        second = dt.second

        # Connect to the PLC.
        async with ClickClient(plc_ip) as plc:
            print(f"Connecting to PLC at {plc_ip}...")

            # Set the date (SD29, SD31, SD32).
            await plc.sd.write(29, year)
            await plc.sd.write(31, month)
            await plc.sd.write(32, day)

            # Turn SC53 ON to update date and check SC54 for errors.
            await plc.sc.write(53, True)
            await asyncio.sleep(settle_seconds)
            sc54_status = await plc.sc[54]
            if sc54_status:
                print(f"Error: Date update failed for PLC at {plc_ip} (SC54 is ON).")
            else:
                print(f"Date update successful for PLC at {plc_ip} (SC54 is OFF).")
            await plc.sc.write(53, False)

            # Set the time (SD34, SD35, SD36).
            await plc.sd.write(34, hour)
            await plc.sd.write(35, minute)
            await plc.sd.write(36, second)

            # Turn SC55 ON to update time and check SC56 for errors.
            await plc.sc.write(55, True)
            await asyncio.sleep(settle_seconds)
            sc56_status = await plc.sc[56]
            if sc56_status:
                print(f"Error: Time update failed for PLC at {plc_ip} (SC56 is ON).")
            else:
                print(f"Time update successful for PLC at {plc_ip} (SC56 is OFF).")
            await plc.sc.write(55, False)

            print(
                f"Date and time set to {year:04}-{month:02}-{day:02} "
                f"{hour:02}:{minute:02}:{second:02} for PLC at {plc_ip}"
            )
    except Exception as exc:
        print(f"An error occurred with PLC at {plc_ip}: {exc}")


async def update_multiple_plcs(
    plc_ips: list[str],
    dt: datetime,
    *,
    settle_seconds: float,
) -> None:
    tasks = [sync_click_datetime(ip, dt, settle_seconds=settle_seconds) for ip in plc_ips]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    dt_now = datetime.now()
    plc_ip_addresses = [
        # "192.168.1.10",
        # Add more IP addresses as needed.
    ]
    asyncio.run(update_multiple_plcs(plc_ip_addresses, dt_now, settle_seconds=1.0))
