"""Tests for pyclickplc.server_tui."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pyclickplc.server import ClickServer, ServerClientInfo
from pyclickplc.server_tui import run_server_tui


@dataclass
class _FakeServer:
    host: str = "127.0.0.1"
    port: int = 5020
    running: bool = False
    clients: list[ServerClientInfo] | None = None
    disconnect_all_count: int = 0
    disconnect_ok: bool = False

    def __post_init__(self) -> None:
        if self.clients is None:
            self.clients = []
        self.start_calls = 0
        self.stop_calls = 0
        self.disconnect_all_calls = 0
        self.disconnect_client_calls: list[str] = []

    def is_running(self) -> bool:
        return self.running

    async def start(self) -> None:
        self.start_calls += 1
        self.running = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.running = False

    def list_clients(self) -> list[ServerClientInfo]:
        return list(self.clients or [])

    def disconnect_all_clients(self) -> int:
        self.disconnect_all_calls += 1
        return self.disconnect_all_count

    def disconnect_client(self, client_id: str) -> bool:
        self.disconnect_client_calls.append(client_id)
        return self.disconnect_ok


def _input_from(values: list[str]):
    queue = list(values)

    def _input(_: str) -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    return _input


async def test_run_server_tui_status_help_shutdown():
    server = _FakeServer()
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["status", "help", "shutdown"]),
        output_fn=output.append,
    )

    assert server.start_calls == 1
    assert server.stop_calls == 1
    assert any("Serving connection at 127.0.0.1:5020" in line for line in output)
    assert any("Running: True | Clients: 0" in line for line in output)
    assert any("Commands:" in line for line in output)


async def test_run_server_tui_clients_empty():
    server = _FakeServer()
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["clients", "shutdown"]),
        output_fn=output.append,
    )

    assert "No clients connected." in output


async def test_run_server_tui_disconnect_all():
    server = _FakeServer(disconnect_all_count=3)
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["disconnect all", "shutdown"]),
        output_fn=output.append,
    )

    assert server.disconnect_all_calls == 1
    assert "Disconnected 3 client(s)." in output


async def test_run_server_tui_disconnect_single_success():
    server = _FakeServer(disconnect_ok=True)
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["disconnect abc", "shutdown"]),
        output_fn=output.append,
    )

    assert server.disconnect_client_calls == ["abc"]
    assert "Disconnected client 'abc'." in output


async def test_run_server_tui_disconnect_single_not_found():
    server = _FakeServer(disconnect_ok=False)
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["disconnect missing", "shutdown"]),
        output_fn=output.append,
    )

    assert server.disconnect_client_calls == ["missing"]
    assert "Client 'missing' not found." in output


async def test_run_server_tui_unknown_command():
    server = _FakeServer()
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server),
        input_fn=_input_from(["badcmd", "shutdown"]),
        output_fn=output.append,
    )

    assert any("Unknown command: badcmd." in line for line in output)


async def test_run_server_tui_eof_triggers_stop():
    server = _FakeServer()
    output: list[str] = []

    def _eof(_: str) -> str:
        raise EOFError

    await run_server_tui(cast(ClickServer, server), input_fn=_eof, output_fn=output.append)

    assert server.stop_calls == 1
    assert "EOF received, shutting down server." in output


async def test_run_server_tui_keyboard_interrupt_triggers_stop():
    server = _FakeServer()
    output: list[str] = []

    def _interrupt(_: str) -> str:
        raise KeyboardInterrupt

    await run_server_tui(cast(ClickServer, server), input_fn=_interrupt, output_fn=output.append)

    assert server.stop_calls == 1
    assert "Interrupted, shutting down server." in output


async def test_run_server_tui_does_not_restart_running_server():
    server = _FakeServer(running=True)
    output: list[str] = []

    await run_server_tui(
        cast(ClickServer, server), input_fn=_input_from(["shutdown"]), output_fn=output.append
    )

    assert server.start_calls == 0
    assert server.stop_calls == 1
