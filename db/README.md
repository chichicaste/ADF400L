# ADF400L database (`adf400l.db`)

Codigo (c) 2026 @chichicaste — MIT License. Documentacion (c) Acrel Electric Co., Ltd.

SQLite database derived from `adf400l.md` (Acrel ADF400L manual V1.8). It is the
data backbone for a Modbus-TCP monitoring & control application.

Rebuild at any time with: `python build.py`

## Tables

| Table | Rows | Purpose |
|:------|-----:|:--------|
| `metadata` | 19 | Project facts, conventions and caveats (transport, addressing, word order…). |
| `device_model` | 1 | Model / family info. |
| `specification` | 21 | Technical specs (section 4). |
| `user_type` | 4 | `single_phase`, `three_phase`, `transformer`, `common`. |
| `register_area` | 12 | Modbus zones with start/end addresses. |
| `register` | 284 | **Full register map** (address, access, length, type, scale, unit, category, enum). |
| `enum_group` / `enum_value` | 15 / 34 | Lookups for coded registers (baud, parity, line mode, control words…). |
| `bitfield` | 9 | DI/DO bit maps (Tables 1 & 2) + status-word skeleton (`0x0311`/`0x0369`, **unverified**). |
| `card_error_code` | 10 | IC-card swipe errors (Err01…Err15). |
| `module_error_code` | 3 | Wiring inspection errors (Err1…Err3). |
| `programming_menu` | 36 | LCD button-programming menu (codes + ranges). |
| `display_screen` | 16 | Per-user key-display sequence. |
| `modbus_function` | 4 | Standard Modbus function codes (FC 0x03/0x04/0x06/0x10; convention, not from manual). |
| `modbus_exception` | 7 | Standard Modbus exception codes for app-layer error handling. |
| `reference` | 4 | External docs/repos for development (V1.8 manual, GitHub repos, HA integration). |

## Key conventions (also in `metadata`)

- **Length is in bytes**: `2` = one 16-bit register, `4` = two registers. `register.length_registers` is precomputed.
- **Scaling**: engineering value = `raw * register.scale` (e.g. voltage `scale=0.1` → V). `scale = NULL` means raw/coded/structured.
- **Data types**: `U` unsigned, `I` signed, `BITFIELD`, `ARRAY` (harmonics), `BLOCK` (multi-field structures: time tables, history, recharge). The RTC registers (`0x090B`–`0x090E`) are **binary byte-packed** (`U`), **not** BCD — confirmed on device.
- **Addressing**: each *user* answers at its own Modbus unit-id. Transformer/three-phase users are spaced by 3, single-phase by 1; meter numbers 1, 37, 73… Single-phase users use the *single-phase data area*; three-phase **and** transformer users use the *three-phase data area* (apply CT ratio for transformer).
- **32-bit word order** for 4-byte values is **BIG (high word first)** — `value = (regs[0]<<16)|regs[1]`. Confirmed on test device (`metadata.32bit_word_order = BIG`), though not stated in the manual.
- **Status words** (`0x0311`, `0x0369`): bit meanings are **not documented** by Acrel. A read-only probe of the test device (2026-06, metering mode) found `0x0369 = 0x0300` (bits 9 & 10 set) on energized transformer users and **disproved** the bit-1 relay hypothesis (bits 1/2 = 0 with relays closed). The relay/trip bit could not be located read-only (no tripped sample in metering mode). The `bitfield` rows record what was observed; see `metadata.status_word_bits` for how to finish the mapping on a prepaid/writable unit.

## Example queries

```sql
-- Live three-phase measurements to poll (FC 0x03)
SELECT address_hex, data_item, length_registers, scale, unit
FROM register WHERE user_type='three_phase' AND category='measurement';

-- All writable setpoints (prepaid, control, config)
SELECT address_hex, data_item, category, unit FROM register WHERE access='R/W';

-- Decode a coded register
SELECT e.raw_value, e.label
FROM register r JOIN enum_value e ON r.enum_group = e.group_code
WHERE r.address_hex = '0x0901';   -- baud rate / parity word

-- Programming-menu submenu
SELECT first_level, second_level, meaning, value_range
FROM programming_menu WHERE first_level='CESEt';
```
