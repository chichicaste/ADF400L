# ADF400L Documentation & Tools

Documentación técnica, base de datos de registro Modbus y herramientas Python para el **medidor de energía eléctrica multiusuario Serie ADF400L** de Acrel.

## Descripción

El ADF400L es un medidor de energía eléctrica multiusuario que soporta hasta:

- **12 circuitos trifásicos** de medición directa
- **36 circuitos monofásicos** de medición directa
- **12 circuitos** de acceso por transformador (TC)
- Combinaciones híbridas de los anteriores

Se comunica vía **RS485 (MODBUS-RTU)** o **Ethernet (Modbus-TCP)**. Este proyecto documenta el protocolo de comunicación, el mapa de registros completo y provee herramientas para interactuar con el dispositivo.

## Contenido

| Archivo / Directorio | Descripción |
|:---------------------|:------------|
| `adf400l.md` | Documentación completa del manual V1.2 convertida a Markdown (especificaciones, cableado, funciones, mapa de registros Modbus, menú de programación LCD) |
| `adf400l.pdf` | Manual original en PDF |
| `images/` | Diagramas de cableado, dimensiones, pantallas LCD y displays de teclas (17 imágenes) |
| `db/` | Base de datos SQLite con el mapa de registros Modbus, especificaciones, menús y códigos de error |
| `db/build.py` | Script para reconstruir la base de datos desde `adf400l.md` |
| `db/README.md` | Documentación de la base de datos y ejemplos de consulta SQL |
| `probe_read.py` | Script de prueba de lectura Modbus-TCP (sondeo rápido) |
| `probe_detail.py` | Lectura detallada del área de parámetros del sistema y datos trifásicos |
| `read_config.py` | Lee y decodifica la configuración del sistema (parámetros de comunicación, red, CT/PT) |

## Estructura del proyecto

```
ADF400L/
├── adf400l.md              # Documentación técnica (manual V1.2)
├── adf400l.pdf             # Manual original PDF
├── README.md               # Este archivo
├── LICENSE                 # Licencia MIT
├── read_config.py          # Lector de configuración Modbus
├── probe_read.py           # Sonda de lectura rápida
├── probe_detail.py         # Lectura detallada del dispositivo
├── images/                 # Diagramas e imágenes
│   ├── adf400l_img-000.jpeg ... adf400l_img-016.jpeg
│   └── adf400l_keydisp_1.png ... adf400l_keydisp_5.png
└── db/
    ├── build.py            # Constructor de la base de datos
    ├── adf400l.db          # Base de datos SQLite
    └── README.md           # Documentación de la BD
```

## Requisitos

- Python 3.6+
- [pymodbus](https://github.com/riptideio/pymodbus) (`pip install pymodbus`)

## Uso

### Leer configuración del dispositivo

```bash
python read_config.py
```

### Sondeo rápido Modbus

```bash
python probe_read.py
```

### Lectura detallada

```bash
python probe_detail.py
```

### Reconstruir base de datos

```bash
python db/build.py
```

## Base de datos SQLite

La base de datos `db/adf400l.db` contiene el mapa de registros Modbus completo con direcciones, escalas, unidades, tipos de dato, y tablas auxiliares (enumeraciones, campos de bits, menú de programación, códigos de error).

Ver `db/README.md` para el esquema y ejemplos de consulta.

## Protocolo de comunicación

- **Transporte**: RS485 (MODBUS-RTU) o Ethernet (Modbus-TCP)
- **Funciones**: FC 0x03 (lectura), FC 0x06/0x10 (escritura)
- **Formato**: 16 bits/registro, Big-endian para valores de 32 bits
- **Direccionamiento**: Cada usuario responde en su propia unidad Modbus; usuarios trifásico/transformador espaciados por 3, monofásicos por 1

## Copyright

- **Codigo y herramientas** — (c) 2026 [@chichicaste](https://github.com/chichicaste) — Licencia MIT.
- **Documentacion tecnica** — (c) Acrel Electric Co., Ltd. Manual de instalacion y operacion V1.2. Todos los derechos reservados.

## Licencia

El codigo en este repositorio se distribuye bajo licencia MIT. Ver `LICENSE` para mas detalles.
La documentacion (`adf400l.md`, `adf400l.pdf`, imagenes) es propiedad de Acrel y se incluye solo con fines de referencia tecnica.
