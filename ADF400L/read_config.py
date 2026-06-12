#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 @chichicaste — MIT License
"""Read & decode ADF400L system parameter area (config). Read-only."""

from pymodbus.client import ModbusTcpClient

HOST, PORT, UID = "192.168.0.20", 502, 1
c = ModbusTcpClient(HOST, port=PORT, timeout=1.5, retries=1)
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


g1 = rd(0x0900, 20)  # 0x0900..0x0913
g2 = rd(0x0950, 35)  # 0x0950..0x0972
c.close()


def reg(block, base, addr):
    return block[addr - base] if block else None


BAUD = {0: "9600", 1: "9600", 2: "4800", 3: "2400", 4: "1200"}
PAR = {0: "NONE", 1: "ODD", 2: "EVEN"}


def baud_word(v):
    if v is None:
        return "n/a"
    return "%s baud, %s parity" % (BAUD.get(v & 0xFF, "?"), PAR.get(v >> 8, "?"))


def bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


def ip_of(regs):
    if not regs or None in regs:
        return "n/a"
    bs = []
    for r in regs:
        bs += [r >> 8, r & 0xFF]
    return ".".join(str(x) for x in bs)


print("== ADF400L system configuration (uid %d) ==\n" % UID)
print(" Address 1 ............:", reg(g1, 0x900, 0x900))
print(
    " Baud rate 1 ..........:",
    baud_word(reg(g1, 0x900, 0x901)),
    "(raw 0x%04X)" % (reg(g1, 0x900, 0x901) or 0),
)
print(" Password .............:", reg(g1, 0x900, 0x902))
print(" 3-phase circuits .....:", reg(g1, 0x900, 0x903))
print(" 1-phase circuits .....:", reg(g1, 0x900, 0x904))
proto = reg(g1, 0x900, 0x908)
if proto is not None:
    print(
        " Protocol selection ...: type=%s, proto=%s (raw 0x%04X)"
        % (
            {0: "Prepaid", 1: "Metering"}.get(proto >> 8, "?"),
            {0: "modbus"}.get(proto & 0xFF, "?"),
            proto,
        )
    )
print(" Force control mark ...:", reg(g1, 0x900, 0x909))
print(" IC card enabled ......:", reg(g1, 0x900, 0x90A))
# RTC
sm = reg(g1, 0x900, 0x90B)
hw = reg(g1, 0x900, 0x90C)
dm = reg(g1, 0x900, 0x90D)
yr = reg(g1, 0x900, 0x90E)
if None not in (sm, hw, dm, yr):
    print(
        " RTC ..................: 20%02d-%02d-%02d  %02d:%02d:%02d  (weekday=%d)"
        % (
            bcd(yr >> 8),
            bcd(dm & 0xFF),
            bcd(dm >> 8),
            bcd(hw >> 8),
            bcd(sm >> 8),
            bcd(sm & 0xFF),
            bcd(hw & 0xFF),
        )
    )
    print("     raw s/m=0x%04X h/w=0x%04X d/m=0x%04X y=0x%04X" % (sm, hw, dm, yr))
print(" SP circuit type(090F).:", reg(g1, 0x900, 0x90F))
print(" Total SP circuits ....:", reg(g1, 0x900, 0x910))
print(" Address 2 ............:", reg(g1, 0x900, 0x911))
print(" Baud rate 2 ..........:", baud_word(reg(g1, 0x900, 0x912)))

print("\n -- measurement / IO --")
print(
    " Line selection .......:", {0: "3P4L", 1: "3P3L"}.get(reg(g2, 0x950, 0x950), "?")
)
print(" PT ratio .............:", reg(g2, 0x950, 0x951))
print(" CT1..CT12 ............:", [reg(g2, 0x950, a) for a in range(0x952, 0x95E)])
print(
    " Output method ........:", {0: "Level", 1: "Pulse"}.get(reg(g2, 0x950, 0x95E), "?")
)
print(" Pulse width ..........:", reg(g2, 0x950, 0x95F), "(x ms)")
print(" Pulse interval .......:", reg(g2, 0x950, 0x960), "(x s)")
print(" Wireless enabled .....:", reg(g2, 0x950, 0x961))
print(" Transformer circuits .:", reg(g2, 0x950, 0x962))
print(" Slave addr rearrange .:", reg(g2, 0x950, 0x963))
print(" CE Ethernet enabled ..:", reg(g2, 0x950, 0x964))
print(" Address 3 ............:", reg(g2, 0x950, 0x965))
print(" Baud rate 3 ..........:", baud_word(reg(g2, 0x950, 0x966)))
print(" Debug info switch ....:", reg(g2, 0x950, 0x967))

print("\n -- network --")
print(" Gateway IP ...........:", ip_of([reg(g2, 0x950, 0x968), reg(g2, 0x950, 0x969)]))
print(" Subnet mask ..........:", ip_of([reg(g2, 0x950, 0x96A), reg(g2, 0x950, 0x96B)]))
print(" Local IP .............:", ip_of([reg(g2, 0x950, 0x96C), reg(g2, 0x950, 0x96D)]))
mac = [reg(g2, 0x950, a) for a in (0x96E, 0x96F, 0x970)]
print(
    " MAC ..................:",
    ":".join("%02X%02X" % (r >> 8, r & 0xFF) for r in mac)
    if None not in mac
    else "n/a",
)
print(" TCP port .............:", reg(g2, 0x950, 0x971))
print(" DI debounce ..........:", reg(g2, 0x950, 0x972))
