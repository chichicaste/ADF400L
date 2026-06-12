#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 @chichicaste — MIT License
"""
Program El Salvador electricity tariff prices into an ADF400L meter (Modbus-TCP).

SAFETY:
  * DRY-RUN by default: nothing is written unless you pass --commit.
  * Only the 4 multi-rate PRICE registers are written (tip/peak/flat/valley).
  * It NEVER touches meter mode (0x0908), address, baud rate or network config.
  * Every write is read back and verified.
  * The daily time-of-use SCHEDULE (period table) is OPTIONAL (--with-schedule)
    and EXPERIMENTAL: the packed field encoding is not documented by Acrel and
    must be validated on the device first.

Tariff source: national energy charge (DGEHM/CNE), CAESS pliego 15-Jan-2025, USD/kWh.
See docs/tarifa_electrica_el_salvador.md for equations and details.

Encoding notes (from db/adf400l.db / manual V1.8):
  * Price registers are U32 (length 4 = 2 registers), scale 0.01 [currency]/kWh.
  * 32-bit word order is BIG (high word first): value = (reg0<<16)|reg1.
  * Resolution is 0.01 USD/kWh -> prices are rounded to cents (see doc Option B).
"""
import argparse
import sys

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    sys.exit("pymodbus is required:  pip install pymodbus")

# --------------------------------------------------------------------------- #
# Tariff catalogue (USD/kWh) — CAESS, effective 15-Jan-2025, VAT excluded.
# type 'tou'  -> {punta, resto, valle};  type 'flat' -> {energy}
# --------------------------------------------------------------------------- #
TARIFFS = {
    "residential": {"type": "flat", "energy": 0.192553,   # block 1 (representative)
                    "note": "Residential is BLOCK-based (0.192553/0.192662/0.190757); "
                            "the meter cannot model consumption blocks - block 1 used."},
    "general":     {"type": "flat", "energy": 0.188268},
    "ap":          {"type": "flat", "energy": 0.169213},   # alumbrado publico
    "md_bt_pot":   {"type": "flat", "energy": 0.186032},
    "md_mt_pot":   {"type": "flat", "energy": 0.173346},
    "md_bt_hor":   {"type": "tou", "punta": 0.210306, "resto": 0.177030, "valle": 0.208128},
    "md_mt_hor":   {"type": "tou", "punta": 0.194827, "resto": 0.164001, "valle": 0.192810},
    "gd_bt":       {"type": "tou", "punta": 0.210306, "resto": 0.177030, "valle": 0.208128},
    "gd_mt":       {"type": "tou", "punta": 0.194827, "resto": 0.164001, "valle": 0.192810},
}

# Multi-rate PRICE registers (U32). Order: tip(F1) / peak(F2) / flat(F3) / valley(F4).
PRICE_REGS = {
    "single": {"tip": 0x0501, "peak": 0x0503, "flat": 0x0505, "valley": 0x0507},
    "three":  {"tip": 0x0537, "peak": 0x0539, "flat": 0x053B, "valley": 0x053D},
}

# Time-of-use -> Acrel 4-rate mapping (El Salvador has 3 periods; tip duplicates punta).
#   peak  <- Punta (18:00-22:59)
#   flat  <- Resto (05:00-17:59)
#   valley<- Valle (23:00-04:59)
#   tip   <- Punta (duplicate)

# Daily ToU schedule. Period table is byte-packed, 2 fields/register, stream
# order Period,Hour,Minute (VALIDATED on device 2026-06 against the factory table).
# Rate index 1..4 = tip/peak/flat/valley (F1..F4), same order as the price regs.
# Two seasonal tables exist (0x0914 table1, 0x0929 table2); the seasonal selector
# (0x093E) alternates between them, so we write the SAME schedule to BOTH.
PERIOD_TABLES = [0x0914, 0x0929]
RATE_IDX = {"tip": 1, "peak": 2, "flat": 3, "valley": 4}  # VALIDATED (factory pattern cycles 1-4)
# El Salvador transitions (rate begins at): 00:00 valle, 05:00 resto, 18:00 punta, 23:00 valle
SCHEDULE = [("valley", 0, 0), ("flat", 5, 0), ("peak", 18, 0), ("valley", 23, 0)]


def build_period_regs():
    """14 monotonic slots; pad after the last transition with valley at +5min steps."""
    slots = list(SCHEDULE)
    pad_m = 5
    while len(slots) < 14:
        slots.append(("valley", 23, pad_m)); pad_m += 5
    fields = []
    for rate, h, mi in slots:
        fields += [RATE_IDX[rate], h, mi]
    regs = [(fields[i] << 8) | fields[i + 1] for i in range(0, len(fields), 2)]
    return regs, slots


def cents(usd):
    """USD/kWh -> integer in 0.01-USD/kWh units (meter resolution)."""
    return int(round(usd * 100))


def split_u32(value):
    """BIG word order: high word first."""
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def join_u32(regs):
    return (regs[0] << 16) | regs[1]


class Meter:
    def __init__(self, host, port, unit):
        self.unit = unit
        self.c = ModbusTcpClient(host, port=port, timeout=2.0, retries=0)
        if not self.c.connect():
            sys.exit("TCP connect FAILED to %s:%d" % (host, port))

    def _call(self, fn, **kw):
        for key in ("device_id", "slave"):
            try:
                return fn(**kw, **{key: self.unit})
            except TypeError:
                continue
        raise RuntimeError("pymodbus kwarg (device_id/slave) not accepted")

    def read(self, addr, count):
        rr = self._call(self.c.read_holding_registers, address=addr, count=count)
        if rr is None or rr.isError():
            return None
        return rr.registers

    def write_u32(self, addr, value):
        regs = split_u32(value)
        rr = self._call(self.c.write_registers, address=addr, values=regs)
        return rr is not None and not rr.isError()

    def close(self):
        self.c.close()


def build_plan(phase, tariff_key):
    """Return list of (label, addr, value_units, usd) for the 4 price registers."""
    t = TARIFFS[tariff_key]
    regs = PRICE_REGS[phase]
    if t["type"] == "tou":
        usd = {"tip": t["punta"], "peak": t["punta"], "flat": t["resto"], "valley": t["valle"]}
    else:
        e = t["energy"]
        usd = {"tip": e, "peak": e, "flat": e, "valley": e}
    plan = []
    for rate in ("tip", "peak", "flat", "valley"):
        plan.append((rate, regs[rate], cents(usd[rate]), usd[rate]))
    return plan, t


def main():
    ap = argparse.ArgumentParser(description="Program El Salvador tariff into ADF400L (read-only unless --commit).")
    ap.add_argument("--host", default="192.168.0.20")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1, help="Modbus unit-id (per user)")
    ap.add_argument("--phase", choices=["single", "three"], default="three",
                    help="three = three-phase/transformer users (0x0537..); single = 0x0501..")
    ap.add_argument("--tariff", choices=sorted(TARIFFS), default="md_mt_hor")
    ap.add_argument("--commit", action="store_true", help="ACTUALLY write (default: dry-run)")
    ap.add_argument("--with-schedule", action="store_true",
                    help="ALSO write the daily ToU period table (EXPERIMENTAL, unvalidated encoding)")
    args = ap.parse_args()

    plan, t = build_plan(args.phase, args.tariff)

    print("=" * 70)
    print("ADF400L tariff programmer  |  %s:%d  unit=%d  phase=%s" % (args.host, args.port, args.unit, args.phase))
    print("Tariff: %s (%s)" % (args.tariff, t["type"]))
    if "note" in t:
        print("  NOTE:", t["note"])
    print("Mode  : %s" % ("COMMIT (will write)" if args.commit else "DRY-RUN (no writes)"))
    print("=" * 70)

    m = Meter(args.host, args.port, args.unit)

    # show current mode (informational; we never change it)
    proto = m.read(0x0908, 1)
    if proto:
        mode = {0: "Prepaid", 1: "Metering"}.get((proto[0] >> 8) & 0xFF, "?")
        print("Device mode (0x0908 hi byte): %s  (price regs are display-only in Metering)\n" % mode)

    print("Planned PRICE writes (U32, scale 0.01 USD/kWh):")
    print("  rate   addr     USD/kWh   -> units  (rounding err)")
    for rate, addr, units, usd in plan:
        err = units / 100.0 - usd
        print("  %-6s 0x%04X   %8.6f -> %4d    (%+.4f)" % (rate, addr, usd, units, err))

    # apply / verify
    print()
    ok = True
    for rate, addr, units, usd in plan:
        before = m.read(addr, 2)
        before_v = join_u32(before) if before else None
        if not args.commit:
            print("  [dry-run] 0x%04X %-6s would set %d (now=%s)" % (addr, rate, units, before_v))
            continue
        wok = m.write_u32(addr, units)
        after = m.read(addr, 2)
        after_v = join_u32(after) if after else None
        good = wok and after_v == units
        ok = ok and good
        print("  [write ] 0x%04X %-6s set %d -> readback %s  %s"
              % (addr, rate, units, after_v, "OK" if good else "FAIL"))

    # optional ToU schedule (validated encoding; written to both seasonal tables)
    if args.with_schedule:
        regs, slots = build_period_regs()
        print("\n--- ToU daily schedule (rate idx 1=tip 2=peak 3=flat 4=valley) ---")
        for rate, h, mi in slots[:len(SCHEDULE)]:
            print("    %02d:%02d -> %-6s (idx %d)" % (h, mi, rate, RATE_IDX[rate]))
        print("    slots %d-14 padded as valley (keeps table monotonic)" % (len(SCHEDULE) + 1))
        for base in PERIOD_TABLES:
            if not args.commit:
                print("    [dry-run] 0x%04X <- %d regs: %s ..."
                      % (base, len(regs), ["0x%04X" % r for r in regs[:6]]))
            else:
                wr = m._call(m.c.write_registers, address=base, values=regs)
                back = m.read(base, len(regs))
                good = wr is not None and not wr.isError() and back == regs
                ok = ok and good
                print("    [write ] 0x%04X period table -> %s" % (base, "OK (verified)" if good else "FAIL"))

    m.close()
    print("\n%s" % ("Done (no changes - dry-run)." if not args.commit else
                    ("Done. All writes verified." if ok else "Done WITH FAILURES - review above.")))
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
