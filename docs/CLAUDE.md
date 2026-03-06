# pyclickplc Documentation — Context for Claude

## What is pyclickplc

pyclickplc is a shared utility library for AutomationDirect CLICK PLCs. It provides Modbus TCP client/server, PLC address parsing and normalization, nickname CSV and DataView CDV file I/O, and bank/register metadata. Consumed by ClickNick (GUI editor), pyrung (simulation), and standalone tooling.

## Tone and style decisions

- **Direct, shows-don't-tells.** No marketing fluff, no "powerful" or "elegant." Say what it does.
- **Code speaks first.** Lead with a working example, explain after. If the code is clear, don't restate it in prose.
- **One concept per section.** Short paragraphs, minimal formatting. Don't pile concepts.
- **Simple to complex.** Every guide starts with the 80% use case, then adds nuance. Don't front-load edge cases.
- **Real scenarios, not API walkthroughs.** "Read a temperature register" not "Step 1: call read()."
- **Link, don't repeat.** If types are explained in the types guide, link to it. Don't re-explain.
- **Don't front-load internals.** Guides = how to use it. API Reference = exhaustive details. Keep them separate.
- **Pick the best pattern.** Don't teach two ways to do the same thing in the same section. Put alternatives in reference docs.

## Audience

Engineers who know CLICK PLCs, learning the Python library. Assume familiarity with PLC concepts (addresses, banks, registers, coils) but not with pymodbus or asyncio internals.

## Key technical details

- All read/write APIs use native Python types (bool, int, float, str) — never raw Modbus registers.
- Address strings are case-insensitive on input, canonical normalized on output (`x1` → `X001`, `ds1` → `DS1`).
- `ClickClient` is async (asyncio). `ModbusService` wraps it for sync/UI callers.
- `ClickServer` simulates a CLICK PLC over Modbus TCP — no hardware needed for development.
- Nickname CSV files are the same format CLICK programming software uses. DataView CDV files are UTF-16 LE CSV.
- X/Y are sparse address banks (slot-based hardware I/O). XD/YD use display indexing (0..8).
