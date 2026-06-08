# Registro de cambios en el medidor — trazabilidad

Bitácora de **escrituras Modbus** realizadas sobre el medidor físico, con los valores
**originales (de fábrica)** y **nuevos** para poder auditar o **restaurar**.

> La IP (`192.168.0.20`) y los `uid` son **ejemplos** — sustitúyalos por los de su instalación.

| Campo | Valor |
|:--|:--|
| Dispositivo | **192.168.0.20:502** (Modbus-TCP) |
| Modo del medidor | Metering (`0x0908 = 0x0100`) — sin cambios |
| Usuarios afectados | **uid 1** y **uid 4** (acceso por transformador, área trifásica) |
| Fecha | 2026-06-07 |
| Herramienta | `write_tariff_es.py` (FC 0x10, con verificación por relectura) |
| Tarifa aplicada | El Salvador **BT horaria** (cargo de energía nacional, CAESS 15-ene-2025) |

> **Word order 32 bits = BIG** (`valor = (reg[0]<<16)|reg[1]`). Precios con escala `0.01 USD/kWh`.

---

## 1. Precios multitarifa trifásicos (prepago) — uid 1 y uid 4

| Registro | Tarifa Acrel | Tramo ES | Original | Nuevo | = USD/kWh |
|:--|:--|:--|--:|--:|--:|
| `0x0537` | tip (F1)    | Punta (dup.) | `10000` | `21` | 0.21 |
| `0x0539` | peak (F2)   | Punta 18:00–22:59 | `10000` | `21` | 0.21 |
| `0x053B` | flat (F3)   | Resto 05:00–17:59 | `10000` | `18` | 0.18 |
| `0x053D` | valley (F4) | Valle 23:00–04:59 | `10000` | `21` | 0.21 |

`10000` (= 100.00) era el **placeholder de fábrica**. Cada precio es U32 (2 registros).

---

## 2. Tabla de períodos multitarifa — uid 1 y uid 4

Escrita **idéntica** en la tabla 1 (`0x0914`–`0x0928`) y la tabla 2 (`0x0929`–`0x093D`),
porque el selector estacional `0x093E` alterna entre ambas. 21 registros cada una.

**Original (patrón de fábrica, idéntico en ambas tablas):**
```
0x0100 0x0202 0x0004 0x0300 0x0604 0x0008 0x0100 0x0A02 0x000C 0x0300 0x0E04
0x0010 0x0100 0x1202 0x0013 0x0300 0x1404 0x0015 0x0100 0x1602 0x0017
```

**Nuevo (calendario El Salvador Punta/Resto/Valle):**
```
0x0400 0x0003 0x0500 0x0212 0x0004 0x1700 0x0417 0x0504 0x170A 0x0417 0x0F04
0x1714 0x0417 0x1904 0x171E 0x0417 0x2304 0x1728 0x0417 0x2D04 0x1732
```

Decodificación del nuevo calendario (byte-packed `Período,Hora,Minuto`; índice 1=tip 2=peak 3=flat 4=valley):

| Transición | Hora | Tarifa (idx) | Tramo ES |
|:--|:--|:--|:--|
| 1 | 00:00 | valley (4) | Valle |
| 2 | 05:00 | flat (3) | Resto |
| 3 | 18:00 | peak (2) | Punta |
| 4 | 23:00 | valley (4) | Valle |
| 5–14 | 23:05…23:50 | valley (4) | relleno monótono |

---

## 3. Restauración (rollback)

Para volver a fábrica, escribir los **valores originales** de arriba con FC 0x10:

```python
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient("192.168.0.20", port=502); c.connect()
FACTORY = [0x0100,0x0202,0x0004,0x0300,0x0604,0x0008,0x0100,0x0A02,0x000C,0x0300,
           0x0E04,0x0010,0x0100,0x1202,0x0013,0x0300,0x1404,0x0015,0x0100,0x1602,0x0017]
for uid in (1, 4):
    for base in (0x0914, 0x0929):                 # period tables -> factory
        c.write_registers(address=base, values=FACTORY, slave=uid)
    for a in (0x0537, 0x0539, 0x053B, 0x053D):    # prices -> 100.00 (10000)
        c.write_registers(address=a, values=[0, 10000], slave=uid)
c.close()
```

---

## 4. NO modificado (verificado)

Modo del medidor (`0x0908`), dirección/baudios, red (IP/MAC/puerto), CT/PT, selección de línea,
umbrales de control de carga / factor de potencia, interruptores de prepago (`0x0500`/`0x0536` = 0)
y acumuladores de energía. Solo se escribieron los registros listados en §1 y §2.

---

## 5. Pendiente

- **Vínculo índice→precio** (1=tip…4=valley): seguro por orden estructural, **sin confirmar por
  observación** de acumuladores bajo carga. Ver §9 de `docs/tarifa_electrica_el_salvador.md`.
- En **modo Metering** estos precios y el calendario son de medición/visualización; **no** accionan
  relé ni descuentan saldo (eso requiere modo Prepago, `0x0908` byte alto = 0 — no modificado).
