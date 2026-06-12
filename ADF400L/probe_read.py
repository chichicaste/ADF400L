#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 @chichicaste — MIT License
"""Read-only Modbus-TCP probe for the ADF400L test device. No writes."""

import sys
from pymodbus.client import ModbusTcpClient

HOST = "192.168.0.20"
PORT = 502

client = ModbusTcpClient(HOST, port=PORT, timeout=0.8, retries=0)
if not client.connect():
    print("TCP connect FAILED")
    sys.exit(1)
print("TCP connected to %s:%d" % (HOST, PORT))


def rd(addr, count, unit, fc="holding"):
    fn = (
        client.read_holding_registers
        if fc == "holding"
        else client.read_input_registers
    )
    for kw in ("device_id", "slave"):
        try:
            rr = fn(address=addr, count=count, **{kw: unit})
        except TypeError:
            continue
        except Exception as e:
            return "ERR:%s" % e
        if rr is None:
            return "NONE"
        if rr.isError():
            return "EXC:%s" % rr
        return rr.registers
    return "ERR:no-kwarg"


# Quick single-target sanity: a few unit-ids x a few addresses, holding + input.
print("\n== quick sanity ==")
for uid in (1, 0, 13, 25):
    print(
        "uid",
        uid,
        "| H0x033F:",
        rd(0x033F, 1, uid, "holding"),
        "| H0x0300:",
        rd(0x0300, 1, uid, "holding"),
        "| H0x0900:",
        rd(0x0900, 1, uid, "holding"),
        "| I0x033F:",
        rd(0x033F, 1, uid, "input"),
    )

client.close()
print("Done.")
