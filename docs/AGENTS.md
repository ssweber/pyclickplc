# pyclickplc Documentation — Agent Context

## What is pyclickplc

pyclickplc is a shared utility library for AutomationDirect CLICK PLCs. It provides a Modbus TCP client and server, PLC address parsing and normalization, nickname CSV and DataView CDV file I/O, and bank and register metadata. ClickNick (the GUI editor), pyrung (the simulator) and standalone tools use it.

## How to write the docs

Sentence style is in the Writing section of `../AGENTS.md`. These decisions are about what the docs contain.

- **Say what it does.** Do not use marketing words such as "powerful" or "elegant".
- **Code first.** Start with a working example and explain it afterwards. If the code is clear, do not restate it in prose.
- **One concept per section.** Keep paragraphs short and formatting minimal.
- **Simple to complex.** Every guide starts with the 80% use case and adds detail after that. Do not open a guide with edge cases.
- **Real scenarios, not API walkthroughs.** Write "Read a temperature register", not "Step 1: call read()."
- **Link, don't repeat.** If the types guide explains types, link to it.
- **Keep internals out of the guides.** A guide shows how to use the library. The API Reference gives the exhaustive details.
- **Pick the best pattern.** Teach one way to do a thing in a section. Put the alternatives in the reference docs.

## Audience

The readers are engineers who know CLICK PLCs and are learning the Python library. They know PLC concepts (addresses, banks, registers, coils). They do not know pymodbus or asyncio internals.

## Key technical details

- Every read and write API takes and returns native Python types (bool, int, float, str). None of them exposes raw Modbus registers.
- Address strings are case-insensitive on input. Output is normalized (`x1` → `X001`, `ds1` → `DS1`).
- `ClickClient` is async (asyncio). `ModbusService` wraps it for sync and UI callers.
- `ClickServer` simulates a CLICK PLC over Modbus TCP, so you need no hardware for development.
- Nickname CSV files have the same format as the ones CLICK programming software writes. DataView CDV files are UTF-16 LE CSV.
- X/Y are sparse address banks (slot-based hardware I/O). XD/YD use display indexing (0..8).
