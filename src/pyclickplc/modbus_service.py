"""Synchronous Modbus service for UI callers.

`ModbusService` wraps `ClickClient` in a background asyncio loop so callers can:
- connect/disconnect synchronously
- poll a replaceable set of addresses
- perform synchronous batched reads/writes
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict, TypeVar, cast

from .addresses import normalize_address, parse_address
from .banks import BANKS, DataType
from .client import ClickClient, ModbusResponse
from .modbus import MODBUS_MAPPINGS
from .validation import assert_runtime_value

PlcValue = bool | int | float | str

MAX_READ_COILS = 2000
MAX_READ_REGISTERS = 125
MAX_WRITE_COILS = 1968
MAX_WRITE_REGISTERS = 123
T = TypeVar("T")


class ConnectionState(Enum):
    """Connection state notifications emitted by ModbusService."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class WriteResult(TypedDict):
    """Per-address write outcome."""

    address: str
    ok: bool
    error: str | None


@dataclass(frozen=True)
class _ReadSpan:
    bank: str
    start: int
    end: int


@dataclass(frozen=True)
class _PollConfig:
    addresses: tuple[str, ...]
    plan: tuple[_ReadSpan, ...]
    enabled: bool


@dataclass(frozen=True)
class _WriteItem:
    pos: int
    normalized: str
    bank: str
    index: int
    value: PlcValue


@dataclass(frozen=True)
class _WriteBatch:
    bank: str
    items: tuple[_WriteItem, ...]


def _default_for_bank(bank: str) -> PlcValue:
    data_type = BANKS[bank].data_type
    if data_type == DataType.BIT:
        return False
    if data_type == DataType.FLOAT:
        return 0.0
    if data_type == DataType.TXT:
        return "\x00"
    return 0


def _is_writable(bank: str, index: int) -> bool:
    mapping = MODBUS_MAPPINGS[bank]
    if mapping.writable is not None:
        return index in mapping.writable
    return mapping.is_writable


def _modbus_count_for_span(bank: str, start: int, end: int) -> int:
    if end < start:
        raise ValueError("end must be >= start")

    mapping = MODBUS_MAPPINGS[bank]
    if mapping.is_coil:
        return end - start + 1

    if bank == "TXT":
        first = (start - 1) // 2
        last = (end - 1) // 2
        return last - first + 1

    return (end - start + 1) * mapping.width


def _max_span_count(bank: str, *, for_write: bool) -> int:
    mapping = MODBUS_MAPPINGS[bank]
    if mapping.is_coil:
        return MAX_WRITE_COILS if for_write else MAX_READ_COILS
    return MAX_WRITE_REGISTERS if for_write else MAX_READ_REGISTERS


def _build_spans(bank: str, indices: Iterable[int], *, for_write: bool) -> list[_ReadSpan]:
    sorted_indices = sorted(set(indices))
    if not sorted_indices:
        return []

    spans: list[_ReadSpan] = []
    limit = _max_span_count(bank, for_write=for_write)
    start = sorted_indices[0]
    prev = start

    for idx in sorted_indices[1:]:
        contiguous = idx == prev + 1
        within_limit = _modbus_count_for_span(bank, start, idx) <= limit
        if contiguous and within_limit:
            prev = idx
            continue

        spans.append(_ReadSpan(bank=bank, start=start, end=prev))
        start = idx
        prev = idx

    spans.append(_ReadSpan(bank=bank, start=start, end=prev))
    return spans


def _normalize_addresses_for_read(
    addresses: Iterable[str],
) -> tuple[list[str], dict[str, tuple[str, int]]]:
    ordered: list[str] = []
    parsed: dict[str, tuple[str, int]] = {}
    seen: set[str] = set()
    for address in addresses:
        if not isinstance(address, str):
            raise ValueError(f"Invalid address format: {address!r}")
        normalized = normalize_address(address)
        if normalized is None:
            raise ValueError(f"Invalid address format: {address!r}")
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
            parsed[normalized] = parse_address(normalized)
    return ordered, parsed


def _build_read_plan(
    ordered: Iterable[str], parsed: Mapping[str, tuple[str, int]]
) -> list[_ReadSpan]:
    by_bank: dict[str, list[int]] = {}
    for address in ordered:
        bank, index = parsed[address]
        by_bank.setdefault(bank, []).append(index)

    plan: list[_ReadSpan] = []
    for bank, indices in by_bank.items():
        plan.extend(_build_spans(bank, indices, for_write=False))
    return plan


class ModbusService:
    """Synchronous wrapper over ClickClient with background polling."""

    def __init__(
        self,
        poll_interval_s: float = 1.5,
        on_state: Callable[[ConnectionState, Exception | None], None] | None = None,
        on_values: Callable[[ModbusResponse[PlcValue]], None] | None = None,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be > 0")

        self._poll_interval_s = poll_interval_s
        self._on_state = on_state
        self._on_values = on_values

        self._state = ConnectionState.DISCONNECTED
        self._client: ClickClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_config = _PollConfig(addresses=(), plan=(), enabled=True)

        self._thread_lock = threading.Lock()
        self._loop_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._start_loop_thread()

    # Lifecycle --------------------------------------------------------------

    def connect(
        self,
        host: str,
        port: int = 502,
        *,
        device_id: int = 1,
        timeout: int = 1,
    ) -> None:
        self._submit_wait(self._connect_async(host, port, device_id=device_id, timeout=timeout))

    def disconnect(self) -> None:
        thread = self._thread
        if thread is None:
            return

        try:
            self._submit_wait(self._disconnect_async())
        finally:
            if threading.current_thread() is not thread:
                self._stop_loop_thread()

    def close(self) -> None:
        self.disconnect()

    # Poll configuration -----------------------------------------------------

    def set_poll_addresses(self, addresses: Iterable[str]) -> None:
        normalized, parsed = _normalize_addresses_for_read(addresses)
        plan = _build_read_plan(normalized, parsed)
        self._submit_wait(self._set_poll_config_async(tuple(normalized), tuple(plan), enabled=True))

    def clear_poll_addresses(self) -> None:
        self._submit_wait(self._set_poll_config_async((), (), enabled=True))

    def stop_polling(self) -> None:
        self._submit_wait(
            self._set_poll_config_async(
                self._poll_config.addresses,
                self._poll_config.plan,
                enabled=False,
            )
        )

    # Sync operations --------------------------------------------------------

    def read(self, addresses: Iterable[str]) -> ModbusResponse[PlcValue]:
        normalized, parsed = _normalize_addresses_for_read(addresses)
        plan = _build_read_plan(normalized, parsed)
        result = self._submit_wait(self._read_plan_async(plan))
        ordered_result: dict[str, PlcValue] = {}
        for address in normalized:
            ordered_result[address] = result.get(address, _default_for_bank(parsed[address][0]))
        return ModbusResponse(ordered_result)

    def write(
        self,
        values: Mapping[str, PlcValue] | Iterable[tuple[str, PlcValue]],
    ) -> list[WriteResult]:
        items: list[tuple[object, object]]
        if isinstance(values, Mapping):
            items = list(values.items())
        else:
            items = list(values)

        return self._submit_wait(self._write_async(items))

    # Internal loop bridge ---------------------------------------------------

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            with self._thread_lock:
                if self._thread is threading.current_thread():
                    self._loop = None

    def _start_loop_thread(self) -> None:
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._loop_ready = threading.Event()
            self._loop = None
            self._thread = threading.Thread(
                target=self._run_loop, name="pyclickplc-modbus-service", daemon=True
            )
            self._thread.start()

        if not self._loop_ready.wait(timeout=5):
            raise RuntimeError("ModbusService event loop thread failed to start")

    def _ensure_loop_thread(self) -> None:
        with self._thread_lock:
            thread = self._thread
            loop = self._loop
            ready = self._loop_ready

        if thread is None or not thread.is_alive() or loop is None or loop.is_closed():
            self._start_loop_thread()
            return

        if not ready.is_set() and not ready.wait(timeout=5):
            raise RuntimeError("ModbusService event loop thread failed to start")

    def _stop_loop_thread(self) -> None:
        with self._thread_lock:
            thread = self._thread
            loop = self._loop

        if thread is None:
            return
        if threading.current_thread() is thread:
            raise RuntimeError(
                "Synchronous ModbusService methods cannot be called from service callbacks"
            )

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)

        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("ModbusService event loop thread failed to stop")

        with self._thread_lock:
            if self._thread is thread:
                self._thread = None
            if self._loop is loop:
                self._loop = None

    def _submit_wait(self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            self._ensure_loop_thread()
        except Exception:
            coro.close()
            raise

        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            coro.close()
            raise RuntimeError("Service event loop is not available")
        if threading.current_thread() is thread:
            coro.close()
            raise RuntimeError(
                "Synchronous ModbusService methods cannot be called from service callbacks"
            )
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def __del__(self) -> None:
        try:
            self._stop_loop_thread()
        except Exception:
            return

    # Async implementation ---------------------------------------------------

    async def _connect_async(
        self,
        host: str,
        port: int,
        *,
        device_id: int,
        timeout: int,
    ) -> None:
        if self._client is not None:
            await self._disconnect_async()

        self._emit_state(ConnectionState.CONNECTING, None)
        candidate: ClickClient | None = None
        try:
            candidate = ClickClient(host, port, timeout=timeout, device_id=device_id)
            await candidate.__aenter__()
            if not candidate._client.connected:  # pyright: ignore[reportPrivateUsage]
                raise OSError(f"Failed to connect to {host}:{port}")
            self._client = candidate
            self._ensure_poll_task()
            self._emit_state(ConnectionState.CONNECTED, None)
        except Exception as exc:
            if candidate is not None:
                await candidate.__aexit__(None, None, None)
            if isinstance(exc, (OSError, ValueError)):
                self._emit_state(ConnectionState.ERROR, exc)
                raise

            wrapped = OSError(str(exc))
            self._emit_state(ConnectionState.ERROR, wrapped)
            raise wrapped from exc

    async def _disconnect_async(self) -> None:
        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None:
            poll_task.cancel()
            await asyncio.gather(poll_task, return_exceptions=True)

        client = self._client
        self._client = None
        if client is not None:
            await client.__aexit__(None, None, None)

        self._emit_state(ConnectionState.DISCONNECTED, None)

    async def _set_poll_config_async(
        self,
        addresses: tuple[str, ...],
        plan: tuple[_ReadSpan, ...],
        *,
        enabled: bool,
    ) -> None:
        self._poll_config = _PollConfig(addresses=addresses, plan=plan, enabled=enabled)

    def _ensure_poll_task(self) -> None:
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop(), name="pyclickplc-poll-loop")

    async def _poll_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._poll_interval_s)

                if self._client is None:
                    continue

                poll_config = self._poll_config
                if not poll_config.enabled or not poll_config.addresses:
                    continue

                try:
                    data = await self._read_plan_async(list(poll_config.plan))
                except OSError as exc:
                    self._emit_state(ConnectionState.ERROR, exc)
                    continue

                ordered: dict[str, PlcValue] = {}
                for address in poll_config.addresses:
                    ordered[address] = data[address]

                if self._on_values is not None:
                    try:
                        self._on_values(ModbusResponse(ordered))
                    except Exception:
                        continue
        except asyncio.CancelledError:
            return

    async def _read_plan_async(self, plan: list[_ReadSpan]) -> dict[str, PlcValue]:
        client = self._client
        if client is None:
            raise OSError("Not connected")

        merged: dict[str, PlcValue] = {}
        for span in plan:
            accessor = client._get_accessor(span.bank)  # pyright: ignore[reportPrivateUsage]
            if span.start == span.end:
                response = await accessor.read(span.start)
            else:
                response = await accessor.read(span.start, span.end)
            merged.update(response)
        return merged

    async def _write_async(self, items: list[tuple[object, object]]) -> list[WriteResult]:
        if not items:
            return []

        results: list[WriteResult] = [
            {"address": str(addr), "ok": False, "error": None} for addr, _ in items
        ]

        validated: list[_WriteItem] = []
        for pos, (address, value) in enumerate(items):
            if not isinstance(address, str):
                results[pos] = {
                    "address": str(address),
                    "ok": False,
                    "error": "Invalid address format",
                }
                continue
            normalized = normalize_address(address)
            if normalized is None:
                results[pos] = {
                    "address": str(address),
                    "ok": False,
                    "error": "Invalid address format",
                }
                continue

            bank, index = parse_address(normalized)

            if not _is_writable(bank, index):
                results[pos] = {
                    "address": normalized,
                    "ok": False,
                    "error": f"{bank}{index} is not writable.",
                }
                continue

            try:
                assert_runtime_value(BANKS[bank].data_type, value, bank=bank, index=index)
            except ValueError as exc:
                results[pos] = {"address": normalized, "ok": False, "error": str(exc)}
                continue

            validated.append(
                _WriteItem(
                    pos=pos,
                    normalized=normalized,
                    bank=bank,
                    index=index,
                    value=cast(PlcValue, value),
                )
            )

        batches = self._build_write_batches(validated)
        client = self._client
        if client is None:
            error_text = "Not connected"
            for item in validated:
                results[item.pos] = {"address": item.normalized, "ok": False, "error": error_text}
            return results

        for batch in batches:
            accessor = client._get_accessor(batch.bank)  # pyright: ignore[reportPrivateUsage]
            try:
                if len(batch.items) == 1:
                    one = batch.items[0]
                    await accessor.write(one.index, one.value)
                else:
                    start = batch.items[0].index
                    values = [item.value for item in batch.items]
                    payload = cast(
                        "list[bool] | list[int] | list[float] | list[str]",
                        values,
                    )
                    await accessor.write(start, payload)

                for item in batch.items:
                    results[item.pos] = {"address": item.normalized, "ok": True, "error": None}
            except (OSError, ValueError) as exc:
                for item in batch.items:
                    results[item.pos] = {"address": item.normalized, "ok": False, "error": str(exc)}

        return results

    def _build_write_batches(self, items: list[_WriteItem]) -> list[_WriteBatch]:
        if not items:
            return []

        batches: list[_WriteBatch] = []
        current: list[_WriteItem] = [items[0]]

        for item in items[1:]:
            prev = current[-1]
            same_bank = item.bank == prev.bank
            contiguous_index = item.index == prev.index + 1
            contiguous_input_order = item.pos == prev.pos + 1

            if same_bank and contiguous_index and contiguous_input_order:
                start_index = current[0].index
                if _modbus_count_for_span(item.bank, start_index, item.index) <= _max_span_count(
                    item.bank, for_write=True
                ):
                    current.append(item)
                    continue

            batches.append(_WriteBatch(bank=current[0].bank, items=tuple(current)))
            current = [item]

        batches.append(_WriteBatch(bank=current[0].bank, items=tuple(current)))
        return batches

    def _emit_state(self, state: ConnectionState, error: Exception | None) -> None:
        if state is self._state and error is None:
            return
        self._state = state
        if self._on_state is not None:
            try:
                self._on_state(state, error)
            except Exception:
                return
