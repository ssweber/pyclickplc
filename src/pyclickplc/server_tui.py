"""Minimal interactive terminal UI for ClickServer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .server import ClickServer


def _print_help(output_fn: Callable[[str], None]) -> None:
    output_fn("Commands:")
    output_fn("  help                 Show this command list")
    output_fn("  status               Show server status")
    output_fn("  clients              List connected clients")
    output_fn("  disconnect <id>      Disconnect one client")
    output_fn("  disconnect all       Disconnect all clients")
    output_fn("  shutdown             Stop server and exit (aliases: exit, quit)")


async def _read_line(prompt: str, input_fn: Callable[[str], str] | None) -> str:
    if input_fn is None:
        return await asyncio.to_thread(input, prompt)
    return input_fn(prompt)


async def run_server_tui(
    server: ClickServer,
    *,
    prompt: str = "clickserver> ",
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> None:
    """Run a basic interactive command loop for a ClickServer."""
    output = output_fn or print

    if not server.is_running():
        await server.start()

    output(f"Serving connection at {server.host}:{server.port}")
    output("Type 'help' for commands.")

    cancelled = False
    try:
        while True:
            try:
                raw = await _read_line(prompt, input_fn)
            except EOFError:
                output("EOF received, shutting down server.")
                break
            except KeyboardInterrupt:
                output("Interrupted, shutting down server.")
                break

            line = raw.strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()

            if cmd in {"shutdown", "exit", "quit"}:
                output("Shutting down server.")
                break

            if cmd == "help":
                _print_help(output)
                continue

            if cmd == "status":
                clients = server.list_clients()
                output(f"Serving connection at {server.host}:{server.port}")
                output(f"Running: {server.is_running()} | Clients: {len(clients)}")
                continue

            if cmd == "clients":
                clients = server.list_clients()
                if not clients:
                    output("No clients connected.")
                else:
                    for client in clients:
                        output(f"{client.client_id} {client.peer}")
                continue

            if cmd == "disconnect":
                if len(parts) != 2:
                    output("Usage: disconnect <client_id|all>")
                    continue
                target = parts[1]
                if target.lower() == "all":
                    count = server.disconnect_all_clients()
                    output(f"Disconnected {count} client(s).")
                elif server.disconnect_client(target):
                    output(f"Disconnected client '{target}'.")
                else:
                    output(f"Client '{target}' not found.")
                continue

            output(f"Unknown command: {cmd}. Type 'help' for commands.")
    except asyncio.CancelledError:
        cancelled = True
        output("TUI cancelled, shutting down server.")
    finally:
        await server.stop()

    if cancelled:
        raise asyncio.CancelledError
