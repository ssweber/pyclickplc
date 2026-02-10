# Client + Server Min/Max Validation Plan

## Goal

Enforce one runtime write contract across pyclickplc:

- Reject invalid values on client writes.
- Reject invalid values in `MemoryDataProvider.write()` / `set()`.
- Do not add a permissive or compatibility mode.

This project is unreleased, so we optimize for a clean contract instead of migration paths.

## Decision Summary

- `HEX` uses IEC WORD semantics: unsigned 16-bit `0..65535` (`0x0000..0xFFFF`).
- Numeric bank validation is explicit (not only implicit `struct.pack` failures).
- Bool-as-int is rejected for numeric banks (`DS`, `DD`, `DH`, `TD`, `CTD`, `SD`, `XD`, `YD`, `DF`).
- `DF` rejects non-finite values (`NaN`, `+Inf`, `-Inf`) and values not representable in float32.
- `TXT` allows blank (`""`) or a single ASCII character (including space `" "`).

## Implementation Plan

1. Add shared runtime value validation helper
- File: `src/pyclickplc/validation.py`
- Add an assertion-style API for runtime write validation keyed by `DataType`.
- Keep existing nickname/comment/initial-value validation intact.

2. Use shared validation in client write path
- File: `src/pyclickplc/client.py`
- Replace `_validate_type()` with `_validate_value()` (type + range + format).
- Keep existing index and writability checks unchanged.
- Raise deterministic `ValueError` messages for invalid values.

3. Validate in `MemoryDataProvider`
- File: `src/pyclickplc/server.py`
- In `write()`, normalize address, resolve bank/type, validate value, then store.
- `set()` and `bulk_set()` inherit strict validation through `write()`.
- No constructor flags for permissive behavior.

4. Keep Modbus server writability behavior unchanged
- `SC` and `SD` writability remains enforced by server request handling.
- Provider validation is value-centric, not Modbus function-code authorization.

## Runtime Validation Matrix

- `BIT`: `type(value) is bool`
- `INT` (`DS`, `TD`, `SD`): `type(value) is int`, range `-32768..32767`
- `INT2` (`DD`, `CTD`): `type(value) is int`, range `-2147483648..2147483647`
- `HEX` (`DH`, `XD`, `YD`): `type(value) is int`, range `0..65535`
- `FLOAT` (`DF`): numeric (`int`/`float`, not bool), finite, packable as float32
- `TXT`: `type(value) is str`, and either:
  - blank string `""`, or
  - length `1` ASCII char (`ord <= 127`)

## Tests To Add/Update

1. Client write rejections
- `plc.ds.write(1, 32768)` -> `ValueError`
- `plc.dd.write(1, 2147483648)` -> `ValueError`
- `plc.dh.write(1, -1)` -> `ValueError`
- `plc.ds.write(1, True)` -> `ValueError`
- `plc.df.write(1, float("nan"))` -> `ValueError`
- `plc.df.write(1, float("inf"))` -> `ValueError`
- `plc.txt.write(1, "AB")` -> `ValueError`
- `plc.txt.write(1, "\\u00E9")` -> `ValueError`
- `plc.txt.write(1, "")` -> succeeds (writes NUL)

2. MemoryDataProvider rejections
- `set("DS1", 999999999999)` -> `ValueError`
- `set("DF1", "abc")` -> `ValueError`
- `set("TXT1", "AB")` -> `ValueError`
- `set("DH1", -1)` -> `ValueError`

3. Regression coverage
- Existing valid read/write tests remain green.
- Existing Modbus mapping/pack/unpack tests remain green.

## Spec/Doc Updates

- `spec/CLICKSERVER_SPEC.md`
  - Add strict runtime value validation semantics for `MemoryDataProvider`.
  - Clarify that DataProvider exceptions include validation errors and map to `SlaveDeviceFailure`.

- `spec/CLICKDEVICE_SPEC.md`
  - Add explicit runtime value-range rules for write APIs.
  - Document WORD range for `HEX` (`0..65535`).
  - Add strict invalid-value scenarios.

## Acceptance Criteria

- Invalid runtime write values fail consistently in both client API and `MemoryDataProvider`.
- Errors are `ValueError` with actionable messages.
- No permissive mode exists in core API.
- Spec docs clearly describe runtime validation behavior and limits.
