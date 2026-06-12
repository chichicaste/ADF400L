# Tarifa eléctrica de El Salvador — Ecuaciones y datos técnicos para reprogramar el medidor Acrel ADF400L

> Documento de referencia para configurar **moneda (USD)** y **costo de energía** en medidores
> ADF400L (Modbus). Reúne el marco regulatorio salvadoreño, las ecuaciones de facturación por
> sector, los valores de cargo de energía vigentes y el **mapeo exacto a los registros Modbus**
> del Acrel.
>
> **Moneda oficial:** Dólar de los Estados Unidos (USD), curso legal desde 2001. La Ley Bitcoin
> fue derogada como moneda de curso legal en enero de 2025 → **toda la programación se hace en USD**.

---

## 1. Marco regulatorio

| Elemento | Detalle |
|:--|:--|
| Regulador | **SIGET** (Superintendencia General de Electricidad y Telecomunicaciones) |
| Política / fijación de precio de energía | **DGEHM** (Dirección General de Energía, Hidrocarburos y Minas) / CNE |
| Ley base | Ley General de Electricidad y su Reglamento |
| Cargo de Energía | **Nacional por ley** (mismo precio para todas las distribuidoras), fijado por DGEHM/CNE y ajustado **trimestralmente** (15 ene / 15 abr / 15 jul / 15 oct) |
| Cargos de Distribución y Comercialización | Se fijan/aprueban **anualmente** (vigentes desde el 1 de enero) y **no varían** con el ajuste trimestral; **sí difieren por distribuidora** (dependen de la red) |
| Impuestos | **IVA 13 %** (no incluido en los cargos del pliego) + **tasas municipales** (varían por alcaldía) |
| Distribuidoras | CAESS, AES CLESA, EEO, DEUSEM (grupo AES), **DELSUR**, EDESAL, B&D, Abruzzo, etc. |

> **Importante:** el **cargo de energía** (USD/kWh) es de **alcance nacional** — los valores
> publicados por AES/CAESS aplican de forma general a todo el país. Solo los **cargos de
> distribución y comercialización** dependen de la distribuidora.

---

## 2. Categorías tarifarias (todos los sectores)

Clasificación por **demanda máxima mensual** y por **nivel de tensión**:

| Clasificación por demanda | Umbral |
|:--|:--|
| **Pequeña demanda** | ≤ 10 kW |
| **Mediana demanda** | > 10 kW y ≤ 50 kW |
| **Gran demanda** | > 50 kW |

| Nivel de tensión | Umbral |
|:--|:--|
| **Baja tensión (BT)** | ≤ 600 V |
| **Media tensión (MT)** | > 600 V y < 115 000 V |

### Códigos de tarifa

| Código | Sector / categoría | Demanda | Medición |
|:--|:--|:--|:--|
| **R** | Residencial | Pequeña (≤10 kW) | Energía (kWh), por bloques |
| **G** | General / comercial | Pequeña (≤10 kW) | Energía (kWh) |
| **AP** | Alumbrado público | Pequeña (≤10 kW) | Energía (kWh) |
| **MD5** | Mediana demanda, BT | >10–50 kW | **Horaria** (punta/resto/valle) + demanda (kW) |
| **MD6** | Mediana demanda, MT | >10–50 kW | **Horaria** + demanda (kW) |
| **GD1** | Gran demanda, BT | >50 kW | **Horaria** + demanda (kW) |
| **GD2** | Gran demanda, MT | >50 kW | **Horaria** + demanda (kW) |

> Las pequeñas demandas (R, G, AP) facturan **solo energía** (sin medición de demanda).
> Las medianas y grandes demandas usan **medidor horario** y **medición de potencia (kW)**.

---

## 3. Bloques horarios (Tarifa Horaria) — medianas y grandes demandas

| Período | Horario | Uso típico |
|:--|:--|:--|
| **Punta** | **18:00 – 22:59** | Energía más cara |
| **Resto** (llano) | **05:00 – 17:59** | Energía intermedia |
| **Valle** | **23:00 – 04:59** | Energía más barata |

Cobertura 24 h continua. Estos tres tramos son la base para mapear las **4 tarifas** del Acrel
(ver §7).

---

## 4. Componentes de cargo y ecuaciones de facturación

Notación: `E` = energía (kWh); `Dmax` = demanda máxima mensual (kW); `FP` = factor de potencia.

### 4.1 Cargos

| Cargo | Unidad | Aplica a | Descripción |
|:--|:--|:--|:--|
| **Comercialización** `C_com` | USD/usuario·mes | todos | Valor **fijo** mensual (emisión de factura, atención) |
| **Energía** `p_E` | USD/kWh | todos | Costo de energía; por bloques (R) u **horario** (MD/GD); ajuste trimestral |
| **Distribución** `c_D` | USD/kWh (pequeña) **o** USD/kW·mes (mediana/gran) | todos | Uso de red; en MD/GD se calcula sobre `Dmax` |
| **Potencia/Demanda** | incluido en distribución (USD/kW·mes) | MD/GD | Sobre la demanda máxima registrada |

### 4.2 Ecuación general de la factura mensual

```
Factura = Cargo_Energía + Cargo_Distribución + Cargo_Comercialización
          + Recargo_FP + Otros        (× 1.13 IVA)  + Tasas_municipales
```

### 4.3 Pequeña demanda — Residencial (R), bloques crecientes

El cargo de energía residencial es por **bloques** de consumo:

```
Cargo_Energía = E_b1·p_b1 + E_b2·p_b2 + E_b3·p_b3
```
donde, para CAESS (ver §5):
- `E_b1` = primeros 99 kWh        → `p_b1`
- `E_b2` = siguientes 100 kWh     → `p_b2`
- `E_b3` = kWh restantes (>199)   → `p_b3`

```
Cargo_Distribución = E · c_D            (USD/kWh)
Factura_R = (Cargo_Energía + E·c_D + C_com) × 1.13 + Tasas_municipales
```

### 4.4 Pequeña demanda — General (G) y Alumbrado público (AP)

Energía a precio único (sin bloques):

```
Factura = (E · p_E + E · c_D + C_com) × 1.13 + Tasas_municipales
```

### 4.5 Mediana / Gran demanda (MD5, MD6, GD1, GD2) — horaria

```
Cargo_Energía   = E_punta·p_punta + E_resto·p_resto + E_valle·p_valle
Cargo_Distrib.  = Dmax · c_Dkw                     (USD/kW·mes)
Factura = (Cargo_Energía + Dmax·c_Dkw + C_com + Recargo_FP) × 1.13 + Tasas_municipales
```

### 4.6 Recargo por bajo factor de potencia (FP < 0.90)

Aplica a usuarios con medición de potencia (MD/GD). Sea `Δ = (0.90 − FP)` en **centésimas**:

| Rango de FP | Recargo sobre el **Cargo de Energía** |
|:--|:--|
| 0.75 ≤ FP < 0.90 | **+1 %** por cada centésima por debajo de 0.90 → `+ (90 − ⌊FP·100⌋)·1 %` |
| 0.60 ≤ FP < 0.75 | **+15 %** + **2 %** por cada centésima por debajo de 0.75 |
| FP < 0.60 | El distribuidor puede **suspender** el servicio |

> El medidor expone FP por fase y total (`0x034D`…`0x0350`, escala 0.001) → el recargo puede
> calcularse en la aplicación. Tras notificación, el usuario tiene **90 días** para corregir.

### 4.7 Subsidio / congelamiento residencial

Usuarios **R y G** con consumo promedio **≤ 300 kWh-mes** (1.er trimestre del año de referencia)
mantienen una **tarifa congelada** (subsidio estatal). El resto paga el pliego vigente. Verificar el
umbral y la tarifa congelada en cada boletín trimestral de SIGET.

---

## 5. Valores vigentes — Cargo de Energía (nacional, desde 15-ene-2025, en USD, **sin IVA**)

> Fuente: pliego CAESS, Acuerdo N° 02/2025/DE (DGEHM). El **cargo de energía es nacional por ley**,
> de modo que estos valores aplican de forma general. **Los cargos de Comercialización y
> Distribución no varían con este ajuste** y deben tomarse del pliego de distribución anual de cada
> distribuidora.

### Pequeñas demandas (≤10 kW) — USD/kWh

| Tarifa | Bloque | `p_E` (USD/kWh) |
|:--|:--|--:|
| **Residencial (R)** | Bloque 1: primeros 99 kWh | **0.192553** |
| | Bloque 2: siguientes 100 kWh | **0.192662** |
| | Bloque 3: restantes | **0.190757** |
| **Uso General (G)** | único | **0.188268** |
| **Alumbrado Público (AP)** | único | **0.169213** |

### Medianas demandas (>10–50 kW) — USD/kWh

| Tarifa | Período | `p_E` (USD/kWh) |
|:--|:--|--:|
| **BT con medición de potencia** | único | **0.186032** |
| **MT con medición de potencia** | único | **0.173346** |
| **BT con medición horaria** | Punta | **0.210306** |
| | Resto | **0.177030** |
| | Valle | **0.208128** |
| **MT con medición horaria** | Punta | **0.194827** |
| | Resto | **0.164001** |
| | Valle | **0.192810** |

### Grandes demandas (>50 kW) — USD/kWh

| Tarifa | Período | `p_E` (USD/kWh) |
|:--|:--|--:|
| **Baja Tensión (GD1)** | Punta | **0.210306** |
| | Resto | **0.177030** |
| | Valle | **0.208128** |
| **Media Tensión (GD2)** | Punta | **0.194827** |
| | Resto | **0.164001** |
| | Valle | **0.192810** |

> Nota: GD1 (BT) comparte los precios de energía de la mediana BT horaria; GD2 (MT) los de la
> mediana MT horaria. **Difieren en el cargo de distribución (USD/kW·mes)**, no en la energía.
> Los valores **no incluyen IVA (13 %)**.

---

## 6. Estado y unidades del medidor ADF400L (lo relevante para programar)

| Concepto | Registro(s) | Escala / unidad | Notas |
|:--|:--|:--|:--|
| Modo del medidor | `0x0908` (byte alto) | 0=Prepago, 1=Metering | **Dispositivo de prueba = Metering (1)** |
| Reloj (RTC) | `0x090B`–`0x090E` | byte-packed binario | Debe estar en hora local para que los tramos horarios apliquen |
| Precios 1φ (尖/峰/平/谷) | `0x0501 / 0x0503 / 0x0505 / 0x0507` | **0.01 [moneda]/kWh**, U32, R/W | tip / peak / flat / valley |
| Precios 3φ | `0x0537 / 0x0539 / 0x053B / 0x053D` | **0.01 [moneda]/kWh**, U32, R/W | tip / peak / flat / valley |
| Tabla de períodos diarios (tarifa 1) | `0x0914`–`0x0928` | 14×3 empacado (Período,Hora,Minuto) | Define qué tarifa rige en cada tramo |
| Tabla de zona horaria (estacional) | `0x093E`–`0x0943` | 4×3 empacado | Rangos de fecha (no usado en ES) |
| Energía activa total | `0x035E` (3φ) / `0x0306` (1φ) | 0.01 kWh, U32 | Para cálculo de costo en software |
| Energía por tarifa (punta/…/valle) | `0x0430`–`0x045F` (3φ), `0x0400`–`0x042F` (1φ) | 0.01 kWh | Acumuladores multitarifa |
| Saldo / montos prepago | `0x0362` (saldo), `0x0509/0x050B` (alarmas), `0x050D` (recarga) | **0.01 [moneda]** | En prepago, en la moneda del medidor |
| FP total / por fase | `0x034D`–`0x0350` | 0.001 | Para recargo por bajo FP |

---

## 7. Mapeo El Salvador → 4 tarifas del Acrel

El Acrel maneja **4 tarifas** (尖 tip / 峰 peak / 平 flat / 谷 valley → pantallas LCD F1/F2/F3/F4).
El Salvador define **3 tramos**. Mapeo recomendado:

| Acrel | Pantalla | El Salvador | Horario |
|:--|:--|:--|:--|
| Peak (峰) | F2 | **Punta** | 18:00–22:59 |
| Flat (平) | F3 | **Resto** | 05:00–17:59 |
| Valley (谷) | F4 | **Valle** | 23:00–04:59 |
| Tip (尖) | F1 | = Punta (duplicado) | — (ES no usa 4.º tramo) |

### Calendario diario a cargar en la tabla de períodos (`0x0914`…)

| Transición | Hora | Tarifa que entra |
|:--|:--|:--|
| 1 | 00:00 | Valley (谷) |
| 2 | 05:00 | Flat (平) |
| 3 | 18:00 | Peak (峰) |
| 4 | 23:00 | Valley (谷) |

**Codificación VALIDADA en equipo (2026-06):** la tabla es byte-packed, 2 campos por registro
(byte alto, byte bajo), con flujo `Período₁, Hora₁, Minuto₁, Período₂, …`. El **índice de tarifa
= 1..4** → **1=tip, 2=peak, 3=flat, 4=valley** (mismo orden que los registros de precio y F1–F4).
Se escriben **14 ranuras monótonas** (las 4 transiciones reales + relleno en valle) en **ambas
tablas** (`0x0914` y `0x0929`), porque el selector estacional `0x093E` alterna entre ellas.

---

## 8. Reprogramación de moneda y costo (procedimiento)

### 8.1 Moneda → USD

El ADF400L **no tiene un registro de "moneda"**: los montos/precios son enteros con escala fija
`0.01`. La conversión a USD es **semántica**: se interpretan y se cargan los valores en USD
directamente (1 unidad de registro = 0.01 USD). El glifo en el LCD puede seguir mostrando el
símbolo de fábrica; el **valor numérico** es el que importa para la app.

### 8.2 Costo de energía

**⚠️ Limitación de resolución:** los registros de precio tienen escala **0.01 USD/kWh** → solo
2 decimales. La tarifa real tiene **6 decimales** (p. ej. 0.192553). Por eso:

- **Opción A (recomendada — modo Metering, estado actual del equipo):**
  El medidor **solo mide**; el **costo se calcula en la aplicación/BD** con precisión completa:
  ```
  costo_periodo = (ΔkWh_punta·p_punta + ΔkWh_resto·p_resto + ΔkWh_valle·p_valle)
  costo_total   = costo_periodo × 1.13 (IVA) + cargos_fijos + tasas_municipales
  ```
  Se leen los acumuladores multitarifa (`0x0430`…/`0x0400`…) o la energía total + el reloj, y se
  aplican los `p_E` de §5 con 6 decimales. Los registros de precio del medidor quedan solo como
  **referencia/visualización** (F1–F4).

- **Opción B (modo Prepago en el medidor):**
  Programar los precios redondeando a centavos (`round(p_E × 100)`), asumiendo error ≤ 0.5 ¢/kWh:

  | Tarifa Acrel | Registro 1φ | Registro 3φ | Valor a escribir (ej. MT horaria) | = USD/kWh |
  |:--|:--|:--|--:|--:|
  | Tip (F1) | `0x0501` | `0x0537` | `19` | 0.19 (=Punta) |
  | Peak (F2) | `0x0503` | `0x0539` | `19` | 0.19 (Punta 0.194827) |
  | Flat (F3) | `0x0505` | `0x053B` | `16` | 0.16 (Resto 0.164001) |
  | Valley (F4) | `0x0507` | `0x053D` | `19` | 0.19 (Valle 0.192810) |

  Escribir con FC `0x10` (Write Multiple Registers, 2 registros por precio U32, word order **BIG**:
  `valor = (reg[0]<<16)|reg[1]`). Configurar también el reloj (`0x090B`–`0x090E`) y la tabla de
  períodos (§7).

> Para facturación oficial **usar siempre la Opción A** (precisión de 6 decimales); la Opción B
> sirve para corte/aviso prepago donde el redondeo a centavos es tolerable.

### 8.3 Cargos fijos e impuestos (siempre en software)

Comercialización (USD/mes), distribución (USD/kWh o USD/kW·mes), IVA 13 % y tasas municipales
**no tienen registro en el medidor** → se aplican en la capa de aplicación sobre la energía/demanda
leída por Modbus.

### 8.4 Script de programación — `write_tariff_es.py`

Carga los 4 precios multitarifa (Opción B) en el medidor. **No escribe nada salvo `--commit`**,
verifica por relectura y **nunca** cambia el modo, dirección, baudios ni red.

```bash
# Ver el plan sin escribir (dry-run, seguro):
python write_tariff_es.py --host 192.168.0.20 --unit 1 --phase three --tariff md_mt_hor

# Escribir realmente (tras revisar el dry-run):
python write_tariff_es.py --unit 1 --phase three --tariff md_mt_hor --commit

# Además, cargar la tabla de horarios diaria (EXPERIMENTAL, encoding sin validar):
python write_tariff_es.py --unit 1 --tariff md_mt_hor --commit --with-schedule
```

| Opción | Valor |
|:--|:--|
| `--phase` | `three` (usuarios trafo/3φ, `0x0537…`) · `single` (`0x0501…`) |
| `--tariff` | `residential`, `general`, `ap`, `md_bt_pot`, `md_mt_pot`, `md_bt_hor`, `md_mt_hor`, `gd_bt`, `gd_mt` |
| `--commit` | Ejecuta la escritura (sin él = dry-run) |
| `--with-schedule` | Escribe también `0x0914…` (validar antes el índice de tarifa, §9) |

Mapeo aplicado: tip=peak=Punta, flat=Resto, valley=Valle. Precios redondeados a centavos
(escala `0.01 USD/kWh`); el error de redondeo se imprime por tarifa.

> Cada escritura sobre el medidor físico queda registrada en **[`../change.md`](../change.md)**
> (valores originales y nuevos, con instrucciones de **restauración**).

#### Estado aplicado (2026-06-07, dispositivo 192.168.0.20, uid 1 y 4 — BT horaria)

| Registro | Tarifa | Original | Nuevo | USD/kWh |
|:--|:--|--:|--:|--:|
| `0x0537` | tip | 10000 | 21 | 0.21 |
| `0x0539` | peak | 10000 | 21 | 0.21 |
| `0x053B` | flat | 10000 | 18 | 0.18 |
| `0x053D` | valley | 10000 | 21 | 0.21 |
| `0x0914`/`0x0929` | tabla de períodos | patrón fábrica | calendario ES | — |

---

## 9. Pendientes de validar en el equipo (solo lectura no basta)

1. ~~Codificación del índice de tarifa en la tabla de períodos~~ — **VALIDADO** (2026-06): byte-packed
   `Período,Hora,Minuto`, índice 1=tip/2=peak/3=flat/4=valley. Calendario ES ya cargado en
   `0x0914`/`0x0929` (uid 1 y 4).
2. **Vínculo índice→precio (comprobación final):** el mapeo 1..4→tip/peak/flat/valley se infiere del
   orden (estructuralmente seguro) pero conviene **confirmarlo observando** qué acumulador
   multitarifa (`0x0430`…/`0x0400`…) incrementa en cada tramo bajo carga real.
3. **Símbolo de moneda en LCD**: confirmar si es configurable o fijo de fábrica.
4. **Comportamiento multitarifa en modo Metering**: confirmar que los acumuladores
   `0x0400`/`0x0430` incrementan según la tabla de períodos aun sin prepago.
5. **Migración a Prepago**: requiere escribir `0x0908` (byte alto = 0) — cambia el modo del medidor.

---

## 10. Fuentes

- SIGET — Tarifas de electricidad: <https://www.siget.gob.sv/gerencias/electricidad/tarifas-de-electricidad/>
- CAESS — Pliego/Cargo de Energía vigente desde 15-ene-2025 (Acuerdo 02/2025/DE), AES El Salvador.
- AES El Salvador — Informativo para Grandes Clientes (tarifa horaria y facturación): <https://aeselsalvador.com/GrandesClientes/web_site/boletines/InfoTF.pdf>
- DELSUR — Pliego tarifario vigente: <https://www.delsur.com.sv/pliego-tarifario-vigente/>
- Manual ADF400L V1.8 y `db/adf400l.db` (mapa de registros, escalas, word order — este repositorio).

---

*Datos de cargo de energía: CAESS, vigentes 15-ene-2025. Verificar el pliego del trimestre y de la
distribuidora correspondientes antes de programar. Valores sin IVA.*
