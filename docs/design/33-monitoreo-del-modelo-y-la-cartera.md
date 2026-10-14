# SDD-33 — Monitoreo del modelo y de la cartera (`bayesrisk.monitoring`)

> **Estado: APROBADO por Cami el 2026-10-13** (S44, interactivo), con la recomendación (a) de cada
> una de las diez decisiones de §12 (D-MNT-1…10, §12-1…10): una corrida propia desde la tarjeta;
> sólo tarjetas de esquema 4; el AUC inicial de Holdout; los cuatro indicadores; la tabla de §3.5
> —redesarrollar cuando cae la discriminación, aunque recalibrar la pendiente devuelva las PD—;
> umbrales constantes; la serie recalculada por corrida; capa A en la 2.13.0 y B en la 2.14.0; la
> serie de estabilidad publicada en la B; y las dos colas de la calibración. Diseño sin código:
> **la capa A se programa en la sesión siguiente** (S45), con tests nacidos rojos, controles
> negativos y Codex sobre el código; cada release pide su OK aparte. Es el hito **H4** del ROADMAP, el tercer eslabón de la
> cadena del banco que Cami puso primero el 2026-10-07 (IFRS 9 firmable → H5 escala maestra →
> **H4** → H2b): una vez que la tarjeta está en uso, saber cada mes o trimestre si la cartera cambió,
> si el modelo sigue ordenando y si cada tramo sigue acertando su PD, y qué hacer en cada caso.
>
> **Base medida:** `main` = `100879a` (bayesrisk 2.12.0 publicada). Las cifras de §0 se midieron
> **fuera del motor**, con las reglas exactas que propone este documento, sobre la tarjeta del
> preset F1 con su escala maestra en las carteras del paquete y un contraejemplo construido. Guiones
> y salidas, sólo agregados, en el repo privado `evidencia/s44/` (`medir_h4.py`, `medir_h4_b.py`,
> `salidas/medir_h4*.txt`, `salidas/veredictos_h4.txt`). La prueba de AUC se cotejó contra dos
> fuentes oficiales del BCE (§3.6, `evidencia/s44/cotejo_bce_auc.txt`).
>
> **Corregido tras la pasada 1 de Codex** (cuatro high y cuatro medium, los ocho reales; dos
> contractuales, elevados): el contraste de cartera usa sólo las filas con desenlace (§3.3); el AUC
> también cae por **composición** con cada tramo calibrado —contraejemplo de Codex, reproducido:
> 0,716 → 0,525 sin que ninguna PD cambie—, así que redesarrollar exige además que el AUC quede bajo
> el que el modelo espera para la composición del periodo (§3.4, §3.5, §12-5, contractual; la
> pasada 2 la sustituyó por la pendiente de calibración); una
> tarjeta de esquema 3 no conserva el AUC de Holdout ni una referencia con huella, y qué hacer con
> ella es la decisión §12-2 (contractual); indicadores no evaluables y corridas sin desenlace tienen
> veredicto (§3.5); la varianza nula deja la prueba «no evaluable» (§3.4); la tarjeta se aplica por
> periodo, porque sus guardas rechazan una misma operación en dos periodos (§7); los cortes del PSI
> son los efectivos de `stability`, de cardinalidad variable (§3.7); y la ruta de `data` está fuera
> del `config_hash` desde la 1.4.0 —la corrección de este documento en su versión anterior estaba
> mal— (§5.3). Informe: `evidencia/s44/codex_sdd33_p1_raw.txt`; medición: `salidas/medir_h4_c.txt`.
>
> **Pasada 2** (un high y tres medium, los cuatro reales; uno contractual, elevado): con la
> composición fija, un **cambio puro de intercepto** —PD 10 %/50 % que pasan a 1,2 %/10 %, mismo
> orden en logit— también baja el AUC sobre tramos, y la prueba contra la composición no lo distingue
> (las dos pruebas rojas, p ≈ 10⁻⁸): recalibrar el intercepto lo arregla exacto. La segunda prueba
> pasa a ser la **pendiente de calibración** (Cox, 1958), que un intercepto o una mezcla dejan en 1 y
> un orden perdido baja (§3.4, §12-5, contractual; medida en siete casos). Además: la tarjeta recibe
> sólo sus predictores y llaves (una tarjeta estricta rechaza el periodo y el desenlace) (§7); un
> periodo sin desenlace se resuelve antes que «sin acción» (§3.5); y el PSI usa el suavizado real de
> `stability` —sólo las proporciones cero— (§3.2). Informe: `evidencia/s44/codex_sdd33_p2_raw.txt`;
> medición: `salidas/medir_h4_d.txt`.
>
> **Pasada 3, la última del tope declarado** (un high y dos medium, reales; el high, contractual,
> elevado): con la pendiente en 0,5 y el AUC de 0,738 a 0,633, una recalibración de pendiente
> (Platt, SDD-10) deja las PD exactas pero **no recupera la discriminación perdida**; si ese caso es
> «redesarrollar» o «recalibrar» lo decide Cami en §12-5, con el caso. Corregidos: la pendiente es
> «no evaluable» si los tramos con desenlace no tienen al menos dos PD distintas (PAVA puede igualar
> tramos) o su matriz de información no es invertible (§3.4); y los artefactos publican las dos colas
> con su dirección y la regla con que el veredicto las consolida (§6.2). Sin cuarta pasada, por el
> criterio declarado. Informe: `evidencia/s44/codex_sdd33_p3_raw.txt`.
>
> **Capa A implementada en S45 (2026-10-13)**, sin publicar: el dominio `monitoring`, la tarjeta de
> esquema 4, `bayesrisk.Monitor` (experimental), los resúmenes y la guía; el oráculo de §0.3
> reproducido con OptBinning real. Cami precisó la fila 3 de §3.5 (el ámbar de un tramo suelto no
> pide vigilar); lo demás que el código precisó, en §14.
>
> **No toca:** el pipeline del scorecard, `stability`, `validation`, `performance`, la escala
> maestra, IFRS 9, CMF ni el arnés H9R. Sin la sección nueva, ninguna corrida, artefacto, YAML ni
> `config_hash` cambia (D-ESC-7). **No autoriza** bump, tag, PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **SDD** | 33 |
| **Módulo** | `bayesrisk.monitoring` (dominio y corrida nuevos); toca `scorecard/bundle.py` (la referencia de Desarrollo, esquema 4), `core/config` (la sección), `guided/` (la puerta `bayesrisk.Monitor` y su resumen), `report`, `ui/jobs.py` + `web/` (capa B) y `docs_site/` |
| **Fase** | F1 (el scorecard, en operación) |
| **Tanda de producción** | T9 (SDD-31: un módulo a la vez, con su §13) |
| **Estado** | Aprobado por Cami el 2026-10-13 (§12) |
| **Depende de** | SDD-09 (la tarjeta), SDD-11 (`stability`: PSI, bandas y su suavizado), SDD-22 (`validation`: Jeffreys y el semáforo), SDD-31, SDD-32 (la escala maestra: tramos, PD por tramo y `tabla_por_tramo`) |
| **Lo consumen** | La guía del scorecard, un trabajo nuevo de la pantalla, el informe de monitoreo; H2b (comparar modelos), H9 (despliegue) |
| **Autor / Fecha** | Claude Code / 2026-10-12 |

---

## Recomendación ejecutiva

Un banco chico que ya usa su tarjeta necesita, cada periodo, tres respuestas y una acción: **¿cambió
la cartera?** (población), **¿el modelo sigue ordenando?** (discriminación) y **¿cada tramo sigue
acertando su PD?** (calibración); y, según eso, **sin acción, vigilar, recalibrar o redesarrollar**.
Hoy la librería no responde ninguna para un modelo en uso: `stability` calcula el PSI por periodo
dentro de la corrida de desarrollo y no lo publica, y nada mide la tasa de malos por tramo en el
tiempo ni compara el AUC con el de la validación inicial (§0).

Se propone una **corrida de monitoreo** que parte de la **tarjeta guardada** y de la cartera nueva
con su columna de periodo y, cuando existe, su desenlace:

```python
mon = bayesrisk.Monitor(bundle="tarjeta/", data="cartera.parquet", period="mes", default="malo")
mon.run()
```

Por cada periodo publica cuatro indicadores con su semáforo —el PSI del puntaje, el PSI de la
participación por tramo, la tasa de malos de cada tramo y de la cartera frente a su PD (Jeffreys) y
la discriminación —el AUC sobre los tramos contra el de la validación inicial (la prueba del BCE) y la
pendiente de calibración, que dice si los tramos separan lo que el modelo promete— y **un veredicto con su acción** por una tabla de
decisión (§3.5). Todo reutiliza el motor que ya existe (el PSI de `stability`, `tabla_por_tramo` de
la escala, Jeffreys y el semáforo de `validation`); lo único nuevo de cálculo son la prueba de AUC del
BCE y la pendiente. Medido (§0.3): con la cartera estable el veredicto es «sin
acción»; cuando la población se mueve y el modelo aguanta, «vigilar»; cuando el nivel se desvía,
«recalibrar», justo en el periodo en que ocurre —y **el PSI solo no lo habría visto** (0,007)—.

Las diez decisiones de §12 llevan una recomendación cada una; las de fondo son **qué AUC es el
inicial** (§12-3: el de Holdout, porque el de Desarrollo es optimista y dispara falsas alarmas,
medido), **qué tarjetas se monitorean** (§12-2: sólo las guardadas desde la versión que trae el
monitoreo, que congelan su referencia) y **la tabla de decisión** (§12-5: la población sola nunca pide
redesarrollar; un tramo rojo aislado sólo pide vigilar, porque con 5 tramos y 6 periodos a α = 0,01 un
rojo por azar tiene ≈ 26 % de probabilidad; y redesarrollar exige que el AUC caiga contra la
validación inicial **y** que la pendiente de calibración quede bajo 1, porque el AUC sobre tramos
también cae sólo por composición o por un cambio de intercepto, que recalibrar arregla).

---

## 0. El estado, medido

### 0.1 Lo que hay hoy (sobre `100879a`)

Censo del código con un subagente de lectura (S44), cada afirmación con su archivo y línea en la
evidencia:

- **PSI por periodo, escondido.** `stability` agrupa por la columna de periodo o cohorte y calcula
  el PSI del puntaje de cada periodo contra Desarrollo, con su media de PD (`stability/evaluator.py`,
  `temporal_records`); **sólo el peor periodo** llega a `stability_metrics`, y la serie vive dentro
  de `("stability", "result")` sin que el informe, la pantalla ni los resúmenes la lean. La ayuda de
  `stability.temporal_axis` en la pantalla dice que «el informe muestra la evolución período a
  período»: **hoy no es cierto**.
- **La escala por muestra, reutilizable por periodo.** `master_scale.engine.tabla_por_tramo` recibe
  un frame con `grade` y `target` por clave y devuelve, por tramo, `n`, malos, tasa, PD, el p-valor
  de Jeffreys y el semáforo: sirve tal cual con periodos como claves.
- **Jeffreys y el semáforo** viven en `validation/calibration_tests.py` (`binomial_by_grade`,
  `traffic_light`), con los cortes 0,05/0,01 como política institucional publicada (D-VAL-15).
- **La tarjeta** (`FittedScorecardBundle`, esquema 3) puntúa solicitudes nuevas con `grade`,
  `grade_pd` y `decision` (D-ESC-6), pero **no congela ninguna referencia de Desarrollo**: ni la
  distribución del puntaje, ni la participación por tramo, ni el AUC. Las reglas de cada variable sí
  traen el conteo de Desarrollo por bin (`support`).
- **Ninguna prueba de AUC** frente a un AUC de referencia: no existe la varianza de Mann-Whitney en
  el motor.
- **Ningún trabajo de la pantalla ni puerta guiada** de monitoreo; `validar_modelo` corre
  `performance` y `stability` sobre las particiones fijas de una corrida.
- **Las carteras del paquete** traen la cohorte como texto (seis trimestres; ninguna con fecha real).
  `consumo_drift` desplaza las variables con la cohorte pero conserva la misma logística: hay deriva
  de **población**, no de **calibración**. Ninguna ejercita un tramo cuya tasa se aleje de su PD.

### 0.2 Lo que necesita un banco chico

El modelador que ya puso en uso su tarjeta tiene, cada mes o trimestre, la cartera puntuada y, para
las cohortes maduras, el desenlace. Necesita: (1) un tablero por periodo que diga si la población
sigue siendo la del desarrollo; (2) si el modelo sigue ordenando como cuando se validó; (3) si cada
tramo sigue acertando su PD; (4) **una acción** —no cinco números sueltos— y el porqué; (5) un
informe que pueda llevar al comité y un Excel; y (6) que todo esto no exija volver a correr el
desarrollo ni conservar sus datos.

### 0.3 Medido con las reglas de este documento

La tarjeta del preset F1 con su escala maestra (5 tramos, PD 4,77 · 13,96 · 24,89 · 36,85 · 53,52 %),
aplicada por cohorte; PSI contra Desarrollo (deciles de Desarrollo, el suavizado de `stability`);
Jeffreys por tramo y de cartera con el semáforo 0,05/0,01; AUC sobre los tramos con la prueba del
BCE (§3.4). Calcular todos los indicadores de seis periodos toma **0,03 s**; la corrida completa del
desarrollo, 7–9 s.

| Caso | Cohorte | PSI puntaje | Malos vs PD (cartera) | Tramos rojos | AUC tramos (p contra Holdout) | Veredicto |
|---|---|---|---|---|---|---|
| Misma cartera, sin deriva | 2023Q1–2024Q1 | 0,003–0,011 | 22,0–25,3 % vs 23,1–23,7 % | — | 0,689–0,713 (≥ 0,65) | sin acción |
| | 2024Q2 (OOT) | 0,007 | 23,7 % vs 23,0 % | 1 | 0,655 (0,092) | vigilar |
| Tarjeta de `consumo_comportamiento` en `consumo_drift` | 2023Q1 | 0,009 | 22,9 % vs 22,5 % | 1 | 0,683 (0,54) | vigilar |
| | 2023Q3–2024Q1 | 0,51–1,59 (rojo) | en línea | — | 0,662–0,673 (≥ 0,12) | vigilar |
| | 2024Q2 | 2,04 (rojo) | **48,5 % vs 43,7 % (rojo)** | 5 | 0,664 (0,12) | **recalibrar** |
| Deriva de calibración (construida) | 2023Q1–2024Q1 | ≤ 0,011 | en línea | — | ≥ 0,65 | sin acción |
| | 2024Q2 | **0,007** | **34,3 % vs 23,0 % (rojo)** | 1, 3, 4, 5 | 0,740 (1,00) | **recalibrar** |
| `consumo_drift` con su propia tarjeta (7 tramos) | las seis | 0,02–0,75 (rojo en 2023Q1, 2024Q1 y 2024Q2) | en línea | — | 0,699–0,720 (≥ 0,89) | vigilar (sin acción en 2023Q3) |
| Discriminación rota (los tramos de la OOT barajados) | 2024Q2 | 0,007 | 23,7 % vs 23,0 % | — | **0,473** (BCE rojo; pendiente −0,12, roja) | **redesarrollar** |
| Composición (contraejemplo de la pasada 1, sintético) | t | — | PD 1 % y 10 % exactas | — | 0,716 → 0,525 (BCE rojo; pendiente 1,00, verde) | vigilar |
| Intercepto (contraejemplo de la pasada 2, sintético) | t | — | 30 % esperado, 5,6 % observado: PD sobrestimada (verde en el contraste del BCE, rojo en su espejo) | 1, 2 (en el espejo) | 0,738 → 0,707 (BCE rojo; pendiente 1,00, verde) | **recalibrar** con §12-10 (a); vigilar con (b) |

El contraejemplo de calibración pasa a malo, en la cohorte OOT, un tercio de los buenos de los
tramos 3 a 5 (semilla fija): la población no cambia y **sólo la tasa de malos por tramo lo detecta**.
El caso «tarjeta de una cartera monitoreada en otra que se deteriora» es el uso real: mientras la
cartera se mueve y el modelo aguanta, el veredicto es vigilar; cuando el nivel se desvía, recalibrar.

### 0.4 Cuatro hallazgos de la medición

1. **El AUC de Desarrollo es un mal inicial.** Sobre los tramos, Desarrollo da 0,709 y Holdout
   0,682 en `consumo_comportamiento` (0,738 y 0,679 en `consumo_drift`): la muestra de ajuste es
   optimista. Contra Desarrollo, la OOT sale **roja** en las dos carteras (p = 0,004 y 0,008); contra
   Holdout, **verde** (p = 0,09 y 0,92). Con Desarrollo como inicial, el monitoreo pediría
   redesarrollar un modelo sano (§12-3).
2. **El PSI y la calibración miden cosas distintas.** En `consumo_drift` el PSI llega a 0,75 con
   todos los tramos verdes (la población cambia y el modelo la sigue); en la deriva construida el PSI
   es 0,007 con cuatro tramos rojos. Una regla que mapee PSI rojo a «redesarrollar» —como el mapa
   banda → acción de `stability`— pediría redesarrollar en el primer caso y nada en el segundo
   (§12-5).
3. **El AUC cae también por composición** (contraejemplo de la pasada 1 de Codex, reproducido): dos
   tramos con PD 1 % y 10 %, ambos exactos; con 10.000 operaciones cada uno el AUC es 0,716, y con
   1.000 y 19.000 —las mismas PD— es 0,525 (`S` del BCE = 162). Con la prueba del BCE sola, un
   cambio de mezcla pediría redesarrollar un modelo que ordena y acierta. El **AUC que el modelo
   espera para la composición del periodo** (§3.4) da exactamente 0,525 (p′ = 0,50); con los tramos
   de la OOT barajados —el modelo dejó de ordenar— da 0,713 contra 0,473 (rojo). Ese contraste solo,
   en cambio, marca rojo la OOT de la cartera estable (0,712 esperado contra 0,655), porque las PD
   heredan el optimismo de Desarrollo (`salidas/medir_h4_c.txt`). Y no distingue un **cambio de
   intercepto** (pasada 2): con la composición fija, PD 10 %/50 % que pasan a 1,2 %/10 % —el mismo
   orden en logit— bajan el AUC de 0,738 a 0,707 y las dos pruebas salen rojas. La **pendiente de
   calibración** (§3.4) vale exactamente 1 en los dos contraejemplos sintéticos, −0,12 con los
   tramos barajados y entre 0,82 y 1,25 en las carteras del paquete; sola, marca rojo la OOT de la
   cartera estable (0,68, p = 0,0004), que la prueba del BCE contra Holdout ve verde: por eso §3.5
   exige las dos (`salidas/medir_h4_d.txt`).
4. **Un tramo rojo aislado no es señal.** Con K = 5 tramos y 6 periodos hay 30 contrastes; a
   α = 0,01 la probabilidad de al menos un rojo por azar es 1 − 0,99³⁰ ≈ 26 %. En la cartera estable
   aparece uno (tramo 1 en 2024Q2) y en la tarjeta trasladada otro (tramo 1 en 2023Q1). La tabla de
   §3.5 los lleva a «vigilar», no a «recalibrar».

---

## 1. Propósito y responsabilidad

**Qué resuelve:** dada una tarjeta en uso y su cartera nueva por periodo, decir por periodo si
cambió la población, si el modelo sigue ordenando y si cada tramo acierta su PD, con un veredicto y
su acción, en el notebook, la pantalla, el informe y el Excel.

**Hace:** aplicar la tarjeta a la cartera nueva; medir por periodo los cuatro indicadores de §3
contra la referencia de Desarrollo que congela la tarjeta; emitir el semáforo de cada uno, el
veredicto y la acción; publicar las tablas por periodo y por tramo × periodo; registrar en el trail
la referencia usada y cada alerta.

**No hace:** reajustar, recalibrar ni redesarrollar el modelo (sólo lee; IHN-004 e IHN-011); pronosticar
la cartera (`portfolio_forecast`, IHN-002); validar IFRS 9 (`validation.backtesting`); migraciones
de clientes entre periodos (la herramienta del BCE exige el mismo cliente en dos fechas; §12-4);
guardar historia entre corridas (cada corrida recalcula la serie entera; §12-7).

## 2. Contexto y ubicación en la arquitectura

Una corrida de monitoreo es un `Study` con tres secciones: `data` (la cartera nueva, **sin target ni
partición**, como una corrida de cartera de IFRS 9), `monitoring` (la tarjeta, la columna de periodo
y la de desenlace) y `report`. El paso `monitoring` requiere `("data", "frame")`, carga la tarjeta,
la aplica con `bundle.apply` y publica `("monitoring", clave)`. No corre ninguna etapa del
scorecard. La puerta guiada `bayesrisk.Monitor` construye ese config y lee sus artefactos, como
`bayesrisk.Ecl` (SDD-31 §12.2-5: un cliente de `bayesrisk.run`, nunca un segundo orquestador).

```
tarjeta (esquema 4: el modelo, la escala y la referencia de Desarrollo)
        │
cartera nueva ──► data ──► monitoring ──► report
 (periodo, desenlace)        │ apply → puntaje, tramo, PD del tramo
                             │ por periodo: población · calibración · discriminación → veredicto
```

## 3. Conceptos y fundamentos

### 3.1 Notación

Periodo `t`; operaciones del periodo `i ∈ t` con puntaje `sᵢ`, tramo `gᵢ ∈ {1…K}` (1 = menor
riesgo) y PD del tramo `p_g`; desenlace `yᵢ ∈ {0, 1}` o vacío (sin madurar). Referencia de
Desarrollo congelada en la tarjeta (§3.7): los cortes del puntaje en deciles `q₀ < … < q₁₀` con
participación `r_b`, la participación por tramo `r_g` y el AUC inicial `AUC₀` con su varianza.

### 3.2 Población (sin desenlace)

- **PSI del puntaje** del periodo contra Desarrollo, con los cortes efectivos de §3.7 y **el mismo
  cálculo de `stability`** (`_psi_from_counts`): `PSI = Σ_b (a_b − r_b) · ln(a_b / r_b)`, donde sólo
  una proporción **cero** se reemplaza por 10⁻⁶ (una positiva, aunque menor, se usa tal cual; con
  referencia [100, 9.900] y periodo [1, 2.999.999] da 0,103, «revisar», y no 0,092). Bandas de `stability`:
  < 0,10 estable, < 0,25 revisar, ≥ 0,25 rojo. Medido igual al `temporal_records` de `stability`
  en las seis cohortes de las dos carteras (§0.3).
- **PSI de la participación por tramo**: la misma fórmula sobre los K tramos. Es la lectura que el
  comité entiende («el tramo 5 pasó de 9 % a 21 % de la cartera»).
- **CSI por variable**, como diagnóstico sin veredicto: la participación de cada bin de la tarjeta
  en el periodo contra el `support` de Desarrollo que la tarjeta ya trae.

### 3.3 Calibración (con desenlace)

- **Por tramo:** `tabla_por_tramo` de la escala maestra, sin cambios —tasa de malos del tramo
  frente a `p_g`, Jeffreys unilateral `B(p_g; d + ½, n − d + ½)` (BCE 2019 §2.5.3, cotejado en
  SDD-22), semáforo 0,05/0,01 y mínimo de 30 operaciones con desenlace por tramo—.
- **De cartera:** el mismo contraste sobre **las mismas filas**: las puntuadas del periodo con
  desenlace conocido (máscara `M_t`). `n`, malos, la tasa observada y la PD esperada
  `p̄ = mean_{i ∈ M_t}(p_{gᵢ})` salen todos de `M_t` (el BCE pide «el número de grados más uno»: el uno
  es la cartera). La PD media de todas las puntuadas del periodo —con y sin desenlace— se publica
  aparte, como descripción, y no entra al contraste: mezclarla con los malos de `M_t` da p ≈ 10⁻²¹
  donde el contraste correcto da 0,50 (contraejemplo de la pasada 1 de Codex).
- **Las dos colas (§12-10).** El contraste del BCE es unilateral: sólo marca una PD **demasiado
  baja** (riesgo subestimado). Una PD **demasiado alta** —el caso de intercepto de la pasada 2: 30 %
  esperado y 5,6 % observado— sale verde, aunque niega crédito a quien podía pagar. Con §12-10 (a) se
  agrega su espejo, `1 − B(p_g; d + ½, n − d + ½)`, con los mismos cortes, por tramo y de cartera, y
  un rojo del espejo cuenta como rojo de calibración en §3.5. Medido: en las tres carteras del
  paquete el espejo no enciende ningún rojo (los veredictos de §0.3 no cambian); en el caso de
  intercepto, p ≈ 0 en la cartera y en los dos tramos (`salidas/espejo_sobrestimacion.txt`).

### 3.4 Discriminación: dos pruebas sobre el AUC

**El AUC del periodo** se calcula, como pide el BCE (§2.5.4), **sobre los tramos de la escala** (la
misma escala que la calibración) por la U de Mann-Whitney con empates en ½ (anexo 3.1), sobre `M_t`.
Su desviación estándar es la del anexo: `s_t² = var̂(V₁₀)/|A| + var̂(V₀₁)/|B|` (varianzas insesgadas
de las contribuciones de malos y buenos).

1. **Contra la validación inicial (la prueba del BCE, §2.5.4.1):** `S = (AUC₀ − AUC_t) / s_t`,
   p-valor `1 − Φ(S)`. `AUC₀` es el de **Holdout** sobre los tramos y, si la corrida de desarrollo no
   tuvo Holdout, el de Desarrollo, declarado (§12-3).
2. **La pendiente de calibración** (Cox, 1958): la regresión logística del desenlace sobre el logit
   de la PD de su tramo, con intercepto, sobre `M_t`: `logit P(y = 1) = a + b·logit(p_g)`. `b = 1`
   cuando los tramos separan lo que el modelo promete —un cambio de composición o de intercepto no la
   mueven: los dos contraejemplos dan 1,00 exacto—; `b < 1` cuando separan menos (orden perdido o
   comprimido). Contraste unilateral `z = (b − 1)/se(b)`, p-valor `Φ(z)`.

Un p-valor chico rechaza, en la prueba 1, que el AUC no haya caído y, en la 2, que la pendiente no
sea menor que 1. **No evaluable** —nunca verde (IHN-010)— con
menos de 2 malos o de 2 buenos en `M_t` (la plantilla del BCE no calcula con menos de 2
incumplimientos), o si `s_t²` no es finito y positivo (por ejemplo, todas las operaciones con
desenlace en un solo tramo: todas las contribuciones valen ½ y la varianza es cero); la pendiente,
además, si los tramos con desenlace no tienen **al menos dos PD distintas** (la igualación de PAVA
en la escala puede dar a dos tramos la misma PD: el logit es constante y la pendiente no se
identifica), si la matriz de información no es invertible, si el error estándar no es finito y
positivo o si el ajuste no converge (separación perfecta), con su causa; los demás indicadores se
calculan igual.
Semáforo con los cortes 0,05/0,01 (política institucional, como el de Jeffreys: el BCE no los fija).
**La discriminación es roja sólo si las dos pruebas son rojas** (§3.5, §12-5); cada una se publica
con su p-valor, y el informe dice cuál de las dos falló.

### 3.5 Veredicto y acción por periodo (§12-5)

| Orden | Condición | Veredicto | Por qué |
|---|---|---|---|
| 1 | Discriminación roja: las dos pruebas de §3.4 rojas | **Redesarrollar** | Los tramos separan menos de lo que el modelo promete y el AUC cayó contra la validación inicial: recalibrar el nivel no lo arregla |
| 2 | Cartera roja, o ≥ 2 tramos rojos, o el mismo tramo rojo dos periodos seguidos | **Recalibrar** | El orden sigue, el nivel no |
| 3 | Población roja, o cualquier ámbar, o un tramo rojo aislado, o una sola de las dos pruebas de discriminación roja | **Vigilar** | Cambió algo que todavía no es una falla del modelo |
| 4 | Todo lo evaluable verde, con `M_t` no vacía | **Sin acción** | |

**Antes de las filas**, un periodo sin desenlace (`M_t` vacía) se resuelve aparte: con la población
roja o ámbar, **vigilar**; si no, **sin desenlace aún** —nunca «sin acción»: su desempeño no se pudo
medir—. Las filas 1–4 se leen en orden y gana la primera que se cumple. **Un indicador no evaluable no cuenta como
verde ni como rojo**: el veredicto se calcula con los evaluables y lleva «evidencia parcial» con la
lista de lo que no se pudo evaluar y por qué (pocos malos, un solo tramo con desenlace); sin la
discriminación evaluable, la fila 1 no puede cumplirse y el resumen lo dice. «Dos periodos seguidos»
mira el periodo anterior **presente** en el orden de la columna.

El **veredicto de la corrida** es el del último periodo; si ese periodo no tiene desenlace, se informa
además el del último periodo que sí lo tiene. Una corrida sin columna de desenlace sólo mide población
(«sin desenlace aún» o «vigilar»). La tabla es una **constante del motor**, no una perilla (§13): es
el criterio que el informe explica.

### 3.6 Lo que dice la norma (cotejado contra dos fuentes oficiales)

- **BCE, *Instructions for reporting the validation results of internal models* (febrero 2019)**,
  PDF oficial, sha256 `f0bef87b…` (el mismo cotejado en S13): §2.5.4 (AUC sobre los grados de la
  escala), §2.5.4.1 (la prueba `S` y `1 − Φ(S)`), anexo 3.1 (la U de Mann-Whitney y la varianza).
- **BCE, plantillas oficiales de reporte** (ZIP sha256 `68a86250…`), libro PD, hoja 4.0: `G10 =
  (AUC_init − AUC_curr)/√s²`, `H10 = 1 − NORM.DIST(G10)`, el AUC desde la tabla por grado de la hoja
  3.0 y «no calculable con menos de 2 incumplimientos». **Coinciden** en forma, orientación y
  distribución.
- Ni el BCE ni Basilea fijan cortes sobre los p-valores ni definen el PSI: sus bandas (0,10/0,25)
  son la convención de la industria que `stability` ya usa, y los cortes 0,05/0,01 son política
  institucional publicada (D-VAL-15). El informe lo dice.
- **La pendiente de calibración:** Cox, D. R. (1958), *Two further applications of a model for binary
  regression*, Biometrika 45(3/4): 562–565. Es una referencia académica estándar; su texto (de pago) no
  se cotejó en línea, como Hosmer-Lemeshow en SDD-22. El contraste unilateral sobre `b` es una
  elección del motor, declarada.
- La «estabilidad» del BCE (§2.5.5) son migraciones de clientes y concentración en grados; la
  concentración (HHI) ya la publica la escala maestra; las migraciones quedan fuera (§12-4).

### 3.7 La referencia que congela la tarjeta (esquema 4)

Al guardar una tarjeta con escala, el bundle agrega un bloque `monitoring_reference`, sólo con
agregados (la tarjeta sigue sin guardar una fila de los datos):

- los **cortes efectivos** del PSI del puntaje con las reglas de `stability` —cuantiles de
  Desarrollo, cortes interiores únicos (un puntaje discreto da menos de diez bins), colas abiertas y
  la misma regla de igualdad— y la participación de Desarrollo en cada bin;
- la participación de Desarrollo por tramo;
- el AUC inicial sobre los tramos con su `source` (`holdout` o, sin Holdout, `desarrollo`), su
  varianza y sus conteos;
- el `n` de Desarrollo.

Sólo las tarjetas de esquema 4 se monitorean (§12-2): una de esquema 3 (la 2.11 y la 2.12) no
conserva el AUC de Holdout y no hay cómo recuperarlo de una muestra sin partición.

## 4. API pública (contrato)

### 4.1 La puerta guiada

```python
mon = bayesrisk.Monitor(
    bundle="tarjeta/",          # la tarjeta guardada (esquema 4: desde la versión con monitoreo)
    data="cartera.parquet",     # la cartera nueva: las variables del modelo, el periodo y el desenlace
    period="mes",               # columna de periodo (texto, fecha o número; una fecha se agrupa por mes)
    default="malo",             # columna de desenlace 0/1; vacía = aún sin madurar; opcional
)
mon.run()                       # una línea; los resúmenes hablan por etapa
mon.summary()                   # veredicto, acción y los cuatro indicadores del último periodo
mon.export_excel("monitoreo/")  # «Monitoreo.xlsx»
```

`Monitor` comparte la maquinaria de `guided/_puerta.py` (`run`, `resume`, `summary`, `export`) y no
tiene decisiones humanas: no hay nada que decidir sobre un modelo que sólo se mide.

### 4.2 La puerta completa

El YAML lleva `data` (sin target ni partición), `monitoring` y `report`; `bayesrisk.run` lo corre.
Mismo `config_hash` y mismos artefactos que la puerta guiada (D-SIM-1).

### 4.3 La pantalla (capa B)

Un trabajo nuevo, «Monitorear un modelo en uso», con las secciones `data`, `monitoring` y `report`.
La tarjeta llega de una corrida del scorecard hecha en la misma pantalla o se sube como `.zip` (el
bundle es una carpeta). Resultados muestra el veredicto, la serie por periodo y la tabla tramo ×
periodo.

## 5. Configuración

### 5.1 La sección `monitoring` (`MonitoringConfig`)

| Campo | Tipo | Default | Esencial | Qué es |
|---|---|---|---|---|
| `bundle` | ruta | — (obligatorio) | sí | La tarjeta a monitorear |
| `period` | columna | — (obligatorio) | sí | El periodo de cada operación |
| `default` | columna \| `None` | `None` | sí | El desenlace 0/1; sin él, sólo población |

### 5.2 Lo que NO se configura

Las bandas del PSI (0,10/0,25, las de `stability`), los cortes del semáforo (0,05/0,01, los de
`validation` y la escala), los deciles, el suavizado, el mínimo por tramo (30, el de la escala), el
mínimo de malos del AUC (2, el del BCE), la tabla de decisión y el AUC inicial (de la tarjeta). Son
constantes con su fuente en el informe (§12-6 mide por qué ninguna falla en las carteras medidas).

### 5.3 Identidad

`monitoring` es una sección nacida después de la 2.10.0: entra a
`SECCIONES_NACIDAS_DESPUES_DE_2_10_0` y se serializa sólo si está declarada (D-ESC-7). Las rutas
quedan fuera del `config_hash` y el contenido se identifica por su huella: `data.load.source` ya está
excluida desde la 1.4.0 (`core/config/hashing.py::_hash_exclude`, con su test en `test_ui_presets.py`)
y la cartera la identifica `data_hash`; `monitoring.bundle` se excluye igual —como las rutas de las
tablas de escenarios (S40)— y la tarjeta la identifica su `bundle_hash`, en el lineage y en la ficha
del informe. Mover un archivo no cambia el `config_hash`; cambiar su contenido cambia su huella. Ningún
campo nuevo entra a `stability`, `validation` ni `eda` (D-ESC-7 no cubre campos dentro de una sección
existente: movería el `config_hash` del preset F1).

## 6. Contratos de datos

### 6.1 Entrada

La cartera trae las columnas que la tarjeta necesita (las mismas que `bundle.apply`), la de periodo
y, opcional, la de desenlace (0, 1 o vacío). Filas no puntuables (`scoring_status` ≠ `"scored"`) se
cuentan y se excluyen de los indicadores, con su motivo.

### 6.2 Salida (`("monitoring", clave)`)

- `periods`: una fila por periodo —`n`, puntuadas, con desenlace, malos, PSI del puntaje y de
  tramos con su banda, la PD media de las puntuadas (descriptiva), la tasa de malos y la PD esperada
  sobre `M_t` con los p-valores y semáforos de las dos colas, su dirección y el consolidado, el AUC del periodo con su `s_t`, `AUC₀`, `S`, su p-valor y
  semáforo, la pendiente `b` con su error, p-valor y semáforo, tramos rojos, lo no evaluable con su causa y el veredicto—.
- `grades_by_period`: tramo × periodo, la salida de `tabla_por_tramo` (sin cambiarla), más la
  participación del tramo y la de Desarrollo y, con §12-10 (a), el p-valor y el semáforo del espejo
  (PD demasiado alta) junto a los del contraste del BCE (PD demasiado baja), con la **dirección** de
  cada rojo («subestima» o «sobrestima») y el semáforo consolidado que usa el veredicto (el peor de
  las dos colas).
- `variables_by_period`: el CSI de cada variable por periodo.
- `verdict`: el veredicto de la corrida con su periodo, su acción y la razón en una línea.
- `card`: la referencia usada (`source` de `AUC₀`, `bundle_hash`), las constantes y las alertas.

### 6.3 Invariantes

Los conteos cuadran por periodo (puntuadas + no puntuables = n); un indicador sin datos suficientes
es «no evaluable», nunca verde (IHN-010); la corrida no escribe en la tarjeta ni en ninguna corrida
anterior (IHN-011).

### 6.4 Excel y numeración

`Monitoreo.xlsx` con un libro único (resumen, periodos, tramos × periodo, variables): la corrida de
monitoreo no tiene etapas previas que numerar.

## 7. Algoritmo

1. Cargar la tarjeta y su `monitoring_reference`; una tarjeta sin ella (esquema ≤ 3) o sin escala
   falla con un mensaje que dice cómo obtener una que sí (§8).
2. Agrupar la cartera por periodo (una fecha se agrupa por mes, con su rótulo `AAAA-MM`).
3. **Aplicar la tarjeta por periodo**, con sus guardas intactas: `bundle.apply` recibe **sólo los
   predictores y las llaves** de la tarjeta (una tarjeta estricta, `extra_columns="forbid"`, rechaza
   el periodo y el desenlace), que se guardan aparte para realinear el resultado con la fila original: las llaves únicas de la tarjeta son
   únicas **dentro** de un periodo, y una misma operación puede estar en enero y en febrero (una
   cartera de comportamiento); aplicada sobre todo el frame, `_validate_apply_frame` la rechazaría.
   Una llave repetida dentro de un mismo periodo sigue fallando, con el mensaje de la tarjeta.
4. Por periodo: PSI del puntaje y de tramos; si hay desenlace, sobre `M_t`, `tabla_por_tramo`, el
   contraste de cartera, la prueba de AUC del BCE y la pendiente.
5. Veredicto por periodo con la tabla de §3.5 (la regla «dos periodos seguidos» mira el periodo
   anterior en el orden de la columna).
6. Publicar artefactos, resumen, alertas al trail y el informe.

## 8. Casos borde

Un periodo sin desenlace (sólo población, «sin desenlace aún»); un tramo vacío en un periodo
(participación 0, PSI suavizado, contraste «no evaluable»); un periodo sin malos o con uno solo (AUC
«no evaluable», evidencia parcial); todas las operaciones con desenlace en un solo tramo (varianza
nula: AUC «no evaluable»); una tarjeta sin escala maestra o de esquema ≤ 3 (falla con mensaje: el
monitoreo mide por tramo contra la referencia que congela la tarjeta; se vuelve a correr el
desarrollo con la versión que trae el monitoreo —mismo config, mismo `config_hash`, mismo modelo— y
se guarda la tarjeta); columnas faltantes (la falla de
`bundle.apply`, sin reinterpretar); un solo periodo (sin la regla de periodos seguidos); fechas con
meses faltantes (el periodo faltante no aparece, y la regla de periodos seguidos mira el anterior
presente, declarado).

## 9. Reproducibilidad y auditoría

Sin componentes estocásticos. El lineage lleva `bundle_hash`, `data_hash` y `config_hash`; el trail,
una `decision` por alerta roja (`accion="alertar"`, con indicador, periodo y valor) y el veredicto.
Cada corrida es inmutable: monitorear más periodos es una corrida nueva sobre la cartera con todos
los periodos (IHN-011).

## 10. Dependencias

Internas: `scorecard.bundle`, `stability` (el PSI y su suavizado), `master_scale.engine`
(`tabla_por_tramo`), `validation.calibration_tests` (`traffic_light`). Externas: `numpy`, `pandas`
y `scipy` (ya dependencias del núcleo). Ninguna nueva.

## 11. Estrategia de tests

- **Oráculos de §0.3**: las cifras de las cuatro filas medidas, con OptBinning real en subproceso
  como el oráculo de la escala (S42).
- **La prueba del BCE contra su plantilla**: un caso chico (dos periodos, tres tramos) calculado a mano
  con las fórmulas del anexo 3.1 y con la hoja 4.0 de la plantilla.
- **Un caso por fila de la tabla de §3.5**, con los contraejemplos medidos: la discriminación rota
  (los tramos de un periodo barajados) da «redesarrollar»; el cambio de composición con tramos
  calibrados (el de la pasada 1 de Codex) no lo da; la máscara de desenlace (filas inmaduras con
  otra PD) no altera el contraste de cartera; un periodo con todas las operaciones con desenlace en
  un solo tramo deja el AUC «no evaluable» por varianza nula; un periodo con un malo, «evidencia
  parcial».
- **Los contraejemplos de las pasadas 1, 2 y 3**: el de composición y el de intercepto dan pendiente
  1 y no dan «redesarrollar» (el de intercepto da «recalibrar» con §12-10 (a)); el de pendiente 0,5
  (10.000 por tramo, PD 10 %/50 %, malos de 1.000/5.000 a 2.500/5.000) da lo que Cami decida en §12-5.
- **Pendiente no identificable**: dos tramos con la misma PD (30 %, 1.000 operaciones y 300 malos
  cada uno) dejan la pendiente «no evaluable» con su causa y el AUC evaluable.
- **Tarjeta estricta**: una tarjeta con `extra_columns="forbid"` se monitorea con el periodo y el
  desenlace en la cartera.
- **El PSI**: equivalencia con `stability` con proporciones positivas menores que 10⁻⁶ (referencia
  [100, 9.900], periodo [1, 2.999.999]: 0,103187).
- **Sin desenlace**: un periodo con `M_t` vacía y la población en cada color da «sin desenlace aún»,
  «vigilar» y «vigilar».
- **Panel**: una cartera con la misma operación en dos periodos se monitorea; una llave repetida
  dentro de un periodo falla con el mensaje de la tarjeta.
- **Cortes efectivos**: una tarjeta con puntaje discreto (dos valores) guarda menos de diez bins y
  su PSI coincide con el de `stability` sobre los mismos datos.
- **Identidad**: sin la sección, el `config_hash` y el YAML de los cuatro presets iguales a la
  2.12.0 (el gate de D-ESC-7).
- **Tarjeta**: una de esquema 3 guardada con la 2.12.0 se sigue leyendo y aplicando igual, y el
  monitoreo la rechaza con el mensaje de §8; una de esquema 4 se guarda y se relee; `apply` no cambia.
- **Identidad de las rutas**: mover la cartera o la tarjeta de carpeta no cambia el `config_hash`.
- **Tres puertas** (capa B): guiada, YAML y pantalla con el mismo `config_hash` y los mismos
  artefactos.

## 12. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 12-1 | Dónde vive el monitoreo | (a) **una corrida propia** que parte de la tarjeta guardada (`bayesrisk.Monitor`, sección `monitoring`, trabajo nuevo de la pantalla); (b) extender `stability` y `validation` dentro de la corrida del scorecard | **(a)**: el banco monitorea un modelo en uso sin volver a correr el desarrollo ni guardar sus datos; (b) movería el `config_hash` del preset F1 (campos nuevos dentro de secciones existentes) y sólo serviría a quien conserva el estudio |
| 12-2 | Qué tarjetas se monitorean (elevada por la pasada 1) | (a) **sólo las de esquema 4**, que congelan su referencia al guardarse (desde la versión que trae el monitoreo); una de la 2.11 o la 2.12 se vuelve a guardar re-corriendo su desarrollo con esa versión (mismo config, mismo `config_hash`, mismo modelo); (b) también las de esquema 3, con una muestra de desarrollo que traiga su columna de partición (Desarrollo para la población, Holdout para el AUC inicial), con su propia huella en el lineage y en la ficha | **(a)**: una tarjeta de esquema 3 no conserva el AUC de Holdout y una muestra externa cambia los resultados sin cambiar ninguna huella declarada (pasada 1: el PSI de una misma cartera pasa de 0 a 0,879 con otra referencia); las tarjetas con escala existen sólo desde la 2.11.0 (2026-10-12); y (a) deja la sección con tres campos en vez de cuatro |
| 12-3 | El AUC inicial | (a) **el de Holdout sobre los tramos** —la validación inicial, fuera de la muestra de ajuste—; sin Holdout, el de Desarrollo, declarado; (b) el de Desarrollo siempre | **(a)**: medido, Desarrollo es optimista (0,709 vs 0,682) y con él la OOT de las dos carteras sale roja (p = 0,004 y 0,008) cuando contra Holdout es verde (0,09 y 0,92) (§0.4-1) |
| 12-4 | Qué se mide | (a) **los cuatro indicadores** de §3 y el CSI como diagnóstico; (b) más las migraciones de clientes del BCE | **(a)**: las migraciones exigen el mismo cliente en dos fechas (un panel), que una cartera de originación no tiene; quedan para cuando un caso real lo pida |
| 12-5 | La tabla de decisión (ampliada por las pasadas 1, 2 y 3) | (a) **la de §3.5**: redesarrollar cuando la discriminación cayó —el AUC contra la validación inicial (BCE) **y** la pendiente de calibración bajo 1, las dos rojas—, aunque una recalibración de pendiente pueda devolver las PD (no devuelve la discriminación: con la pendiente en 0,5 el AUC pasa de 0,738 a 0,633 y queda ahí, contraejemplo de la pasada 3); recalibrar con la cartera roja, ≥ 2 tramos rojos o el mismo tramo dos periodos; vigilar con la población roja o ámbar, un tramo aislado o una sola prueba de discriminación roja; un periodo sin desenlace nunca es «sin acción»; lo no evaluable no cuenta como verde; (b) como (a), pero con la pendiente positiva y los tramos todavía ordenados el veredicto es «recalibrar» (Platt, SDD-10), y redesarrollar sólo si el orden de los tramos se invierte; (c) la prueba del BCE sola para redesarrollar; (d) el mapa banda → acción de `stability`; (e) sólo semáforos | **(a)**: medido en siete casos (§0.3, §0.4), acierta en todos; la prueba del BCE existe para vigilar el poder de discriminación, y un modelo que separa la mitad de lo que separaba aprueba más malos con el mismo corte aunque sus PD vuelvan a cuadrar; (b) mantiene en uso un modelo con AUC 0,633 sin pedir revisarlo; (c) pide redesarrollar con un cambio de mezcla o de intercepto; (d) pediría redesarrollar con el PSI en 0,75 y el modelo sano; (e) deja al modelador sin la respuesta que vino a buscar |
| 12-6 | Umbrales | (a) **constantes**: PSI 0,10/0,25 y p-valores 0,05/0,01, los que la librería ya usa, nombrados en el informe como política; (b) configurables en la sección | **(a)**: SDD-31 (perillas nacen en cero); en las cuatro carteras medidas ninguno produce un veredicto que no se explique; una institución con otra política es un caso real que se mide cuando llegue |
| 12-7 | Historia entre corridas | (a) **cada corrida recibe todos los periodos y recalcula la serie** (determinista, inmutable); (b) un almacén que acumula corridas | **(a)**: IHN-011 —ninguna corrida histórica se muta—, sin estado que pueda quedar viejo; calcular seis periodos toma 0,03 s |
| 12-8 | Capas y releases | (a) **A** —motor, `bayesrisk.Monitor`, tarjeta de esquema 4, resumen, guía con un bloque que entrena en `consumo_comportamiento` y monitorea `consumo_drift`— en la **2.13.0**, experimental; **B** —pantalla (la tarjeta de una corrida de la pantalla o un `.zip`), informe con su capítulo, Excel; estable— en la **2.14.0**; (b) A y B juntas | **(a)**: como H5; A ya da la respuesta en el notebook, B mueve front, informe y goldens |
| 12-9 | La serie de estabilidad que ya se calcula y no se publica | (a) **publicarla** en Resultados y el informe del scorecard en la capa B (aditivo: ningún hash cambia) y corregir así la ayuda que la promete; (b) sólo corregir la ayuda | **(a)**: es la historia por periodo que el ROADMAP pide para `stability` y hoy la pantalla afirma algo falso |
| 12-10 | La calibración mira también PD demasiado altas (elevada al reproducir la pasada 2) | (a) **las dos colas**: el contraste del BCE (PD demasiado baja) y su espejo (PD demasiado alta), con los mismos cortes; (b) sólo la cola del BCE, como la validación y la escala | **(a)**: la misión es también «menos negados a quien sí podía pagar», y una PD cinco veces más alta que lo observado lo hace; el BCE mira la subestimación porque supervisa capital, no originación; medido, el espejo no agrega ningún rojo en las carteras del paquete |

**Respuestas de Cami (2026-10-12/13, interactivas): la recomendación (a) en las diez.** Vigente:
D-MNT-1 (§12-1) una corrida de monitoreo propia que parte de la tarjeta guardada —`bayesrisk.Monitor`,
la sección `monitoring` y un trabajo nuevo en la pantalla—; D-MNT-2 (§12-2) sólo tarjetas de esquema
4, que congelan su referencia; D-MNT-3 (§12-3) el AUC inicial de Holdout sobre los tramos, y sin
Holdout el de Desarrollo, declarado; D-MNT-4 (§12-4) los cuatro indicadores y el CSI como
diagnóstico, sin migraciones; D-MNT-5 (§12-5) la tabla de §3.5, con redesarrollar cuando la prueba
del BCE y la pendiente de calibración son rojas aunque recalibrar la pendiente devuelva las PD;
D-MNT-6 (§12-6) umbrales constantes; D-MNT-7 (§12-7) cada corrida recalcula la serie entera; D-MNT-8
(§12-8) capa A → 2.13.0 experimental y B → 2.14.0 estable; D-MNT-9 (§12-9) la serie de PSI por
periodo de `stability` se publica en la capa B; D-MNT-10 (§12-10) la calibración mira las dos colas.

## 13. Simplicidad (SDD-31)

- **Entrada mínima:** la tarjeta, la cartera, la columna de periodo y la de desenlace. Se infieren y
  se declaran: la referencia (de la tarjeta), el AUC inicial y su fuente, la frecuencia de una
  columna de fecha (mes).
- **Qué NO se configura:** §5.2.
- **Esenciales:** `bundle`, `period`, `default` (3 ≤ 6); sin «Avanzado».
- **Presupuesto de perillas:** 3 hojas nuevas (`bundle`, `period`, `default`), las
  tres entradas de la institución; cero umbrales.
- **Resumen por etapa:** «Monitoreo»: el veredicto y su acción en una línea, los cuatro indicadores
  del último periodo, las alertas («Qué revisar») y la tabla de periodos como tabla de decisión. Sin
  decisiones humanas.
- **Notebook mínimo:** 3 líneas de usuario (`import`, `Monitor(...)`, `run()`).
- **Las cinco cifras (D-SIM-11)** —líneas del ejemplo · campos visibles de la sección · perillas ·
  segundos al primer resultado · conceptos—: **antes**, el monitoreo no existe (medirlo a mano son
  ~100 líneas de código propio, `medir_h4.py`); **objetivo**, 3 · 3 · 3 ·
  ≈ 1 s · 3 (tarjeta, periodo, desenlace). Las del scorecard (15 · 37 · 414 · ≈ 1 s · 5) no cambian
  en la capa A; la B suma la sección al formulario del trabajo nuevo, no al del scorecard.

## 14. Lo que el código precisó (capa A, S45, 2026-10-13)

Base medida: `375e02e` (2.12.0 con este documento aprobado). Ninguna precisión cambia un contrato
salvo la primera, que decidió Cami.

1. **El ámbar que pide vigilar** (Cami, 2026-10-13, interactivo; «Respuestas de Cami» › S45). La
   fila 3 de §3.5 dice «cualquier ámbar» y el oráculo de §0.3 da «sin acción» en la cartera estable
   en 2024Q1, con el tramo 1 en ámbar (p entre 0,01 y 0,05): las dos fuentes chocaban. Decidido:
   piden vigilar el ámbar de los indicadores de la cartera —el PSI del puntaje o de los tramos, la
   calibración de cartera y cada prueba de discriminación—, no el de un tramo suelto: un tramo rojo
   aislado ya sólo pide vigilar (§0.4-4) y, con K tramos a 0,05, uno sale ámbar por azar en uno de
   cada cuatro o cinco periodos. Con esa lectura el motor reproduce los veredictos de §0.3.
2. **Un p-valor ausente no enciende el espejo.** La tabla por tramo guarda el p-valor de un tramo
   no evaluable como celda vacía (NaN) y el espejo `1 − p` lo convertía en un rojo inventado.
   Defecto propio, visto al medir el motor contra §0.3 antes de cablear el dominio; con su test y
   su control negativo.
3. **El contraste de cartera reutiliza `binomial_by_grade`**: la cartera es «el grado más uno» del
   BCE y la función ya promedia la PD del tramo sobre las mismas filas con desenlace (`M_t`), así
   que no hay un Jeffreys propio. Con menos de 30 filas con desenlace (el mínimo del tramo), la
   cartera queda «no evaluable».
4. **La pendiente se ajusta con Newton sobre los conteos por tramo** (la misma verosimilitud que
   por operación): coincide con `statsmodels` a 1e-8 en los coeficientes y a 2e-6 en el error
   estándar (statsmodels lo evalúa en su última iteración IRLS). La separación perfecta se detecta
   antes de ajustar, con la regla exacta para una covariable. §10 decía que scipy es del núcleo: no
   lo es; el monitoreo, como la escala y la tarjeta, exige `bayesrisk[scoring]`.
5. **La referencia de Desarrollo** vive en `monitoring_reference` del manifiesto, con **conteos**
   —no proporciones—: los cortes interiores, los conteos por bin y por tramo, `n` y el AUC inicial
   con su varianza, sus conteos y su causa si no es evaluable; se valida al leer (cortes
   crecientes, conteos que suman `n`). Toda tarjeta nueva es de esquema 4; el bloque existe sólo
   con la escala. Una tarjeta nueva de la misma corrida cambia de huella; las ya guardadas, no.
6. **`bundle_hash` en el lineage** es un campo opcional de `LineageBundle` que se omite vacío: el
   lineage de toda corrida que no monitorea queda byte a byte igual (gate).
7. **Los resúmenes hablan en la familia «monitoreo»** («Cartera monitoreada», «Monitoreo») y el
   resumen final dice «Veredicto» donde el del scorecard dice «Validación técnica».
8. **El periodo**: un texto se ordena alfabéticamente (la lectura de `stability`), un número en
   orden numérico y una fecha se agrupa por mes (`AAAA-MM`); una fila sin periodo queda fuera y se
   cuenta en «Qué revisar».
9. **La tarjeta se copia al proyecto** (`input/tarjeta-<huella>`), como los datos, y la corrida
   verifica su huella antes de correr.
10. **`Monitoreo.xlsx` va en la capa B**, como fija D-MNT-8 en el registro (el prompt de S45 lo
    listaba en la A).
11. **El oráculo de §0.3 con OptBinning real** (`test_monitoring_oraculo.py`, en un subproceso):
    PSI, tasas, AUC sobre los tramos y pendiente idénticos a S44 a sus decimales, en las cinco
    filas; los veredictos, todos. Los p-valores de la prueba del BCE quedan a ≤ 0,002 de S44, que
    redondeó cifras intermedias con un guion que no quedó en la evidencia; dos no se reproducen
    —la cartera estable en 2023Q2 y 2023Q4: 0,9461 y 0,8948 en S44, 0,9278 y 0,9008 en el motor,
    que es igual al anexo 3.1 par a par—, con el mismo semáforo y sin figurar en §0.3. La
    discriminación rota se reproduce exacta por el motor (0,4732 y −0,115) y, por la puerta, con
    las variables de la OOT barajadas: «redesarrollar».
12. **Las cinco cifras**: 3 · 3 · 3 · ≈ 1–2 s · 2. El SDD estimó 3 conceptos («tarjeta, periodo,
    desenlace»): son los tres argumentos; la regla de los gemelos cuenta lo importado más los
    métodos llamados, `Monitor` y `run`.
13. **Pasada 1 de Codex sobre el código** (`c8133a0`): tres hallazgos, reales y ninguno
    contractual, corregidos con su test nacido rojo y su control negativo. Un AUC inicial con
    varianza nula (Holdout separado o en un solo tramo) se descartaba, aunque §3.4 sólo usa la
    varianza del periodo: ahora se usa (redesarrollar dejaba de ser alcanzable con esa tarjeta).
    Dos periodos enteros mayores que 2⁵³ se fundían al pasar por float y se contaban dos veces:
    ahora se ordenan exactos. Y «sin acción» con evidencia parcial decía que todo estaba en línea y
    el resumen final, «Sin alertas»: ahora la acción dice que parte no se pudo evaluar y la
    evidencia parcial va a «Qué revisar».
14. **Pasada 2 de Codex sobre el código** (`9ce1955`): cuatro hallazgos, reales y ninguno
    contractual —dos completaban arreglos de la pasada 1—, corregidos con su test nacido rojo y su
    control negativo. La huella de la tarjeta entra al lineage sólo después de publicar la
    evidencia: un `run_step` repetido sobre una corrida terminada cambiaba su `bundle_hash` antes
    de chocar con sus artefactos. Un periodo de fechas como objetos —un CSV con fechas ISO llega
    así— se lee como fecha y se agrupa por mes, en la puerta guiada (que lo declara fecha con
    coacción) y en el paso. Los enteros grandes con vacíos (`Int64`) tampoco se funden. Y la
    evidencia parcial del último periodo con desenlace no se pierde cuando lo sigue uno sin
    desenlace.
15. **Pasada 3 de Codex sobre el código**, la última del tope declarado (`c535b85`): tres medium,
    reales y ninguno contractual, corregidos con su test nacido rojo y su control negativo; sin
    cuarta pasada por el criterio declarado. Un CSV con periodos enteros de 2⁵³ o más y vacíos los
    lee como decimales —dos periodos consecutivos ya llegan iguales—: el monitoreo se detiene y pide
    guardarlos como texto, en vez de fundirlos. Un panel con la identidad en el índice (el índice se
    repite entre periodos) chocaba con la unicidad global del paso de datos: la puerta guiada pasa
    ese índice a columna antes del snapshot y la tarjeta lo vuelve a usar como índice al puntuar
    cada periodo. Y la huella de la tarjeta se reconcilia con lo que el intento dejó guardado: si
    el registro de auditoría falla a mitad de la publicación, la tabla que quedó lleva igual su
    `bundle_hash` (y un reintento que no guardó nada sigue sin poder cambiarlo).
16. **Pasada 4 de Codex**, de confirmación, pedida por Cami antes del tag (`5e70fed`): un medium,
    real, introducido por el arreglo del panel de la pasada 3 —un índice sin nombre que se repite
    se descartaba, y una tarjeta con `id=None` (que identifica por ese índice) dejaba pasar un
    duplicado dentro de un periodo y rechazaba un panel con índice textual—. Corregido: el índice
    sin nombre se conserva en una columna reservada (`__bayesrisk_indice__`) con su dtype y el paso
    lo restaura como índice de cada periodo; con su test nacido rojo y su control negativo.
17. **Pasada 5 de Codex**, de confirmación sobre el arreglo de la 4 (`ee74b03`): tres medium,
    reales y ninguno contractual, corregidos con su test nacido rojo y su control negativo. El
    índice volvía a la tarjeta sin su dtype (`to_numpy()`): un índice categórico, con o sin nombre,
    llegaba como texto y la tarjeta lo rechazaba; ahora vuelve con su tipo. Con la identidad en
    columnas (`id="loan_id"`) el índice es auxiliar: un panel de lotes concatenados con sus índices
    locales —repetidos dentro de un periodo— se rechazaba, y ahora el índice vuelve sólo si es único
    en el periodo (si no, la tarjeta puntúa con el de posición y comprueba sus llaves, que siguen
    fallando repetidas). Y `__bayesrisk_indice__` es un nombre reservado: una columna del usuario
    con ese nombre se tomaba por el índice; la puerta la rechaza con su motivo antes de correr.
18. **Pasada 6 de Codex**, la última de confirmación (`a7233e7`): un medium, real y no
    contractual, corregido con su test nacido rojo y su control negativo; sustituye la regla del
    índice auxiliar del punto 17. Con la identidad en columnas, el índice de posición que recibía
    la tarjeta era siempre entero y una tarjeta formada con un índice de texto o categórico lo
    rechazaba por tipo. Ahora, cuando la puerta aplanó un índice que se repite (con o sin nombre:
    la columna reservada es la señal), una tarjeta con llaves recibe un índice de posición **del
    tipo que congeló** y comprueba sus llaves como siempre; el índice no llega a ningún artefacto,
    porque el resultado se realinea por posición. Una tarjeta sin llaves (`id=None`) sigue
    recibiendo el índice original. Y un índice que se repite y se llama como una columna se
    rechaza antes de correr, en vez de caerse con el error de pandas.

## 15. Lo que el código precisó (capa B, S46, 2026-10-13)

Base medida: `db1d638` (la 2.13.0 publicada). Ninguna precisión cambia un contrato.

1. **La tarjeta en la pantalla.** No existía ni la subida de un `.zip` ni un trabajo que consumiera
   la salida de otra corrida. La pantalla guarda la tarjeta con cada corrida del scorecard que se
   puede monitorear (`runs/<run_id>/tarjeta/`, con una ficha al lado para listarla) y la recibe
   como `.zip` (`cards/tarjeta-<huella>/`), validada con la misma lectura que `bayesrisk.Monitor`;
   el `.zip` se comprueba antes de extraer (sólo `manifest.json` y `bins.parquet`, en una carpeta,
   sin rutas fuera de ella y bajo el tope de subida). Las dos rutas nuevas
   (`/api/cards/list` y `/api/cards/upload`) exigen credenciales: listan rutas del `workdir` y
   corridas; el listado es un `POST` porque un `GET` del navegador no lleva `Origin`.
2. **El trabajo «Monitorear un modelo en uso»** lleva `data`, `monitoring`, `report` y
   `governance` latente, como los demás (el gate de D-GOB-11 lo exige; §4.3 no la nombraba), y
   siembra target y partición en «no aplica» (D-ECL-2). Pregunta la tarjeta y el periodo; el
   desenlace es opcional.
3. **`export_excel()` sin argumento**, como las otras puertas (§4.1 lo escribía con una ruta): el
   libro queda en `<run_dir>/<name>/excel/Monitoreo.xlsx`.
4. **El CSI de cada variable por periodo** entra al resumen «Monitoreo» como tabla adicional: es
   la hoja «Variables» del libro y la tercera subsección del capítulo, desde la misma fuente.
5. **La serie de estabilidad (D-MNT-9)** se publica desde el resumen «Estabilidad» —una tabla
   adicional que el informe arma con la misma función—, sin un artefacto nuevo: ningún hash ni
   artefacto de una corrida F1 cambia. La demo publicada no la muestra hasta una recaptura.
6. **El capítulo del informe** («Monitoreo del modelo en uso») es condicional a la card del
   monitoreo, con tres subsecciones —el veredicto con la serie, cada tramo y cada variable por
   periodo— y su paso en la metodología con los umbrales que la card publica; el documento se
   titula «Informe de Monitoreo del Modelo». Las tablas completas del motor van al anexo de
   tablas, como en las demás familias.
