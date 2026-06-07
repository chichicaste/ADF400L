#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 @chichicaste — MIT License
"""
Builds adf400l.db (SQLite) from the ADF400L manual (adf400l.md).

The database is intended as the data backbone for a monitoring & control
application that talks to ADF400L multi-user energy meters over Modbus TCP/IP.

It captures: device/model info, technical specs, the full Modbus register map
(with scaling/units/access), enumerations, bit-field maps, fault/error codes,
the LCD programming menu, the key-display sequence and Modbus/addressing notes.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adf400l.db")

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
SCHEMA = """
PRAGMA foreign_keys = ON;

-- General key/value metadata (project-level facts, conventions, caveats).
CREATE TABLE metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    note        TEXT
);

-- The meter model / product family.
CREATE TABLE device_model (
    id              INTEGER PRIMARY KEY,
    model_code      TEXT NOT NULL,
    name            TEXT NOT NULL,
    manual_version  TEXT,
    manufacturer    TEXT,
    description     TEXT
);

-- Technical specifications (section 4 of the manual).
CREATE TABLE specification (
    id          INTEGER PRIMARY KEY,
    category    TEXT NOT NULL,
    parameter   TEXT NOT NULL,
    value       TEXT NOT NULL,
    unit        TEXT
);

-- Logical user kinds served by a single physical meter.
CREATE TABLE user_type (
    code        TEXT PRIMARY KEY,          -- single_phase | three_phase | transformer | common
    name        TEXT NOT NULL,
    description TEXT
);

-- Modbus register areas (zones).
CREATE TABLE register_area (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    start_addr_hex  TEXT NOT NULL,
    start_addr_dec  INTEGER NOT NULL,
    end_addr_hex    TEXT,
    end_addr_dec    INTEGER,
    applies_to      TEXT,                  -- user_type.code or 'common'
    description     TEXT
);

-- The Modbus register map (holding registers).
CREATE TABLE register (
    id                  INTEGER PRIMARY KEY,
    area_id             INTEGER NOT NULL REFERENCES register_area(id),
    address_hex         TEXT NOT NULL,
    address_dec         INTEGER NOT NULL,
    data_item           TEXT NOT NULL,
    access              TEXT NOT NULL,     -- R | R/W
    length_registers    INTEGER NOT NULL,  -- number of 16-bit registers
    length_bytes        INTEGER NOT NULL,
    data_type           TEXT NOT NULL,     -- U | I | BITFIELD | BCD | ARRAY | BLOCK
    scale               REAL,              -- engineering = raw * scale (NULL = none/special)
    unit                TEXT,              -- V, A, kW, kvar, kWh, kvarh, Hz, yuan, ...
    user_type           TEXT REFERENCES user_type(code),
    category            TEXT,              -- measurement|energy|prepaid|config|status|control|time|network|harmonic|history|record
    enum_group          TEXT,              -- -> enum_group.code when the value is coded
    remarks             TEXT
);
CREATE INDEX idx_register_addr ON register(address_dec);
CREATE INDEX idx_register_area ON register(area_id);
CREATE INDEX idx_register_user ON register(user_type);

-- Enumerations referenced by coded registers / menu items.
CREATE TABLE enum_group (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);
CREATE TABLE enum_value (
    id          INTEGER PRIMARY KEY,
    group_code  TEXT NOT NULL REFERENCES enum_group(code),
    raw_value   TEXT NOT NULL,
    label       TEXT NOT NULL,
    note        TEXT
);
CREATE INDEX idx_enum_value_group ON enum_value(group_code);

-- Bit-field maps for status / DI-DO control words (Tables 1 & 2, status words).
CREATE TABLE bitfield (
    id              INTEGER PRIMARY KEY,
    register_hex    TEXT NOT NULL,
    bit_position    INTEGER NOT NULL,      -- 1-based as printed in the manual
    signal          TEXT NOT NULL,
    description     TEXT
);

-- IC-card swipe error codes (section 8.1).
CREATE TABLE card_error_code (
    code        TEXT PRIMARY KEY,
    meaning     TEXT NOT NULL
);

-- Module wiring / power-on inspection error codes (section 6.5).
CREATE TABLE module_error_code (
    code        TEXT PRIMARY KEY,
    meaning     TEXT NOT NULL
);

-- The LCD button-programming menu (section 8.4).
CREATE TABLE programming_menu (
    id              INTEGER PRIMARY KEY,
    seq             INTEGER NOT NULL,
    first_level     TEXT NOT NULL,         -- LCD code shown (7-segment)
    second_level    TEXT,                  -- '/' = none
    meaning         TEXT NOT NULL,
    value_range     TEXT
);

-- The per-user key-display sequence (section 8.2 / 8.3).
CREATE TABLE display_screen (
    id          INTEGER PRIMARY KEY,
    seq         INTEGER NOT NULL,
    content     TEXT NOT NULL,
    values_shown TEXT,
    unit        TEXT
);

-- Standard Modbus function codes useful to the application layer.
CREATE TABLE modbus_function (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    usage       TEXT,
    source      TEXT
);
"""


def h2d(hex_str):
    """'0x0300' -> 768"""
    return int(hex_str, 16)


# --------------------------------------------------------------------------- #
# Register data  (addr, name, access, length_bytes, data_type, scale, unit, category)
# user_type / area assigned per-block below.
# --------------------------------------------------------------------------- #

SINGLE_PHASE = [
    ("0x0300", "Single phase voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0301", "Single phase current", "R", 2, "U", 0.01, "A", "measurement"),
    ("0x0302", "Single-phase active power", "R", 2, "I", 0.001, "kW", "measurement"),
    (
        "0x0303",
        "Single phase reactive power",
        "R",
        2,
        "I",
        0.001,
        "kvar",
        "measurement",
    ),
    ("0x0304", "Single phase power factor", "R", 2, "I", 0.001, None, "measurement"),
    ("0x0305", "Single phase frequency", "R", 2, "U", 0.01, "Hz", "measurement"),
    ("0x0306", "Single-phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0308", "Single-phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x030A", "Single-phase residual energy", "R", 4, "I", 0.01, "kWh", "energy"),
    (
        "0x030C",
        "Single-phase total power purchase",
        "R",
        4,
        "U",
        0.01,
        "kWh",
        "prepaid",
    ),
    ("0x030E", "Single-phase power purchases", "R", 2, "U", None, None, "prepaid"),
    ("0x030F", "Single-phase basic electricity", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0311", "Single-phase status word", "R", 2, "BITFIELD", None, None, "status"),
    (
        "0x0312",
        "Single-phase basic power remaining",
        "R",
        4,
        "I",
        0.01,
        "kWh",
        "energy",
    ),
    ("0x0314", "Reserved", "R", 2, "U", None, None, "status"),
    ("0x0315", "Single-phase over-limit amount", "R", 4, "U", None, None, "prepaid"),
    ("0x0317", "Recovery Time", "R", 2, "U", None, None, "control"),
    ("0x0318", "Recovery time overload value", "R", 2, "U", 1.0, "s", "control"),
    (
        "0x0319",
        "Single-phase positive active energy",
        "R",
        4,
        "U",
        0.01,
        "kWh",
        "energy",
    ),
    ("0x031B", "Unidirectional active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    (
        "0x031D",
        "Single-phase forward reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
    (
        "0x031F",
        "Single-phase reverse reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
]

THREE_PHASE = [
    ("0x033F", "A Phase voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0340", "B Phase voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0341", "C Phase voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0342", "A Phase current", "R", 2, "U", 0.01, "A", "measurement"),
    ("0x0343", "B Phase current", "R", 2, "U", 0.01, "A", "measurement"),
    ("0x0344", "C Phase current", "R", 2, "U", 0.01, "A", "measurement"),
    ("0x0345", "Total active power", "R", 2, "I", 1.0, "W", "measurement"),
    ("0x0346", "A Phase active power", "R", 2, "I", 0.001, "kW", "measurement"),
    ("0x0347", "B Phase active power", "R", 2, "I", 0.001, "kW", "measurement"),
    ("0x0348", "C Phase active power", "R", 2, "I", 0.001, "kW", "measurement"),
    ("0x0349", "Total reactive power", "R", 2, "I", 0.001, "kvar", "measurement"),
    ("0x034A", "A Phase reactive power", "R", 2, "I", 0.001, "kvar", "measurement"),
    ("0x034B", "B Phase reactive power", "R", 2, "I", 0.001, "kvar", "measurement"),
    ("0x034C", "C Phase reactive power", "R", 2, "I", 0.001, "kvar", "measurement"),
    ("0x034D", "Total power factor", "R", 2, "I", 0.001, None, "measurement"),
    ("0x034E", "A Phase power factor", "R", 2, "I", 0.001, None, "measurement"),
    ("0x034F", "B Phase power factor", "R", 2, "I", 0.001, None, "measurement"),
    ("0x0350", "C Phase power factor", "R", 2, "I", 0.001, None, "measurement"),
    ("0x0351", "Frequency", "R", 2, "U", 0.01, "Hz", "measurement"),
    ("0x0352", "A Phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0354", "B Phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0356", "C Phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0358", "A Phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x035A", "B Phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x035C", "C Phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x035E", "Total active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0360", "Total reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x0362", "Remaining amount", "R", 4, "I", 0.01, "yuan", "prepaid"),
    ("0x0364", "Total purchase amount", "R", 4, "U", 0.01, "yuan", "prepaid"),
    ("0x0366", "Number of power purchases", "R", 2, "U", None, None, "prepaid"),
    ("0x0367", "Base amount", "R", 4, "U", 0.01, "yuan", "prepaid"),
    ("0x0369", "Running status word", "R", 2, "BITFIELD", None, None, "status"),
    ("0x036A", "Basic battery remaining", "R", 4, "U", 0.01, "yuan", "prepaid"),
    ("0x036C", "Reserved", "R", 2, "U", None, None, "status"),
    ("0x036D", "Overdraft amount", "R", 2, "U", None, None, "prepaid"),
    ("0x036F", "Recovery Time", "R", 2, "U", 1.0, "s", "control"),
    ("0x0370", "Recovery time overload value", "R", 2, "U", 1.0, "s", "control"),
    ("0x0371", "AB Line voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0372", "BC Line voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0373", "CA Line voltage", "R", 2, "U", 0.1, "V", "measurement"),
    ("0x0374", "Zero sequence current", "R", 2, "U", 0.1, "A", "measurement"),
    ("0x0375", "Voltage unbalance", "R", 2, "U", 0.01, None, "measurement"),
    ("0x0376", "Current unbalance", "R", 2, "U", 0.01, None, "measurement"),
    ("0x0377", "A Phase positive active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0379", "A Reverse phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x037B", "B Phase positive active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x037D", "B Reverse phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x037F", "C Phase positive active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0381", "C Reverse phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    (
        "0x0383",
        "A Phase positive reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
    ("0x0385", "A Reverse phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    (
        "0x0387",
        "B Phase positive reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
    ("0x0389", "B reverse phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    (
        "0x038B",
        "C Phase positive reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
    ("0x038D", "C reverse phase reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    ("0x038F", "Total positive active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0391", "Total reverse phase active energy", "R", 4, "U", 0.01, "kWh", "energy"),
    ("0x0393", "Total positive reactive energy", "R", 4, "U", 0.01, "kvarh", "energy"),
    (
        "0x0395",
        "Total reverse phase reactive energy",
        "R",
        4,
        "U",
        0.01,
        "kvarh",
        "energy",
    ),
]

# Multiple rate area: single-phase 0x0400-0x042F, three-phase 0x0430-0x045F.
MULTI_RATE = [
    # (addr, name, access, user_type)
    ("0x0400", "Single-phase active tip electric energy", "R", "single_phase", "kWh"),
    ("0x0402", "Single-phase active peak energy", "R", "single_phase", "kWh"),
    ("0x0404", "Single-phase active flat energy", "R", "single_phase", "kWh"),
    (
        "0x0406",
        "Single-phase active valley electric energy",
        "R",
        "single_phase",
        "kWh",
    ),
    (
        "0x0408",
        "Single-phase reactive tip electric energy",
        "R",
        "single_phase",
        "kvarh",
    ),
    ("0x040A", "Single-phase reactive peak energy", "R", "single_phase", "kvarh"),
    ("0x040C", "Single-phase reactive flat energy", "R", "single_phase", "kvarh"),
    (
        "0x040E",
        "Single-phase reactive valley electric energy",
        "R",
        "single_phase",
        "kvarh",
    ),
    ("0x0410", "Single-phase forward active tip energy", "R/W", "single_phase", "kWh"),
    ("0x0412", "Single-phase forward active peak energy", "R/W", "single_phase", "kWh"),
    ("0x0414", "Single-phase forward active flat energy", "R/W", "single_phase", "kWh"),
    (
        "0x0416",
        "Single-phase forward active valley energy",
        "R/W",
        "single_phase",
        "kWh",
    ),
    (
        "0x0418",
        "Single-phase reverse active tip electric energy",
        "R/W",
        "single_phase",
        "kWh",
    ),
    ("0x041A", "Single-phase reverse active peak energy", "R/W", "single_phase", "kWh"),
    ("0x041C", "Single-phase reverse active flat energy", "R/W", "single_phase", "kWh"),
    (
        "0x041E",
        "Single phase reverse active valley energy",
        "R/W",
        "single_phase",
        "kWh",
    ),
    (
        "0x0420",
        "Single-phase forward reactive tip energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x0422",
        "Single-phase forward reactive peak energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x0424",
        "Single-phase forward reactive flat energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x0426",
        "Single-phase positive reactive valley energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x0428",
        "Single-phase reverse reactive tip electric energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x042A",
        "Single-phase reverse reactive peak energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x042C",
        "Single-phase reverse reactive flat energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    (
        "0x042E",
        "Single phase reverse reactive valley energy",
        "R/W",
        "single_phase",
        "kvarh",
    ),
    ("0x0430", "Three-phase active tip electric energy", "R", "three_phase", "kWh"),
    ("0x0432", "Three-phase active peak energy", "R", "three_phase", "kWh"),
    ("0x0434", "Three-phase active flat energy", "R", "three_phase", "kWh"),
    ("0x0436", "Three-phase active valley electric energy", "R", "three_phase", "kWh"),
    ("0x0438", "Three-phase reactive tip electric energy", "R", "three_phase", "kvarh"),
    ("0x043A", "Three-phase reactive peak energy", "R", "three_phase", "kvarh"),
    ("0x043C", "Three-phase reactive flat energy", "R", "three_phase", "kvarh"),
    (
        "0x043E",
        "Three-phase reactive valley electric energy",
        "R",
        "three_phase",
        "kvarh",
    ),
    ("0x0440", "Three-phase forward active tip energy", "R/W", "three_phase", "kWh"),
    ("0x0442", "Three-phase forward active peak energy", "R/W", "three_phase", "kWh"),
    ("0x0444", "Three-phase forward active flat energy", "R/W", "three_phase", "kWh"),
    (
        "0x0446",
        "Three-phase positive active valley electric energy",
        "R/W",
        "three_phase",
        "kWh",
    ),
    (
        "0x0448",
        "Three-phase reverse active tip electric energy",
        "R/W",
        "three_phase",
        "kWh",
    ),
    ("0x044A", "Three-phase reverse active peak energy", "R/W", "three_phase", "kWh"),
    ("0x044C", "Three-phase reverse active flat energy", "R/W", "three_phase", "kWh"),
    ("0x044E", "Three-phase reverse active valley energy", "R/W", "three_phase", "kWh"),
    (
        "0x0450",
        "Three-phase forward reactive tip electric energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x0452",
        "Three-phase forward reactive peak energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x0454",
        "Three-phase forward reactive flat energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x0456",
        "Three-phase forward reactive valley electric energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x0458",
        "Three-phase reverse reactive tip electric energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x045A",
        "Three-phase reverse reactive peak energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x045C",
        "Three-phase reverse reactive flat energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
    (
        "0x045E",
        "Three-phase reverse reactive valley energy",
        "R/W",
        "three_phase",
        "kvarh",
    ),
]

# Prepaid area 0x0500-0x0547 (price/alarm/purchase). access R/W.
PREPAID = [
    ("0x0500", "Single phase prepaid switch", 2, "U", None, None, "single_phase"),
    ("0x0501", "Single-phase peak price", 4, "U", 0.01, "yuan/kWh", "single_phase"),
    (
        "0x0503",
        "Single-phase peak electricity price",
        4,
        "U",
        0.01,
        "yuan/kWh",
        "single_phase",
    ),
    (
        "0x0505",
        "Single-phase electricity price",
        4,
        "U",
        0.01,
        "yuan/kWh",
        "single_phase",
    ),
    ("0x0507", "Single-phase valley price", 4, "U", 0.01, "yuan/kWh", "single_phase"),
    ("0x0509", "Single-phase alarm amount 1", 4, "U", 0.01, "yuan", "single_phase"),
    ("0x050B", "Single-phase alarm amount 2", 4, "U", 0.01, "yuan", "single_phase"),
    (
        "0x050D",
        "Single-phase new power purchase amount",
        4,
        "U",
        0.01,
        "yuan",
        "single_phase",
    ),
    ("0x050F", "Single-phase power purchases", 2, "U", None, None, "single_phase"),
    ("0x0510", "Single-phase basic amount", 4, "U", 0.01, "yuan", "single_phase"),
    ("0x0512", "Single phase prepaid switch", 2, "U", None, None, "single_phase"),
    ("0x0536", "Three-phase prepaid switch", 2, "U", None, None, "three_phase"),
    ("0x0537", "Three-phase peak price", 4, "U", 0.01, "yuan/kWh", "three_phase"),
    (
        "0x0539",
        "Three-phase peak electricity price",
        4,
        "U",
        0.01,
        "yuan/kWh",
        "three_phase",
    ),
    (
        "0x053B",
        "Three-phase electricity price",
        4,
        "U",
        0.01,
        "yuan/kWh",
        "three_phase",
    ),
    (
        "0x053D",
        "Three-phase valley electricity price",
        4,
        "U",
        0.01,
        "yuan/kWh",
        "three_phase",
    ),
    ("0x053F", "Three-phase alarm amount 1", 4, "U", 0.01, "yuan", "three_phase"),
    ("0x0541", "Three-phase alarm amount 2", 4, "U", 0.01, "yuan", "three_phase"),
    (
        "0x0543",
        "Three-phase new power purchase amount",
        4,
        "U",
        0.01,
        "yuan",
        "three_phase",
    ),
    ("0x0545", "Three-phase power purchase", 2, "U", None, None, "three_phase"),
    ("0x0546", "Three-phase basic amount", 4, "U", 0.01, "yuan", "three_phase"),
]

# Time zone area 0x0600-0x0667.
TIME_ZONE = [
    (
        "0x0600",
        "Single-phase time control switch",
        "R/W",
        2,
        "U",
        None,
        "single_phase",
        None,
    ),
    (
        "0x0601",
        "Single-phase working day time control table",
        "R/W",
        24,
        "BLOCK",
        None,
        "single_phase",
        "8 events x (Switch, Hour, Minute), 2 fields/register, spans 0x0601-0x060C",
    ),
    (
        "0x060D",
        "Single-phase rest day time control table",
        "R/W",
        24,
        "BLOCK",
        None,
        "single_phase",
        "Same layout, spans 0x060D-0x0618",
    ),
    (
        "0x0619",
        "Single phase rest day setting word",
        "R/W",
        2,
        "U",
        None,
        "single_phase",
        None,
    ),
    (
        "0x064E",
        "Three phase time control switch",
        "R/W",
        2,
        "U",
        None,
        "three_phase",
        None,
    ),
    (
        "0x064F",
        "Three-phase working day time control table",
        "R/W",
        24,
        "BLOCK",
        None,
        "three_phase",
        "Same layout, spans 0x064F-0x065A",
    ),
    (
        "0x065B",
        "Three-phase rest day time control table",
        "R/W",
        24,
        "BLOCK",
        None,
        "three_phase",
        "Same layout, spans 0x065B-0x0666",
    ),
    (
        "0x0667",
        "Three phase rest day setting word",
        "R/W",
        2,
        "U",
        None,
        "three_phase",
        None,
    ),
]

# Load control area 0x0700-0x071F.
LOAD_CONTROL = [
    ("0x0700", "Single phase load control switch", None, "single_phase", None),
    ("0x0701", "Single phase maximum power threshold", 0.001, "single_phase", "kW"),
    (
        "0x0702",
        "Single phase active power increment threshold",
        0.001,
        "single_phase",
        "kW",
    ),
    ("0x0703", "Single phase power factor threshold", None, "single_phase", None),
    ("0x0704", "Single phase load control times", None, "single_phase", None),
    ("0x0705", "Single phase load control allow times", None, "single_phase", None),
    ("0x0706", "Single phase load control recovery time", 10.0, "single_phase", "s"),
    ("0x0707", "Single phase voltage loss threshold", 0.1, "single_phase", "V"),
    ("0x0718", "Three phase load control switch", None, "three_phase", None),
    ("0x0719", "Three phase maximum power threshold", 0.001, "three_phase", "kW"),
    (
        "0x071A",
        "Three phase active power increment threshold",
        0.001,
        "three_phase",
        "kW",
    ),
    ("0x071B", "Three phase power factor threshold", None, "three_phase", None),
    ("0x071C", "Three phase load control times", None, "three_phase", None),
    ("0x071D", "Three phase load control allow times", None, "three_phase", None),
    ("0x071E", "Three phase load control recovery time", 10.0, "three_phase", "s"),
    ("0x071F", "Three phase voltage loss threshold", 0.1, "three_phase", "V"),
]

# Strong control zone 0x0800-0x0804.
STRONG_CONTROL = [
    (
        "0x0800",
        "Single three-phase category",
        "common",
        "enum_single_three_category",
        None,
    ),
    (
        "0x0801",
        "Single-phase strong control's control word",
        "single_phase",
        "enum_strong_control_word",
        "High bit 1: open, low bit 1: closed",
    ),
    (
        "0x0804",
        "Three-phase strong control's control word",
        "three_phase",
        "enum_strong_control_word",
        "High bit 1: open, low bit 1: closed",
    ),
]

# System parameter area 0x0900-0x0972 (common device config).
# (addr, name, access, length_bytes, data_type, enum_group, remarks)
SYSTEM = [
    ("0x0900", "Address 1", "R/W", 2, "U", None, "0~247"),
    (
        "0x0901",
        "Baud rate 1",
        "R/W",
        2,
        "U",
        "enum_baud_parity",
        "High byte parity / low byte baud",
    ),
    ("0x0902", "Password", "R/W", 2, "U", None, None),
    (
        "0x0903",
        "Number of three-phase circuits directly connected",
        "R/W",
        2,
        "U",
        None,
        "0~12",
    ),
    (
        "0x0904",
        "Number of single-phase circuits directly connected",
        "R/W",
        2,
        "U",
        None,
        "0~36",
    ),
    (
        "0x0908",
        "Protocol selection",
        "R/W",
        2,
        "U",
        "enum_protocol",
        "High byte type / low byte protocol",
    ),
    ("0x0909", "Force control mark", "R/W", 2, "U", None, "Not enabled"),
    (
        "0x090A",
        "Whether the IC card is enabled",
        "R/W",
        2,
        "U",
        "enum_enable_disable",
        None,
    ),
    (
        "0x090B",
        "Second/minute",
        "R/W",
        2,
        "U",
        None,
        "RTC: hi byte=second, lo byte=minute. Binary byte-packed (NOT BCD) - confirmed on device",
    ),
    (
        "0x090C",
        "Hour/week",
        "R/W",
        2,
        "U",
        None,
        "RTC: hi byte=hour, lo byte=weekday (1=Mon). Binary byte-packed",
    ),
    (
        "0x090D",
        "Sun / month",
        "R/W",
        2,
        "U",
        None,
        "RTC: hi byte=day, lo byte=month. Binary byte-packed",
    ),
    (
        "0x090E",
        "Year/reserved",
        "R/W",
        2,
        "U",
        None,
        "RTC: hi byte=year (20xx), lo byte=reserved. Binary byte-packed",
    ),
    (
        "0x090F",
        "Type (number of single-phase circuits)",
        "R/W",
        2,
        "U",
        "enum_sp_circuit_type",
        None,
    ),
    (
        "0x0910",
        "Total number of single-phase circuits",
        "R/W",
        2,
        "U",
        None,
        "Total circuit number of cabinet (single phase)",
    ),
    ("0x0911", "Address 2", "R/W", 2, "U", None, "The second address"),
    ("0x0912", "Baud rate 2", "R/W", 2, "U", "enum_baud_parity", None),
    ("0x0913", "Vacant lower board control word", "R/W", 2, "U", None, "Not Enabled"),
    (
        "0x0914",
        "Multiple rate period table 1",
        "R/W",
        42,
        "BLOCK",
        None,
        "14x3 packed, spans 0x0914-0x0928",
    ),
    (
        "0x0929",
        "Multiple rate period table 2",
        "R/W",
        42,
        "BLOCK",
        None,
        "14x3 packed, spans 0x0929-0x093D",
    ),
    (
        "0x093E",
        "Time zone table",
        "R/W",
        12,
        "BLOCK",
        None,
        "4x3 packed, spans 0x093E-0x0943",
    ),
    ("0x0944", "Order number 1, 2", "R/W", 2, "U", None, None),
    ("0x0945", "Order number 3, 4", "R/W", 2, "U", None, None),
    ("0x0946", "Backlight time", "R/W", 2, "U", None, None),
    ("0x0947", "Serial number [0][1]", "R/W", 2, "U", None, None),
    ("0x0948", "Serial number [2][3]", "R/W", 2, "U", None, None),
    ("0x0949", "Serial number [4][5]", "R/W", 2, "U", None, None),
    ("0x094A", "Serial number [6][7]", "R/W", 2, "U", None, None),
    ("0x094B", "Serial number [8][9]", "R/W", 2, "U", None, None),
    ("0x094C", "Serial number [10][11]", "R/W", 2, "U", None, None),
    ("0x094D", "Serial number [12][13]", "R/W", 2, "U", None, None),
    ("0x094E", "Switch DI state", "R", 2, "BITFIELD", None, "See Table 1"),
    ("0x094F", "Switch DO status", "R/W", 2, "BITFIELD", None, "See Table 1"),
    ("0x0950", "Line selection", "R/W", 2, "U", "enum_line_mode", None),
    ("0x0951", "PT", "R/W", 2, "U", None, "1-9999"),
    ("0x0952", "CT1", "R/W", 2, "U", None, "1-9999"),
    ("0x0953", "CT2", "R/W", 2, "U", None, "1-9999"),
    ("0x0954", "CT3", "R/W", 2, "U", None, "1-9999"),
    ("0x0955", "CT4", "R/W", 2, "U", None, "1-9999"),
    ("0x0956", "CT5", "R/W", 2, "U", None, "1-9999"),
    ("0x0957", "CT6", "R/W", 2, "U", None, "1-9999"),
    ("0x0958", "CT7", "R/W", 2, "U", None, "1-9999"),
    ("0x0959", "CT8", "R/W", 2, "U", None, "1-9999"),
    ("0x095A", "CT9", "R/W", 2, "U", None, "1-9999"),
    ("0x095B", "CT10", "R/W", 2, "U", None, "1-9999"),
    ("0x095C", "CT11", "R/W", 2, "U", None, "1-9999"),
    ("0x095D", "CT12", "R/W", 2, "U", None, "1-9999"),
    ("0x095E", "Output method", "R/W", 2, "U", "enum_output_method", None),
    ("0x095F", "Pulse Width", "R/W", 2, "U", None, "Default 500, unit ms"),
    ("0x0960", "Pulse interval", "R/W", 2, "U", None, "Default 30, unit s"),
    (
        "0x0961",
        "Whether wireless is enabled",
        "R/W",
        2,
        "U",
        "enum_enable_disable",
        None,
    ),
    ("0x0962", "Number of transformer access circuits", "R/W", 2, "U", None, "0~12"),
    (
        "0x0963",
        "Slave address rearrangement",
        "R/W",
        2,
        "U",
        "enum_enable_disable",
        None,
    ),
    ("0x0964", "Enable CE Ethernet", "R/W", 2, "U", "enum_enable_disable", None),
    ("0x0965", "Address 3", "R/W", 2, "U", None, "The third address"),
    ("0x0966", "Baud rate 3", "R/W", 2, "U", "enum_baud_parity", None),
    ("0x0967", "Debug information switch", "R/W", 2, "U", None, None),
    ("0x0968", "Gateway IP[0][1]", "R/W", 2, "U", None, "Ethernet gateway, bytes 0-1"),
    ("0x0969", "Gateway IP[2][3]", "R/W", 2, "U", None, "Ethernet gateway, bytes 2-3"),
    ("0x096A", "Subnet mask [0][1]", "R/W", 2, "U", None, None),
    ("0x096B", "Subnet mask [2][3]", "R/W", 2, "U", None, None),
    ("0x096C", "IP[0][1]", "R/W", 2, "U", None, "Local IP, bytes 0-1"),
    ("0x096D", "IP[2][3]", "R/W", 2, "U", None, "Local IP, bytes 2-3"),
    ("0x096E", "MAC address[0][1]", "R", 2, "U", None, None),
    ("0x096F", "MAC address[2][3]", "R", 2, "U", None, None),
    ("0x0970", "MAC address[4][5]", "R", 2, "U", None, None),
    ("0x0971", "The port number", "R/W", 2, "U", None, "Modbus-TCP listening port"),
    ("0x0972", "DI debounce time", "R/W", 2, "U", None, None),
]

SWITCH_AREA = [
    ("0x1800", "Switch DI state", "R", "BITFIELD", "See Table 2"),
    ("0x1801", "Switch DO status", "R/W", "BITFIELD", "See Table 2"),
]

# Harmonic region 0x1900-0x19B9 (6 quantities x 31 registers: total + 2nd..31st).
HARMONIC = [
    ("0x1900", "A phase voltage harmonic content rates"),
    ("0x191F", "B phase voltage harmonic content rates"),
    ("0x193E", "C phase voltage harmonic content rates"),
    ("0x195D", "A phase current harmonic content rates"),
    ("0x197C", "B phase current harmonic content rates"),
    ("0x199B", "C phase current harmonic content rates"),
]

HISTORY_MONTHS = [
    "previous month",
    "last two months",
    "last three months",
    "last April",
    "last May",
    "last June",
    "last July",
    "last August",
    "last September",
    "last October",
    "last November",
    "last December",
]


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(SCHEMA)

    # ---- metadata ----
    meta = [
        (
            "source_document",
            "adf400l.md",
            "ADF400L Installation and Operation Manual V1.2 (Acrel)",
        ),
        (
            "transport_rs485",
            "MODBUS-RTU",
            "RS485 interface (main module), up to 3 channels",
        ),
        (
            "transport_ethernet",
            "Modbus-TCP / TCP-IP",
            "CE Ethernet option (main module)",
        ),
        (
            "default_tcp_port_register",
            "0x0971",
            "TCP port is configurable via register 0x0971 (The port number)",
        ),
        (
            "register_model",
            "holding registers",
            "Read with FC 0x03; write with FC 0x06/0x10. FC 0x04 (input regs) mirrors 0x03 (confirmed on device).",
        ),
        ("word_size_bits", "16", "Each register is 16 bits / 2 bytes"),
        (
            "length_convention",
            "bytes",
            "Manual 'length' column is in bytes: 2 = 1 register, 4 = 2 registers",
        ),
        (
            "32bit_word_order",
            "BIG (high word first)",
            "CONFIRMED on test device 192.168.10.121: 0x0352=[0,107]=1.07 kWh (low-word-first gives nonsense). value = (regs[0]<<16)|regs[1].",
        ),
        (
            "validated_against",
            "192.168.10.121 unit-id 1 (read-only, 2026-06)",
            "Verified scaling, signed 'I' type (Q=-2), 32-bit word order, and config registers.",
        ),
        (
            "test_device_config",
            "addr=1, 9600/NONE, 2 transformer channels, 3P4L, PT=1, CT1=20, TCP port 502",
            "Configuration read back from the test device system parameter area.",
        ),
        (
            "signed_marker",
            "I",
            "'I' = signed integer, 'U' = unsigned integer (manual Remarks column)",
        ),
        (
            "user_addressing",
            "per Modbus unit-id",
            "Each user answers at its own Modbus slave/unit address; data read from the per-user-type area",
        ),
        (
            "addr_interval_transformer_three_phase",
            "3",
            "Adjacent transformer-access and three-phase users are spaced by 3 in unit address (sec. 9.3)",
        ),
        (
            "addr_interval_single_phase",
            "1",
            "Each single-phase user is spaced by 1 in unit address (sec. 9.3)",
        ),
        (
            "meter_number_values",
            "1, 37, 73, ...",
            "Allowed meter (table) numbers; meters on the same bus must differ (sec. 9.3 / 8.4)",
        ),
        (
            "addr_example",
            "table 1: 4 transformer + 4 three-phase + 12 single-phase",
            "Transformer users 1,4,7,10; three-phase 13,16,19,22; single-phase 25..36 (sec. 9.3)",
        ),
        (
            "keys",
            "SET, LEFT, RIGHT, ENTER",
            "Main-module front keys (sec. 8.4 / dimension drawing)",
        ),
        (
            "max_config",
            "12 three-phase OR 36 single-phase OR 12 transformer (2-way) circuits",
            "Module-combination maximum (sec. 1 / 2)",
        ),
    ]
    cur.executemany("INSERT INTO metadata(key,value,note) VALUES (?,?,?)", meta)

    # ---- device model ----
    cur.execute(
        "INSERT INTO device_model(id,model_code,name,manual_version,manufacturer,description) "
        "VALUES (1,?,?,?,?,?)",
        (
            "ADF400L-HSD(Y)",
            "ADF400L Series Multi User Electric Energy Meter",
            "V1.2",
            "Jiangsu Acrel Electrical Manufacturing Co., Ltd",
            "Multi-user meter: up to 12 three-phase or 36 single-phase direct-access, "
            "or 12 three-phase transformer (CT) access; metering or prepaid type.",
        ),
    )

    # ---- specifications (section 4) ----
    specs = [
        (
            "Auxiliary power",
            "Voltage",
            "Three-phase 3x220V/380V (short terminals 1,2,3 for single-phase)",
            None,
        ),
        ("Auxiliary power", "Power consumption", "<=10", "W"),
        ("Voltage input", "Rated voltage", "3x220/380V, 3x57.7/100V", None),
        ("Voltage input", "Reference frequency", "50", "Hz"),
        (
            "Current input",
            "Input Current",
            "3x1(6)A (transformer access), 3x10(80)A (direct access)",
            None,
        ),
        ("Current input", "Starting current", "1per-mille Ib (1‰Ib)", None),
        ("Measuring performance", "Measurement accuracy", "0.5s level", None),
        ("Measuring performance", "Clock accuracy", "<=0.5", "s/d"),
        (
            "Pulse",
            "Pulse output",
            "Each three-phase metering module has 1 active energy pulse output",
            None,
        ),
        ("Pulse", "Pulse Width", "80±20", "ms"),
        ("Pulse", "Pulse constant (transformer)", "6400", "imp/kWh"),
        ("Pulse", "Pulse constant (direct)", "400", "imp/kWh"),
        ("Switch", "Main module", "2DI+2DO (DI dry contact)", None),
        (
            "Switch",
            "Slave module",
            "Transformer slave 4DI+4DO (DI 220V wet contact)",
            None,
        ),
        ("Communication", "Infrared interface", "Infrared communication", None),
        ("Communication", "RS485 interface", "MODBUS-RTU", None),
        ("Communication", "Ethernet interface", "Modbus-TCP, TCP/IP", None),
        ("Surroundings", "Operating temperature", "-20 ~ +60", "C"),
        ("Surroundings", "Storage temperature", "-30 ~ +70", "C"),
        ("Surroundings", "Humidity", "<=95 (no condensation)", "%RH"),
        ("Surroundings", "Altitude", "<=2000", "m"),
    ]
    cur.executemany(
        "INSERT INTO specification(category,parameter,value,unit) VALUES (?,?,?,?)",
        specs,
    )

    # ---- user types ----
    cur.executemany(
        "INSERT INTO user_type(code,name,description) VALUES (?,?,?)",
        [
            (
                "single_phase",
                "Single-phase user",
                "Direct-access single-phase circuit; uses the single-phase data area.",
            ),
            (
                "three_phase",
                "Three-phase user",
                "Direct-access three-phase circuit; uses the three-phase data area.",
            ),
            (
                "transformer",
                "Transformer (CT) access user",
                "CT-access three-phase circuit; uses the three-phase data area, apply CT ratio.",
            ),
            (
                "common",
                "Device / main module",
                "Device-level configuration shared by all users.",
            ),
        ],
    )

    # ---- register areas ----
    areas = [
        (
            "Single-phase data area",
            "0x0300",
            "0x0320",
            "single_phase",
            "Per single-phase user measurements/energy/prepaid.",
        ),
        (
            "Three-phase data area",
            "0x033F",
            "0x0396",
            "three_phase",
            "Per three-phase / transformer user measurements/energy/prepaid.",
        ),
        (
            "Multiple rate area",
            "0x0400",
            "0x045F",
            "common",
            "Multi-rate (tip/peak/flat/valley) energy, single- and three-phase.",
        ),
        (
            "Prepaid area",
            "0x0500",
            "0x0547",
            "common",
            "Prices, alarm amounts, purchases (single- and three-phase).",
        ),
        (
            "Time zone area",
            "0x0600",
            "0x0667",
            "common",
            "Time-control switches and working/rest-day control tables.",
        ),
        (
            "Load control area",
            "0x0700",
            "0x071F",
            "common",
            "Load-control thresholds and timers (single- and three-phase).",
        ),
        (
            "Strong control zone",
            "0x0800",
            "0x0804",
            "common",
            "Forced control category and control words.",
        ),
        (
            "System parameter area",
            "0x0900",
            "0x0972",
            "common",
            "Comms, RTC, circuit counts, CT/PT, network, IDs.",
        ),
        (
            "Switch area",
            "0x1800",
            "0x1801",
            "common",
            "Live DI/DO state (see Table 2).",
        ),
        (
            "Harmonic region",
            "0x1900",
            "0x19B9",
            "three_phase",
            "Per-phase voltage/current harmonic content rates (total + 2..31).",
        ),
        (
            "Historic Power District",
            "0x1A00",
            "0x1A0B",
            "common",
            "Last 12 months of frozen energy data (20 regs each).",
        ),
        (
            "Recharge record area",
            "0x1B00",
            "0x1B13",
            "common",
            "Last 20 recharge records (20 regs each).",
        ),
    ]
    area_id = {}
    for name, sh, eh, applies, desc in areas:
        cur.execute(
            "INSERT INTO register_area(name,start_addr_hex,start_addr_dec,end_addr_hex,end_addr_dec,applies_to,description)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, sh, h2d(sh), eh, h2d(eh), applies, desc),
        )
        area_id[name] = cur.lastrowid

    def add_reg(
        area,
        addr,
        name,
        access,
        length_bytes,
        dtype,
        scale,
        unit,
        user_type,
        category,
        enum_group=None,
        remarks=None,
    ):
        cur.execute(
            "INSERT INTO register(area_id,address_hex,address_dec,data_item,access,"
            "length_registers,length_bytes,data_type,scale,unit,user_type,category,enum_group,remarks)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                area_id[area],
                addr,
                h2d(addr),
                name,
                access,
                max(1, length_bytes // 2),
                length_bytes,
                dtype,
                scale,
                unit,
                user_type,
                category,
                enum_group,
                remarks,
            ),
        )

    # Single-phase / three-phase data areas
    for addr, name, acc, lb, dt, sc, un, cat in SINGLE_PHASE:
        add_reg(
            "Single-phase data area",
            addr,
            name,
            acc,
            lb,
            dt,
            sc,
            un,
            "single_phase",
            cat,
        )
    for addr, name, acc, lb, dt, sc, un, cat in THREE_PHASE:
        add_reg(
            "Three-phase data area", addr, name, acc, lb, dt, sc, un, "three_phase", cat
        )

    # Multiple rate area
    for addr, name, acc, ut, un in MULTI_RATE:
        add_reg("Multiple rate area", addr, name, acc, 4, "U", 0.01, un, ut, "energy")

    # Prepaid area
    for addr, name, lb, dt, sc, un, ut in PREPAID:
        add_reg("Prepaid area", addr, name, "R/W", lb, dt, sc, un, ut, "prepaid")

    # Time zone area
    for addr, name, acc, lb, dt, sc, ut, rem in TIME_ZONE:
        add_reg(
            "Time zone area", addr, name, acc, lb, dt, sc, None, ut, "time", remarks=rem
        )

    # Load control area
    for addr, name, sc, ut, un in LOAD_CONTROL:
        add_reg("Load control area", addr, name, "R/W", 2, "U", sc, un, ut, "control")

    # Strong control zone
    for addr, name, ut, eg, rem in STRONG_CONTROL:
        add_reg(
            "Strong control zone",
            addr,
            name,
            "R/W",
            2,
            "U",
            None,
            None,
            ut,
            "control",
            enum_group=eg,
            remarks=rem,
        )

    # System parameter area
    for addr, name, acc, lb, dt, eg, rem in SYSTEM:
        cat = (
            "network"
            if (
                "IP" in name
                or "MAC" in name
                or "mask" in name
                or "port" in name.lower()
                or "Gateway" in name
            )
            else "config"
        )
        add_reg(
            "System parameter area",
            addr,
            name,
            acc,
            lb,
            dt,
            None,
            None,
            "common",
            cat,
            enum_group=eg,
            remarks=rem,
        )

    # Switch area
    for addr, name, acc, dt, rem in SWITCH_AREA:
        add_reg(
            "Switch area",
            addr,
            name,
            acc,
            2,
            dt,
            None,
            None,
            "common",
            "status",
            remarks=rem,
        )

    # Harmonic region (block per quantity: 31 registers = 62 bytes)
    for addr, name in HARMONIC:
        add_reg(
            "Harmonic region",
            addr,
            name,
            "R",
            62,
            "ARRAY",
            0.01,
            "%",
            "three_phase",
            "harmonic",
            remarks="31 registers: total content rate then 2nd..31st",
        )

    # Historic Power District (12 monthly blocks, 20 regs = 40 bytes)
    for i, label in enumerate(HISTORY_MONTHS):
        addr = "0x%04X" % (0x1A00 + i)
        add_reg(
            "Historic Power District",
            addr,
            "Historical energy data for %s" % label,
            "R",
            40,
            "BLOCK",
            None,
            None,
            "common",
            "history",
            remarks="Freeze time (year/month, day/hour) + tip/peak/flat/valley active energy",
        )

    # Recharge record area (20 blocks, 20 regs = 40 bytes)
    for i in range(20):
        addr = "0x%04X" % (0x1B00 + i)
        ord_lbl = (
            "Last recharge record block"
            if i == 0
            else "Last %d recharge record blocks" % (i + 1)
        )
        add_reg(
            "Recharge record area",
            addr,
            ord_lbl,
            "R",
            40,
            "BLOCK",
            None,
            None,
            "common",
            "record",
            remarks="Recharge time (Y/M, D/H, m/s), purchase count, amount, remaining, total consumption",
        )

    # ---- enum groups & values ----
    enum_groups = [
        (
            "enum_baud_parity",
            "Baud rate / parity word",
            "High byte = parity, low byte = baud-rate code",
        ),
        ("enum_parity", "Parity (check digit, high byte)", None),
        ("enum_baud", "Baud rate (low byte)", None),
        (
            "enum_protocol",
            "Protocol selection word (0x0908)",
            "High byte = meter type, low byte = protocol",
        ),
        ("enum_meter_type", "Meter type (high byte of 0x0908)", None),
        ("enum_line_mode", "Line / wiring mode", None),
        ("enum_output_method", "Relay/pulse output method", None),
        ("enum_enable_disable", "Enable / disable", None),
        ("enum_strong_control_enable", "Strong control enable", None),
        ("enum_strong_control_state", "Strong control state", None),
        (
            "enum_strong_control_word",
            "Strong control word bits",
            "High bit = open, low bit = closed",
        ),
        ("enum_single_three_category", "Single/three-phase category (0x0800)", None),
        ("enum_sp_circuit_type", "Single-phase circuit type (0x0910)", None),
        ("enum_encryption", "Encryption switch", None),
        ("enum_relay_setting", "Relay setting (menu 'do')", None),
    ]
    cur.executemany(
        "INSERT INTO enum_group(code,name,description) VALUES (?,?,?)", enum_groups
    )

    enum_values = [
        ("enum_parity", "0", "NONE", None),
        ("enum_parity", "1", "ODD", None),
        ("enum_parity", "2", "EVEN", None),
        ("enum_baud", "0", "9600", None),
        ("enum_baud", "1", "9600", None),
        ("enum_baud", "2", "4800", None),
        ("enum_baud", "3", "2400", None),
        ("enum_baud", "4", "1200", None),
        ("enum_meter_type", "0", "Prepaid", None),
        ("enum_meter_type", "1", "Metering type", None),
        ("enum_protocol", "0", "modbus", "Low byte"),
        ("enum_line_mode", "0", "3P4L (three-phase four-wire)", None),
        ("enum_line_mode", "1", "3P3L (three-phase three-wire)", None),
        ("enum_output_method", "0", "L: Level output", None),
        ("enum_output_method", "1", "P: Pulse output", None),
        ("enum_enable_disable", "0", "Disable", None),
        ("enum_enable_disable", "1", "Enable", None),
        ("enum_strong_control_enable", "0", "Disable", None),
        ("enum_strong_control_enable", "1", "Enable", None),
        ("enum_strong_control_enable", "2", "Invalid", None),
        ("enum_strong_control_state", "0", "Disconnect", None),
        ("enum_strong_control_state", "1", "Closure", None),
        ("enum_strong_control_state", "2", "Invalid", None),
        ("enum_strong_control_word", "high_bit=1", "Open", None),
        ("enum_strong_control_word", "low_bit=1", "Closed", None),
        ("enum_single_three_category", "0", "Three-phase", None),
        ("enum_single_three_category", "1", "Single-phase", None),
        ("enum_sp_circuit_type", "0", "36 circuits", None),
        ("enum_sp_circuit_type", "1", "24 circuits", None),
        ("enum_sp_circuit_type", "2", "12 circuits", None),
        ("enum_encryption", "on", "Encryption on", None),
        ("enum_encryption", "oFF", "Encryption off", None),
        ("enum_relay_setting", "L", "Level output", None),
        ("enum_relay_setting", "P", "Pulse output", None),
    ]
    cur.executemany(
        "INSERT INTO enum_value(group_code,raw_value,label,note) VALUES (?,?,?,?)",
        enum_values,
    )

    # ---- bit-field maps (Tables 1 & 2) ----
    bitfields = [
        ("0x094E", 1, "DI1", "Main module digital input 1 (Table 1)"),
        ("0x094E", 2, "DI2", "Main module digital input 2 (Table 1)"),
        ("0x094F", 1, "DO1", "Main module digital output 1 (Table 1)"),
        ("0x094F", 2, "DO2", "Main module digital output 2 (Table 1)"),
        ("0x1800", 1, "DI1", "Live switch DI1 (Table 2)"),
        ("0x1801", 1, "DO1", "Live switch DO1 (Table 2)"),
        ("0x1801", 2, "DO2", "Live switch DO2 (Table 2)"),
    ]
    cur.executemany(
        "INSERT INTO bitfield(register_hex,bit_position,signal,description) VALUES (?,?,?,?)",
        bitfields,
    )

    # ---- card error codes ----
    card_errors = [
        ("Err01", "Write back failure"),
        ("Err02", "Data error"),
        ("Err03", "Undefined card"),
        ("Err04", "This account opening card has been used"),
        ("Err10", "Insert the account opening card into the opened account meter"),
        (
            "Err11",
            "Insert the electricity purchase card into the meter without an account",
        ),
        ("Err12", "User card error"),
        ("Err13", "Wrong number of purchases"),
        ("Err14", "Non-present card"),
        ("Err15", "Wrong account card type"),
    ]
    cur.executemany(
        "INSERT INTO card_error_code(code,meaning) VALUES (?,?)", card_errors
    )

    # ---- module error codes ----
    module_errors = [
        ("Err1", "Same type module address error"),
        ("Err2", "Module location does not match module type"),
        ("Err3", "Module missing"),
    ]
    cur.executemany(
        "INSERT INTO module_error_code(code,meaning) VALUES (?,?)", module_errors
    )

    # ---- programming menu (section 8.4) ----
    menu = [
        (
            "Addr 1",
            "/",
            "Mailing address settings 1",
            "1, 37, 73, 109 (add sequentially +36) ...",
        ),
        ("bAUd 1", "/", "Baud rate selection 1", "9600, 4800, 2400, 1200"),
        (
            "Addr 2",
            "/",
            "Mailing address settings 2",
            "1, 37, 73, 109 (add sequentially +36) ...",
        ),
        ("bAUd 2", "/", "Baud rate selection 2", "9600, 4800, 2400, 1200"),
        ("CodE", "/", "Password setting", "0-9999"),
        ("bLt.AE", "/", "Backlight setting", "0-999"),
        ("FCEn", "/", "Strong control enable", "0: Disable, 1: Enable, 2: Invalid"),
        ("FCStA", "/", "Strong control state", "0: Disconnect, 1: Closure, 2: Invalid"),
        (
            "HPHnUn",
            "/",
            "Number of transformer access circuits",
            "0, 2, 4, 6, 8, 10, 12",
        ),
        ("SPHnUn", "/", "Number of three-phase circuits", "0-12"),
        ("dPHnUn", "/", "Number of single-phase circuits", "0-36"),
        ("do", "/", "Relay settings", "L: Level output, P: Pulse output"),
        ("LinE", "/", "Line selection", "3P4L: four-wire, 3P3L: three-wire"),
        ("PtCt", "Pt", "Voltage transformation ratio setting", "1-9999"),
        ("PtCt", "Ct1", "Current ratio setting 1", "1-9999"),
        ("PtCt", "Ct2", "Current ratio setting 2", "1-9999"),
        ("PtCt", "Ct3", "Current ratio setting 3", "1-9999"),
        ("PtCt", "Ct4", "Current ratio setting 4", "1-9999"),
        ("PtCt", "Ct5", "Current ratio setting 5", "1-9999"),
        ("PtCt", "Ct6", "Current ratio setting 6", "1-9999"),
        ("PtCt", "Ct7", "Current ratio setting 7", "1-9999"),
        ("PtCt", "Ct8", "Current ratio setting 8", "1-9999"),
        ("PtCt", "Ct9", "Current ratio setting 9", "1-9999"),
        ("PtCt", "Ct10", "Current ratio setting 10", "1-9999"),
        ("PtCt", "Ct11", "Current ratio setting 11", "1-9999"),
        ("PtCt", "Ct12", "Current ratio setting 12", "1-9999"),
        (
            "dbUGPASS",
            "/",
            "Debug function settings",
            "0-9999 (6606: Slave address rearrangement)",
        ),
        ("CESEt", "GAtE.IP1", "Gateway IP address 1, 2", None),
        ("CESEt", "GAtE.IP2", "Gateway IP address 3, 4", None),
        ("CESEt", "nASb1", "Subnet mask 1, 2", None),
        ("CESEt", "nASb2", "Subnet mask 3, 4", None),
        ("CESEt", "iP1", "Local IP address 1, 2", None),
        ("CESEt", "iP2", "Local IP address 3, 4", None),
        ("CESEt", "Port", "Port", None),
        (
            "EnCrYPt",
            "/",
            "Encryption switch settings",
            "on: encryption on, oFF: encryption off",
        ),
        ("UEr", "/", "Software number and version number", None),
    ]
    for i, (fl, sl, mean, rng) in enumerate(menu, start=1):
        cur.execute(
            "INSERT INTO programming_menu(seq,first_level,second_level,meaning,value_range) VALUES (?,?,?,?,?)",
            (i, fl, sl, mean, rng),
        )

    # ---- key-display sequence (section 8.2) ----
    screens = [
        ("Ua, Ub", "Phase voltage Ua and Ub", "V"),
        ("Uc, Uab", "Phase voltage Uc and line voltage Uab", "V"),
        ("Ubc, Uca", "Line voltage Ubc and Uca", "V"),
        ("F, Ia", "Frequency F and current Ia", "Hz / A"),
        ("Ib, Ic", "Current Ib and Ic", "A"),
        ("Pa, Pb", "Active power Pa and Pb", "kW"),
        ("Pc, Ps", "Active power Pc and total active power", "kW"),
        ("Qa, Qb", "Reactive power Qa and Qb", "kvar"),
        ("Qc, Qs", "Reactive power Qc and total reactive power", "kvar"),
        ("Sa, Sb", "Apparent power Sa and Sb", "kVA"),
        ("Sc, Ss", "Apparent power Sc and total apparent power", "kVA"),
        ("PFa, PFb", "Power factor PFa and PFb", None),
        ("PFc, PFs", "Power factor PFc and total power factor", None),
        ("Date / time", "Date and time", None),
        ("F1, F2", "Tip price and peak price", "yuan/kWh"),
        ("F3, F4", "Flat price and valley price", "yuan/kWh"),
    ]
    for i, (content, vals, un) in enumerate(screens, start=1):
        cur.execute(
            "INSERT INTO display_screen(seq,content,values_shown,unit) VALUES (?,?,?,?)",
            (i, content, vals, un),
        )

    # ---- modbus function codes (standard; not from manual) ----
    fcs = [
        (
            "0x03",
            "Read Holding Registers",
            "Read measurement/config registers",
            "Modbus standard",
        ),
        ("0x06", "Write Single Register", "Write one R/W register", "Modbus standard"),
        (
            "0x10",
            "Write Multiple Registers",
            "Write multi-register values (e.g. 4-byte energies, IP)",
            "Modbus standard",
        ),
    ]
    cur.executemany(
        "INSERT INTO modbus_function(code,name,usage,source) VALUES (?,?,?,?)", fcs
    )

    con.commit()

    # ---- summary ----
    tables = [
        r[0]
        for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print("Database created:", DB_PATH)
    for t in tables:
        n = cur.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        print("  %-20s %4d rows" % (t, n))
    con.close()


if __name__ == "__main__":
    main()
