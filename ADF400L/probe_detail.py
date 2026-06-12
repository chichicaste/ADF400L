#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 @chichicaste — MIT License
"""Read-only detailed read of ADF400L at unit-id 1. No writes."""

import struct
from pymodbus.client import ModbusTcpClient

HOST, PORT, UID = "192.168.0.20", 502, 1
c = ModbusTcpClient(HOST, port=PORT, timeout=1.0, retries=1)
c.connect()


def rd(addr, count):
    for kw in ("device_id", "slave"):
        try:
            rr = c.read_holding_registers(address=addr, count=count, **{kw: UID})
        except TypeError:
            continue
        if rr is None or rr.isError():
            return None
        return rr.registers
    return None


def u32(regs, hi_first=True):
    if regs is None or len(regs) < 2:
        return None
    hi, lo = (regs[0], regs[1]) if hi_first else (regs[1], regs[0])
    return (hi << 16) | lo


print("== System parameter area (uid 1) ==")
sysblk = rd(0x0900, 5)
print(" 0x0900..0904:", sysblk)
if sysblk:
    print(
        "   Address1 =",
        sysblk[0],
        "| Baud/parity word =",
        hex(sysblk[1]),
        "| 3ph_count =",
        sysblk[3],
        "| 1ph_count =",
        sysblk[4],
    )
print(" 0x0962 transformer_count:", rd(0x0962, 1))
print(
    " 0x0950 line_selection:",
    rd(0x0950, 1),
    "| 0x0951 PT:",
    rd(0x0951, 1),
    "| 0x0952 CT1:",
    rd(0x0952, 1),
)
print(" 0x0971 tcp_port:", rd(0x0971, 1))

print("\n== Three-phase area 0x033F.. (uid 1) ==")
b = rd(0x033F, 0x13)  # 0x033F..0x0351
labels = [
    "Ua",
    "Ub",
    "Uc",
    "Ia",
    "Ib",
    "Ic",
    "Ptot",
    "Pa",
    "Pb",
    "Pc",
    "Qtot",
    "Qa",
    "Qb",
    "Qc",
    "PFtot",
    "PFa",
    "PFb",
    "PFc",
    "Freq",
]
if b:
    for lab, addr, raw in zip(labels, range(0x033F, 0x0352), b):
        print("  0x%04X %-5s raw=%-7d" % (addr, lab, raw))

print("\n== 32-bit word-order test on A-phase active energy 0x0352 ==")
e = rd(0x0352, 2)
print(
    "  regs:",
    e,
    "| BIG(hi,lo)=",
    u32(e, True),
    "x0.01 ->",
    (u32(e, True) or 0) * 0.01,
    "| LITTLE(lo,hi)=",
    u32(e, False),
    "x0.01 ->",
    (u32(e, False) or 0) * 0.01,
)
tot = rd(0x035E, 2)
print(
    "  Total active energy 0x035E regs:",
    tot,
    "| BIG x0.01 ->",
    (u32(tot, True) or 0) * 0.01,
    "| LITTLE x0.01 ->",
    (u32(tot, False) or 0) * 0.01,
)

print("\n== Compare single-phase area 0x0300 vs three-phase 0x033F ==")
print("  0x0300..0x0305:", rd(0x0300, 6))
print("  0x033F..0x0344:", rd(0x033F, 6))

c.close()
print("\nDone.")
