# SDD-34 — Comparar modelos (`bayesrisk.comparison`)

> **Estado: APROBADO por Cami el 2026-10-14** (S48, interactivo), con la recomendación de cada una
> de las nueve decisiones de §12 (D-CMP-1…9, §12-1…9): una corrida de comparación propia; el resumen
> comparable que deja cada corrida terminada; el índice de concentración del BCE; «No evaluable» sin
> escala maestra; comparar y avisar cuando no son las mismas operaciones; la institución elige con
> su motivo; DeLong pareada, frontera como núcleo y un PSI común de fábrica; IFRS 9 en la misma
> enmienda, con los montos restados sólo en la misma unidad; capa A en la 2.15.0 y B en la 2.16.0.
> **Capa A implementada en S49 (2026-10-14), sin publicar** —el resumen comparable en cada corrida
> terminada, el dominio `comparison`, `bayesrisk.Comparison` (experimental) y la familia de
> resúmenes «comparación»; el oráculo de §0.3 reproducido por el motor con OptBinning real; lo que
> el código precisó, en §14— → 2.15.0 con su OK; la capa B, después. Cada release pide su OK aparte. Por decisión de Cami
> del mismo día, tras H2b va H10 (benchmarks públicos).
>
> Propuesto en S47 (2026-10-14). Es el hito **H2b** del ROADMAP, que Cami pidió
> el 2026-10-05 y puso después de la cadena del banco (IFRS 9 firmable → H5 → H4, cerrada con la
> 2.14.0): comparar **N corridas** —el modelo en uso y sus alternativas, por ejemplo diez— sin
> trabajo manual, por variable y por muestra, con dos gráficos de compromiso (AUC frente a PSI, Gini
> frente a un índice de concentración), en el notebook, la pantalla, el informe y el Excel, y también
> para IFRS 9.
>
> **Base medida:** `main` = `c26af2b` (bayesrisk 2.14.0). Las cifras de §0 se midieron **fuera del
> motor**, con las reglas exactas que propone este documento, sobre ocho scorecards y tres
> provisiones de las carteras del paquete. Guiones y salidas, sólo agregados, en el repo privado
> `evidencia/s47/` (`medir_h2b.py`, `medir_h2b_delong.py`, `salidas/medir_h2b*.txt`). El índice de
> concentración se cotejó contra dos fuentes oficiales del BCE (§3.4, `evidencia/s47/cotejo_bce_hi.txt`).
>
> **Corregido tras la pasada 1 de Codex** (dos high y tres medium, los cinco reales; tres
> contractuales, elevados): `data_hash` ordena una copia por índice y no garantiza el orden de la
> muestra, así que la prueba pareada empareja por un **orden canónico** (el índice) y exige la misma
> huella de la muestra efectiva y del desenlace (§3.3, §6.1); comparar el PSI con las bandas de cada
> corrida premia relajar sus cortes —contraejemplo: el mismo PSI 0,15 «Revisar» con 0,10 y «Estable»
> con 0,20—, así que la frontera usa **los cortes de fábrica** para todas y avisa cuando una corrida
> usó otros (§3.5, §12-7, contractual); `bundle_hash` incluye el `config_hash` (en su `fit_lineage`)
> y **no** detecta los repetidos —medido: tres huellas distintas para el mismo modelo—, así que el
> mismo modelo se reconoce por una **huella computacional** de la tarjeta sin su lineage, que sí los
> agrupa (§3.3, §12-2, contractual); varianza cero no implica AUC iguales (AUC 1 frente a 0,5), y
> ese caso queda «prueba no evaluable» (§3.5); y `choose()` se ata a la huella del resumen elegido,
> con la regla de «sin efecto» de D-DEC cuando esa corrida ya no está (§4.1, §12-6, contractual).
> Informe: `evidencia/s47/codex_sdd34_p1_raw.txt`; medición: `salidas/medir_h2b_model_hash.txt`.
>
> **Pasada 2** (dos high y dos medium, los cuatro reales; tres contractuales, elevados): con empates
> no transitivos, una alternativa que a su vez queda superada podía sacar de la frontera a un
> compromiso real —contraejemplo: A empata con B, B con C, A discrimina más que C (p < 0,001) y sólo
> quedaba C—, así que la frontera es el **núcleo** de la relación: un modelo sale sólo si lo supera
> otro que **está** en la frontera, bien definido porque la relación no tiene ciclos (§3.5, §12-7);
> exigir la misma `data_hash` descartaba emparejamientos válidos (otro tamaño de Holdout cambia la
> huella con la misma OOT) y la prueba no pareada **no** es siempre conservadora —contraejemplo: p =
> 0,023 sin parear frente a 0,102 pareada—, así que la prueba se hace **sólo** cuando la muestra
> evaluada es la misma (misma cartera, mismas filas efectivas, mismo desenlace), sin depender de las
> otras muestras, y si no, no hay prueba (§3.3, §12-7); la huella computacional se define **campo
> por campo**, porque el manifiesto guarda procedencia también en la calibración (`anchor_source`),
> con un gate que obliga a clasificar cada campo (§3.3, §12-2); y una corrida terminada sin tarjeta
> —«Validar un modelo existente», con puntajes externos— deja su resumen con los campos que no
> tiene en nulo, sin fallar (§6.1, §12-2). Informe: `evidencia/s47/codex_sdd34_p2_raw.txt`.
>
> **Pasada 3, la última del tope** (un high y un medium, los dos reales y elevados en §12-7 y
> §12-8; S48): fijar los cortes de banda no basta, porque el PSI mismo cambia con la **receta** de
> cada corrida —`psi_bins` va de 2 a 50 y el suavizado es configurable—: con las funciones del
> motor, Desarrollo 0…999 frente a una OOT partida en 250 y 750 da PSI 10,50 «Redesarrollar» con 10
> tramos y 0 «Estable» con 2, y sobre la corrida base real el mismo puntaje da de 0,0019 (2 tramos) a
> 0,0511 (50), así que la frontera usa un **PSI común** con la receta de fábrica, que el resumen mide
> con las mismas funciones de `stability` (reproduce exacto el publicado, 0,006792, y no depende de
> la escala del puntaje) (§3.5, §6.1); y con `report.currency` sin declarar en las dos corridas
> (D-MON: no declarada no es «la misma») los montos de dos provisiones sólo se restan cuando la
> unidad es la misma por construcción —la misma cartera con las mismas columnas de monto— o por
> declaración (§3.7, §8). Informe: `evidencia/s47/codex_sdd34_p3_raw.txt`; medición:
> `evidencia/s48/salidas/medir_h2b_psi_receta.txt`.
>
> **No toca:** el pipeline del scorecard, `performance`, `stability`, `selection`, la escala maestra,
> IFRS 9, el monitoreo, CMF ni el arnés H9R. Ninguna corrida, artefacto, YAML ni `config_hash`
> existente cambia (D-ESC-7). **Sí toca**, y por eso se eleva (§12-2): el layout del directorio de
> corrida de D-GOB-6/7 y el de `runs/<id>/` de la pantalla, con un archivo nuevo (§6.1).
> **No autoriza** bump, tag, PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **SDD** | 34 |
| **Módulo** | `bayesrisk.comparison` (dominio y corrida nuevos); toca `api.run` y `ui/runs.py` (el resumen comparable que deja cada corrida), `core/config` (la sección), `core/lineage` (las huellas comparadas), `guided/` (la puerta `bayesrisk.Comparison` y su resumen), `report`, `ui/jobs.py` + `web/` (capa B) y `docs_site/` |
| **Fase** | F1 (el scorecard, en decisión de comité) y H2 (provisiones) |
| **Tanda de producción** | T9 (SDD-31: un módulo a la vez, con su §13) |
| **Estado** | Aprobado por Cami el 2026-10-14 (§12); capa A implementada en S49, sin publicar (§14) |
| **Depende de** | SDD-07 (`selection`: el IV), SDD-08 (`model`: los coeficientes), SDD-11 (`performance` y `stability`), SDD-22 (`validation`), SDD-31, SDD-32 (la escala maestra: la participación por tramo), SDD-33 (el AUC con la varianza del anexo 3.1 del BCE, `monitoring/engine.py`) |
| **Lo consumen** | La guía del scorecard y la de IFRS 9, un trabajo nuevo de la pantalla, el informe de comparación; H6 (el retador ML, que compara **dentro** de una corrida) |
| **Autor / Fecha** | Claude Code / 2026-10-14 |

---

## Recomendación ejecutiva

Un banco chico entrena varias versiones de su modelo y hoy las compara copiando cifras a una
planilla: la librería sólo pone **dos objetos vivos** lado a lado y como texto (`Scorecard.compare`,
§0.1). Se propone una **corrida de comparación** que lee de cada corrida guardada un **resumen
comparable** —sólo agregados, en JSON, que toda corrida terminada deja desde esta versión— y las
pone lado a lado:

```python
comp = bayesrisk.Comparison(runs=[sc, alternativa, "bayesrisk-runs/consumo_v03"])
comp.run()
```

Por muestra y por variable, con la muestra de evaluación de cada una (la OOT, si no el Holdout); con
el **índice de concentración del BCE** (§3.4), que es el HHI que la escala maestra ya calcula,
normalizado por el número de tramos; con un aviso cuando las corridas no se midieron sobre las mismas
operaciones (§3.3); y con dos gráficos y una **frontera**: los modelos que ningún otro supera en
discriminación y estabilidad (o concentración) a la vez. La comparación **no elige**: la
institución registra su elección con su motivo, y el informe la dice.

Medido sobre seis versiones de un scorecard de la misma cartera (§0.3), la comparación dice algo que
la planilla no dice: **dos de los cinco «retadores» son el mismo modelo** que la referencia (otro
`config_hash`, los mismos coeficientes); las diferencias de AUC entre los demás son **ruido** salvo
una (la prueba de DeLong **pareada**, que usa que son las mismas operaciones, detecta −0,025 con
p < 0,001 donde la no pareada da p = 0,39); y con la misma discriminación, una versión reparte mucho
mejor sus tramos (índice 0,07 frente a 0,13) y pasa la validación que la referencia falla. Las
decisiones de fondo de §12 son **de dónde lee** (§12-2: el resumen comparable, que toca el layout de
D-GOB-6/7), **qué índice** (§12-3: el del BCE, porque el HHI crudo ordena al revés modelos con
distinto número de tramos, medido) y **cómo trata el ruido** (§12-7: empates por la prueba pareada,
porque sobre cifras puntuales una versión que pasa la validación quedaría «superada» por una
diferencia de p = 0,71).

---

## 0. El estado, medido

### 0.1 Lo que hay hoy (sobre `c26af2b`)

Censo del código con tres subagentes de lectura (S47), cada afirmación con su archivo y línea en la
evidencia:

- **`Scorecard.compare(otro)`** (D-FLU-6, `guided/scorecard.py:1155`) pone **dos objetos vivos**
  lado a lado: ejecución, validación, las cinco cifras del resumen final (AUC, Gini y KS de la
  muestra de evaluación, la caída del AUC y el peor PSI), las variables finales y las decisiones.
  Devuelve un `StageSummary` cuyas celdas son **texto ya formateado**: no hay números que graficar ni
  que ordenar. No lee carpetas, no compara más de dos, no muestra IV, CSI ni signo por variable, ni
  las cifras de cada muestra, ni la escala, ni IFRS 9. Dos tests (`test_guided_decisiones.py`) y una
  frase en la guía. `Ecl` y `Monitor` no tienen `compare`.
- **Recargar una corrida guardada** sólo se puede con `Study.load(ruta, trust=True)`, que
  deserializa `joblib` (ejecuta código); la capa `ui` lo tiene prohibido por gate
  (`test_ui_no_deserializa_objetos.py`). `runs.save` de la pantalla no guarda el `Study`, sólo
  `results.json` y los informes, y `results.json` no trae la escala maestra como número ni el IV por
  muestra. Medido de paso: el **primer** `Study.load` de un proceso devuelve las secciones del config
  como `dict` (los dominios todavía no están importados) y `FittedScorecardBundle.from_study` falla
  sobre él; es un defecto aparte, registrado fuera de este documento.
- **Lo que una comparación consume ya existe, por corrida:** AUC, Gini y KS por muestra
  (`("performance", "discriminant_metrics")`), el PSI del puntaje y el CSI de cada variable por
  comparación con su banda (`("stability", "stability_metrics")`), el IV de Desarrollo y por muestra
  (`("selection", "selection_table")`, `("selection", "iv_by_partition")`), el coeficiente, su signo
  y si cumple el esperado (`("model", "coefficients")`), el estado de la validación
  (`("validation", "card").overall_status`) y la participación de cada tramo por muestra
  (`("master_scale", "grade_table")`). Para IFRS 9, ECL, exposición, conteo y cobertura por etapa y
  escenario (`("provisioning_ifrs9", "summary")`).
- **El índice de concentración ya existe** —corrige la fila H2b del ROADMAP, anterior a SDD-32—:
  desde la 2.11.0 la escala maestra publica por muestra el Herfindahl `HHI = Σ participación²` y la
  participación del tramo mayor, sin umbral (D-ESC-3, `master_scale/engine.py:539-552`). No llega al
  canal de métricas ni a `results.json` como número, y su piso es `1/K`: depende del número de
  tramos.
- **La varianza del AUC ya existe**: `monitoring/engine.py::auc_sobre_tramos` da la U de
  Mann-Whitney y la varianza del anexo 3.1 del BCE sobre conteos por tramo; con cada valor distinto
  del puntaje como «tramo» es el AUC del puntaje y su varianza de DeLong. Falta sólo la covarianza
  entre dos modelos sobre las mismas operaciones.
- **Ni la pantalla ni el informe conocen más de una corrida.** No hay historial de corridas ni un
  endpoint que las liste; el store del front guarda la última; `ReportBuilder.collect` recibe un solo
  `Study`. El patrón más cercano es el del monitoreo: `runs.save` deja una ficha liviana por corrida
  (`tarjeta.json`) y `POST /api/cards/list` las lista para un selector.
- **Gráficos:** el informe dibuja con matplotlib (SVG determinista, PNG para Word) y la pantalla con
  recharts; ninguno tiene un gráfico de dispersión entre modelos.
- **Las palabras ya tienen dueño:** «retador» nombra el trabajo «Scorecard con modelo retador» del
  hito H6 (un modelo ML contra el scorecard **dentro** de una corrida, D-PAR). Este documento dice
  **«referencia»** (el modelo en uso, el primero de la lista) y **«alternativas»**.

### 0.2 Lo que necesita un banco chico

El modelador que entrena varias versiones —con y sin una variable, con otros tramos, con otra
ventana— necesita: (1) ponerlas lado a lado desde lo que ya guardó, sin volver a correrlas; (2) por
muestra, cuál discrimina más y si esa diferencia es real; (3) por variable, cuáles comparten y qué
agrega o quita cada una, con su IV, su estabilidad y su signo; (4) saber si la comparación es justa
—las mismas operaciones en cada muestra—; (5) una lectura en palabras y un gráfico que el comité
entienda; (6) registrar cuál eligió la institución y por qué; y (7) lo mismo para dos provisiones de
la misma cartera.

### 0.3 Medido con las reglas de este documento

`bayesrisk.Scorecard` con sus defaults sobre `consumo_comportamiento` (OOT 2024Q2) y cinco
alternativas que cambian una sola cosa; además, la base con **otra partición** y sobre **otra
cartera**. Todo en la OOT (1.008 operaciones, 239 malos, salvo donde se indica). Índice del BCE sobre
la participación por tramo de la OOT (§3.4); prueba de DeLong pareada contra la base sobre el
puntaje publicado (`medir_h2b_delong.py`).

| Corrida | Qué cambia | Variables | AUC | Gini | KS | PSI (banda) | Tramos · HHI · índice BCE | Validación | DeLong pareada contra la base |
|---|---|---|---|---|---|---|---|---|---|
| **base** (referencia) | — | 5 | 0,656 | 0,312 | 0,252 | 0,007 (Estable) | 5 · 0,245 · 0,127 | Falla (Hosmer-Lemeshow en OOT) | — |
| tramos_4 | hasta 4 tramos por variable | 5 | 0,658 | 0,316 | 0,249 | 0,008 (Estable) | 6 · 0,189 · **0,069** | Pasa | +0,001, p = 0,83 |
| iv_005 | IV mínimo 0,05 | 3 | 0,633 | 0,266 | 0,195 | 0,013 (Estable) | 6 · **0,217** · **0,147** | Falla | **−0,025, p < 0,001** (no pareada: p = 0,39) |
| sin_mejor | sin `ingreso_mensual` (IV 0,305) | 4 | 0,650 | 0,299 | 0,242 | 0,017 (Estable) | 5 · 0,307 · 0,267 | Pasa | −0,007, p = 0,71 |
| sin_stepwise | sin selección paso a paso | 5 | 0,656 | 0,312 | 0,252 | 0,007 (Estable) | 5 · 0,245 · 0,127 | Falla | **el mismo modelo** (coeficientes y puntajes idénticos) |
| corr_050 | correlación máxima 0,5 | 5 | 0,656 | 0,312 | 0,252 | 0,007 (Estable) | 5 · 0,245 · 0,127 | Falla | **el mismo modelo** |
| otra_particion | OOT 2024Q1 y 2024Q2 (1.990 op.) | 4 | 0,661 | 0,322 | 0,247 | 0,009 (Estable) | 6 · 0,211 · 0,131 | Falla | no aplica: otras operaciones |
| otra_cartera | `consumo_drift` (1.045 op.) | 5 | 0,712 | 0,424 | 0,320 | **0,745 (Redesarrollar)** | 7 · 0,213 · 0,205 | Falla | no aplica: otros datos |

Variables (la unión de las seis de la misma cartera, todas con el signo esperado): `ingreso_mensual`
(IV 0,305), `deuda_ingreso` (0,164) y `utilizacion_linea` (0,061) en todas; `iv_005` quita
`antiguedad_meses` (0,041) y `mora_max_12m` (0,022); `sin_mejor`, `ingreso_mensual`.

Frontera (§3.5), sobre las seis de la misma cartera:

| Regla | Discriminación y estabilidad | Discriminación y concentración |
|---|---|---|
| Cifras puntuales | base, tramos_4 (y sus dos copias); **superados: iv_005 y sin_mejor** | tramos_4 |
| **Con empates** (DeLong pareada p ≥ 0,05 = empate; PSI por banda) | todas **salvo iv_005** | **tramos_4** |

Provisiones IFRS 9 sobre `ifrs9_retail_latam` (la misma huella en las tres; 5.235 · 477 · 288
operaciones por etapa en las tres):

| Corrida | ECL total | Cobertura | Stage 1 | Stage 2 | Stage 3 | Contra la referencia |
|---|---|---|---|---|---|---|
| **f4** (referencia) | 4.786.739 | 4,19 % | 1.571.504 | 980.623 | 2.234.612 | — |
| horizonte_3 | 4.565.384 | 3,99 % | 1.571.504 | 759.268 | 2.234.612 | −221.355 (−4,6 %), todo en Stage 2 |
| cov_2 (dos covariables) | 4.718.194 | 4,13 % | 1.610.614 | 872.968 | 2.234.612 | −68.545 (−1,4 %): Stage 1 +39.110, Stage 2 −107.655 |

Cada corrida tomó 7–8 s (la primera, 24,6 s con el arranque); armar la comparación sobre los
agregados, milisegundos; la prueba pareada de seis modelos (15 pares), menos de un segundo.

### 0.4 Cinco hallazgos de la medición

1. **Un «retador» puede ser el mismo modelo.** `sin_stepwise` y `corr_050` tienen otro `config_hash`
   y dan exactamente los coeficientes y los puntajes de la base: con estos datos, el paso a paso no
   saca nada y ninguna correlación pasa de 0,5. Una tabla de N columnas los muestra como tres
   modelos. La comparación tiene que decirlo; `bundle_hash` no sirve, porque incluye el
   `config_hash` de la corrida (medido: 9ddd…, 4f97…, df5a… para el mismo modelo), y la huella de la
   tarjeta **sin su lineage** sí los agrupa (fc1b… en los tres, 8945… en `tramos_4`) (§3.3).
2. **Las diferencias de AUC son, casi todas, ruido; la prueba tiene que ser pareada.** El error
   estándar del AUC en esta OOT es ±0,020. Contra la base, `tramos_4` (+0,001, p = 0,83) y
   `sin_mejor` (−0,007, p = 0,71) empatan; `iv_005` discrimina menos (−0,025): la prueba de DeLong
   **pareada** lo detecta con p < 0,001 porque las dos corridas puntúan las mismas operaciones
   (correlación 0,95), mientras que la **no pareada** —que ignora esa correlación— da p = 0,39. Sin
   la prueba pareada, el comité no distingue una caída real de una fluctuación (§12-7).
3. **Sobre cifras puntuales la frontera se equivoca.** Por 0,006 de AUC (p = 0,71) y un PSI de 0,017
   frente a 0,007 —los dos «Estable»—, `sin_mejor` quedaría «superado» por la base, siendo la que
   **pasa** la validación técnica que la base falla. Con empates (DeLong pareada y PSI por banda) sólo
   `iv_005` queda superado en discriminación y estabilidad, y `tramos_4` es la única que ningún otro
   supera en discriminación y concentración: la misma discriminación con los tramos mejor repartidos
   (índice 0,069 frente a 0,127) y la validación aprobada (§3.5, §12-7).
4. **El HHI crudo ordena al revés modelos con distinto número de tramos.** `iv_005` (6 tramos) tiene
   HHI 0,217, menor que el 0,245 de la base (5 tramos), y el índice del BCE dice lo contrario: 0,147
   frente a 0,127. Lo mismo `otra_cartera` (7 tramos): 0,213 contra 0,245 en HHI, 0,205 contra 0,127
   en el índice. El piso del HHI es `1/K` y premia tener más tramos; el índice del BCE lo normaliza
   (§3.4, §12-3).
5. **El `config_hash` no identifica lo que se compara, y la huella de datos mezcla cartera y
   partición.** `otra_cartera` tiene el **mismo** `config_hash` que la base (la ruta de los datos está
   fuera del hash desde la 1.4.0) y otra huella de datos; `otra_particion`, la misma cartera, tiene
   otra huella, porque `data_hash` se calcula después de etiquetar y particionar
   (`data/step.py:111`). Para los tres niveles de §3.3 el resumen guarda las dos huellas: la de la
   cartera antes de particionar y la de la corrida.

---

## 1. Propósito y responsabilidad

**Qué resuelve:** dadas entre 2 y 10 corridas terminadas de la misma familia —scorecards o
provisiones IFRS 9—, ponerlas lado a lado por muestra y por variable, decir si son comparables y si
alguna es el mismo modelo, qué diferencias son reales, cuáles no quedan superadas por ninguna otra y
cuál eligió la institución, en el notebook, la pantalla, el informe y el Excel.

**Hace:** leer de cada corrida su **resumen comparable** (§6.1), verificar su huella, alinear sus
muestras y sus variables, calcular el índice del BCE sobre la participación por tramo que la corrida
ya publicó, la prueba de DeLong pareada cuando las corridas comparten operaciones, la frontera (§3.5)
y la lectura (§3.6); publicar las tablas y los dos gráficos; registrar en el trail las corridas
comparadas y la elección.

**No hace:** volver a correr ni a puntuar ningún modelo (sólo lee lo que cada corrida publicó, con sus
propias reglas); elegir un ganador ni ponderar cifras (§3.5); comparar familias distintas; correr un
YAML (se corre con `bayesrisk run` y se compara su carpeta); comparar corridas de monitoreo;
reemplazar a `Scorecard.compare`, que se queda como la vista rápida de dos objetos vivos (D-FLU-6).

## 2. Contexto y ubicación en la arquitectura

Una corrida de comparación es un `Study` con la sección `comparison` (las corridas), `report` y
`governance` latente, **sin `data`**: no hay cartera, sólo los resúmenes comparables. El paso
`comparison` no requiere artefactos de otro dominio: lee los resúmenes y publica `("comparison",
clave)`. La puerta guiada `bayesrisk.Comparison` construye ese config y lee sus artefactos, como
`bayesrisk.Monitor` (SDD-31 §12.2-5: cliente de `bayesrisk.run`, nunca un segundo orquestador). Cada
corrida de scorecard o de IFRS 9 deja su resumen comparable al terminar (§6.1), venga de la puerta
que venga; la familia de resúmenes se decide desde el config, como hoy (`family_of`).

```
corrida A ─┐  comparable.json (agregados + puntaje de la muestra de evaluación, con huella)
corrida B ─┼─► comparison ──► report
corrida C ─┘       │ comparabilidad · mismo modelo · DeLong pareada
                   │ índice del BCE · frontera · lectura · elección de la institución
```

## 3. Conceptos y fundamentos

### 3.1 Notación

`M = {m_1, …, m_N}` las corridas, `m_1` la **referencia** (el modelo en uso: la primera de la lista).
Por corrida, sus muestras `s ∈ {Desarrollo, Holdout, OOT}` con `AUC_s`, `Gini_s = 2·AUC_s − 1`, `KS_s`
y `n_s`; el PSI del puntaje de cada comparación y su banda; por variable del modelo final, el signo de
su coeficiente, si cumple el esperado, su IV de Desarrollo y por muestra, y su CSI con su banda; con
escala maestra, `K` tramos y la participación `R_{g,s}` de cada tramo.

### 3.2 La muestra de evaluación

Una sola regla, la del resumen final de hoy (`_cinco_cifras`): la **OOT** si la corrida la tiene; si
no, el **Holdout**. El PSI que la acompaña es el del puntaje de Desarrollo contra esa muestra (en las
corridas medidas coincide con el «peor PSI» del resumen final salvo en la base, cuyo peor PSI es el de
Holdout: 0,013 frente a 0,007 en la OOT). Una corrida sin OOT ni Holdout muestra sus cifras de
Desarrollo, declaradas optimistas, y queda fuera de los gráficos y de la frontera.

### 3.3 Comparabilidad y mismo modelo

La comparación es justa sólo si cada modelo se mide sobre **las mismas operaciones**. Con las
huellas que el resumen guarda —la de la cartera antes de etiquetar y particionar, y las de su muestra
de evaluación: las filas efectivas y el desenlace—, tres niveles contra la referencia:

| Nivel | Regla | Qué dice la comparación |
|---|---|---|
| **Misma muestra evaluada** | misma huella de cartera, de filas efectivas y de desenlace en la muestra de evaluación | nada: la comparación es directa y la prueba es pareada |
| **Misma cartera, otra muestra evaluada** | misma huella de cartera, otras filas o desenlace (otra OOT, otro objetivo, una tarjeta que deja filas fuera) | alerta: «B se evaluó sobre otras operaciones de la misma cartera»; sin prueba, las cifras |
| **Otra cartera** | otra huella de cartera | alerta: «B se midió sobre otros datos: la comparación es orientativa»; sin prueba, las cifras |

Nunca bloquea: comparar un modelo redesarrollado con datos nuevos contra el que está en uso es
legítimo, y el comité tiene que saberlo, no dejar de verlo (§12-5).

**El emparejamiento.** `data_hash` hashea una copia ordenada por índice (`data/hashing.py`) y
cubre **todas** las particiones, así que no sirve para emparejar: no garantiza el orden de la
muestra —reordenar la cartera conserva la huella y, si los puntajes se emparejaran por posición, una
permutación dentro de cada clase cambiaría la prueba sin cambiar ningún AUC (pasada 1: el
estadístico pasa de 7,01 a 0,77)— y cambia con otro tamaño de Holdout aunque la OOT sea la misma
(pasada 2). Por eso el resumen guarda la muestra de evaluación en **orden canónico** —por el
índice— y dos huellas de ella: la del índice ordenado de las filas efectivas (las que `performance`
evaluó, sin las que una tarjeta deja fuera) y la del desenlace. La prueba es pareada cuando la
cartera y esas dos huellas coinciden, sin mirar las otras muestras; si no, **no hay prueba**: la no
pareada ignora la correlación y puede salir más significativa que la correcta (pasada 2: p = 0,023
frente a 0,102 pareada, con modelos de orden inverso), así que no es un sustituto seguro. El índice
no se guarda: sólo su huella.

**El mismo modelo.** `bundle_hash` no sirve: incluye el `config_hash` y el entorno de la corrida en
su `fit_lineage`, y el mismo modelo con otro config da otra huella (§0.4-1). Tampoco basta quitar
ese bloque: el manifiesto guarda procedencia también dentro de otros campos —la calibración serializa
`anchor_source`, y dos corridas que resuelven la misma PD objetivo por caminos distintos aplican la
misma transformación con otra fuente declarada (pasada 2)—. La **huella computacional** es una
proyección **campo por campo** del manifiesto: entra lo que la aplicación consume para puntuar —las
reglas de cada variable (`rules_sha256`), las variables, el intercepto y los coeficientes, el
escalamiento del puntaje, el método y los parámetros ajustados de la calibración, los tramos y su PD,
el tratamiento de especiales y no vistos— y sale la procedencia —`fit_lineage`, `anchor_source`,
`monitoring_reference`, `bundle_hash`, `files`, la columna de identidad—. Un gate enumera los campos
del manifiesto y exige que cada uno esté clasificado en una de las dos listas, en los dos sentidos:
un campo nuevo de la tarjeta no entra ni sale de la huella sin una decisión. Dos corridas con la
misma huella computacional son **el mismo modelo**, lo diga o no su `config_hash`, y la lectura lo
dice primero (§12-2). Una corrida sin tarjeta (puntajes externos) no tiene huella computacional: no
se la declara igual a ninguna. En IFRS 9: la
misma regla de huellas, más la fecha de corte y la moneda del informe; dos provisiones con el mismo
ECL por etapa «dan la misma provisión».

### 3.4 El índice de concentración del BCE

El BCE (*Instructions for reporting the validation results of internal models*, febrero 2019,
§2.5.5.3 «Concentration in rating grades») mide si los tramos tienen «dispersión significativa» con el
índice de Herfindahl normalizado:

```
CV = √( K · Σ_g (R_g − 1/K)² ),     HI = 1 + ln( (CV² + 1) / K ) / ln(K)
```

con `K` el número de tramos y `R_g` la frecuencia relativa del tramo `g`. Como
`K · Σ (R_g − 1/K)² = K · Σ R_g² − 1`, se reduce a

```
HI = 1 + ln(HHI) / ln(K),     HHI = Σ_g R_g²
```

—el HHI que la escala maestra **ya publica**—, y queda en `[0, 1]`: 0 si los `K` tramos pesan
igual, 1 si todo cae en uno. A diferencia del HHI, **no depende del número de tramos**, y por eso es
el que se compara entre modelos con escalas distintas (§0.4-4). Cotejado contra dos fuentes
oficiales —el PDF (p. 26–27) y la plantilla oficial de reporte (libro PD, hojas 3.0 y 4.0:
`HI_curr = 1 + LN((K·SUM(Y8:Y47) + 1)/K)/LN(K)`)—, que coinciden en forma y orientación
(`evidencia/s47/cotejo_bce_hi.txt`). Se pondera **por número de operaciones**: la versión del BCE por
exposición exige la exposición original, que un scorecard no tiene. La prueba de Miller (1991) que el
BCE asocia compara el índice **de un mismo modelo** entre la validación inicial y hoy; entre modelos
distintos no aplica y no se calcula. Ni el BCE ni Basilea (§403, §409: «sin concentraciones
excesivas») fijan un umbral: se publica y no se alerta, como D-ESC-3. Sin escala maestra no hay
tramos y el índice queda «No evaluable» para esa corrida, con la razón (§12-4); la puerta guiada
corre la escala por defecto, el preset F1 y un YAML sin la sección no.

### 3.5 La frontera, no un ganador

Un modelo queda **superado** si otro es al menos igual de bueno en las dos cifras de un gráfico y
estrictamente mejor en una. «Igual de bueno» no es «la misma cifra con cuatro decimales» (§0.4-3):

- **Discriminación** (AUC o Gini, en la muestra de evaluación): dos modelos **empatan** si la prueba
  de DeLong pareada no rechaza la igualdad (p ≥ 0,05, el corte que la librería ya usa, D-VAL-15);
  uno es mejor si la rechaza a su favor. Sin la misma muestra evaluada no hay prueba y se comparan
  las cifras, declarado (§3.3). Si la varianza
  de la diferencia es cero, empatan sólo si los dos AUC son iguales; con AUC distintos (uno separa
  perfecto, AUC 1, y otro puntúa todo igual, 0,5) la prueba es «no evaluable» y se comparan las
  cifras, declarado.
- **Estabilidad** (PSI del puntaje): **por banda** —Estable, Revisar, Redesarrollar—, la lectura
  que la librería ya da al PSI; dos PSI de la misma banda empatan. La frontera usa un **PSI común**,
  medido con **la receta de fábrica** para todas las corridas —10 tramos por cuantiles de
  Desarrollo, suavizado 1e-6 y cortes 0,10 y 0,25, los defaults de `stability`—, no con la de cada
  una: la receta es configurable, y con la propia la frontera premiaría cambiar la medición. Con los
  cortes, el mismo PSI 0,15 sería «Revisar» con 0,10 y «Estable» con 0,20 (pasada 1); con los
  tramos, el mismo puntaje da 10,50 o 0 según se cuente en 10 o en 2 (pasada 3, con las funciones
  del motor), y en la corrida base real, de 0,0019 a 0,0511 entre 2 y 50 tramos. El resumen de cada
  corrida mide ese PSI común con las mismas funciones de `stability` sobre los mismos puntajes de
  Desarrollo y de la muestra de evaluación (§6.1); con la receta de fábrica coincide con el
  publicado (medido: 0,006792 en los dos) y, por ir sobre cuantiles, no depende de la escala del
  puntaje. Si una corrida evaluó con otra receta, la tabla muestra también su PSI y su banda propios
  y la lectura lo avisa; sin `stability` o sin muestra de evaluación, el PSI común queda «No
  evaluable» y el modelo sale del primer gráfico (§12-7).
- **Concentración** (índice del BCE): por valor; no hay prueba entre modelos ni umbral (§3.4).

La **frontera** es el núcleo de esa relación: un modelo queda fuera sólo si lo supera otro que
**está** en la frontera. No basta «lo supera alguno»: con empates no transitivos, una alternativa
que a su vez queda superada podría sacar a un compromiso real (pasada 2: A empata con B y B con C, A
discrimina más que C con p < 0,001, B concentra menos que A y C menos que B; con «lo supera alguno»
sólo queda C; con el núcleo, A y C). El núcleo existe y es único porque la relación no tiene ciclos:
en un ciclo la segunda cifra no podría empeorar en ningún paso, así que sería igual en todos, y cada
paso tendría que mejorar la discriminación de forma significativa, lo que exige AUC estrictamente
crecientes alrededor del ciclo. Se calcula en orden: primero los que nadie supera, después cada uno
contra los ya admitidos. En la medición de §0.3 da lo mismo que «lo supera alguno». Es lo único que
la comparación concluye: elegir
dentro de la frontera es pesar discriminación contra estabilidad o concentración, y ese peso es de la
institución (un puntaje compuesto sería una perilla sin evidencia, SDD-31). La elección se registra
con su motivo (§4.1, §12-6). Una cifra no evaluable deja al modelo fuera de ese gráfico y de su
frontera, declarado. Con N corridas se hacen `N(N−1)/2` pruebas (45 con diez); no se corrige por
multiplicidad y se declara.

### 3.6 La lectura

Entre 3 y 8 líneas, con reglas constantes y en este orden, cada una sólo si aplica:

1. La comparabilidad (§3.3), si no son las mismas operaciones, y los modelos repetidos.
2. Discriminación: quién discrimina menos o más que la referencia de verdad, y quiénes empatan
   («En discriminación empatan base, tramos_4 y sin_mejor; iv_005 discrimina menos: Gini 0,266
   frente a 0,312, p < 0,001»).
3. Estabilidad: las bandas, si difieren («Todas son estables» si no).
4. Concentración, si hay índice («Reparte mejor sus tramos: tramos_4, índice 0,07 frente a 0,13»).
5. La frontera de cada gráfico y quién supera a quién.
6. Quién pasa y quién falla la validación técnica, con su motivo.
7. Las variables: cuántas comparten todos y qué agrega o quita cada alternativa.
8. La elección de la institución, si se registró.

Con la medición de §0.3 la lectura sería: «Las seis corridas usan las mismas operaciones;
sin_stepwise y corr_050 son el mismo modelo que la base. En discriminación empatan base, tramos_4 y
sin_mejor; iv_005 discrimina menos (Gini 0,266 frente a 0,312; p < 0,001). Todas son estables.
Reparte mejor sus tramos: tramos_4 (índice 0,07 frente a 0,13). Ninguna otra supera a tramos_4 en
discriminación y concentración. Pasan la validación técnica tramos_4 y sin_mejor; la base falla por
Hosmer-Lemeshow en OOT. Comparten tres variables; iv_005 quita antiguedad_meses y mora_max_12m, y
sin_mejor, ingreso_mensual».

### 3.7 IFRS 9

Para provisiones, la comparación pone lado a lado, por etapa (1, 2, 3 y total): operaciones,
exposición, ECL y cobertura; y contra la referencia, la diferencia de ECL en monto y porcentaje y la
etapa donde está la mayor. Los escenarios de cada corrida (nombres y pesos) se listan. Sin gráficos
ni frontera: el pedido es para scorecards, y en provisiones «más» no es «mejor». La lectura dice la
comparabilidad, quién provisiona más y cuánto, dónde está la diferencia («horizonte_3 provisiona
221.355 menos que f4 (−4,6 %), todo en Stage 2») y la elección.

**La unidad de los montos** (pasada 3). `report.currency` sin declarar significa «no declarada»
(D-MON), no «la misma»: dos provisiones con la moneda en nulo pueden estar en dólares y en pesos.
Los montos de dos corridas se restan —diferencia en monto y en porcentaje, «más» y «menos»— sólo
cuando la unidad es la misma **por construcción** (la misma huella de cartera y las mismas columnas
de monto —exposición, saldo y límite—, sin monedas declaradas distintas: los montos salen de los
mismos números) o **por declaración** (las dos declaran la misma moneda). En otro caso —monedas
declaradas distintas, o carteras distintas sin las dos monedas declaradas iguales— cada provisión
se muestra con su unidad (o sin ella, si no se declaró), la cobertura por etapa, que no tiene
unidad, se compara en puntos, y la lectura dice por qué no se restan los montos. Las tres
provisiones de §0.3 no declaran moneda y comparten cartera y columnas: se restan.

## 4. API: guiada, completa y pantalla

### 4.1 Puerta guiada

```python
from bayesrisk import Comparison

comp = Comparison(runs=[sc, alternativa, "bayesrisk-runs/consumo_v03"])
comp.run()
comp.summary()                                   # la lectura, los modelos y la frontera
comp.choose("consumo_v03", motivo="misma discriminación, tramos mejor repartidos")   # opcional
comp.export_excel()                              # Comparación.xlsx (capa B)
```

`runs` acepta, en cualquier mezcla: un `Scorecard`, un `Ecl` o un `Study` ya corridos; la carpeta de
un proyecto guiado (`<run_dir>/<name>/`), el `run_dir` de `bayesrisk.run`, la carpeta de una corrida
de la pantalla (`runs/<id>/`) o el `comparable.json` mismo. El orden es el de la lista y la primera
es la referencia. La puerta copia cada resumen a `input/` del proyecto con su huella en el nombre
(como `Monitor` copia la tarjeta), así que la comparación se reproduce desde su carpeta. Sin datos,
sin columnas, sin umbrales: nada más que preguntar.

`choose(nombre, motivo)` registra la elección de la institución en la sección INFRA `decisions`
(D-DEC: fuera del `config_hash`) y como decisión del trail con `autor` y `motivo` (D-GOB-17); el
resumen y el informe la dicen. Vuelve a correr la comparación, como `set_cutoff`. El nombre sólo
sirve para encontrarla: la decisión se ata a la **huella del resumen elegido**, no al nombre ni a la
posición, así que reordenar las corridas no la mueve y, si esa huella ya no está entre las
comparadas (se reemplazó la corrida o cambió su resumen), la decisión queda **sin efecto**, con la
regla y el aviso de D-DEC para un registro cuyo sujeto cambió; dos corridas con el mismo nombre se
eligen por su posición en la llamada y quedan registradas por su huella. Es una extensión de D-DEC
(un registro cuyo sujeto es una corrida comparada y no una hoja del config), elevada en §12-6.

### 4.2 Puerta completa

```yaml
comparison:
  runs:
    - bayesrisk-runs/consumo_v01/run
    - bayesrisk-runs/consumo_v02/run
report: {}
```

Las rutas quedan **fuera del `config_hash`**, con la huella de cada resumen en el lineage (§9), como
la tarjeta del monitoreo (D-MNT) y las tablas de escenarios (D-FIR).

### 4.3 Pantalla (capa B)

Un trabajo nuevo, **«Comparar modelos»** (`comparison`, `report` y `governance` latente; sin
`data`): un selector lista las corridas de la misma pantalla que dejaron su resumen
(`POST /api/comparables/list`, con credenciales, como las tarjetas) y deja subir un `comparable.json`
hecho por código (`POST /api/comparables/upload`); se marcan entre 2 y 10 y una como referencia, que
pasa a ser la primera. Resultados muestra la lectura, la tabla de modelos, los dos gráficos, las
variables y, en IFRS 9, la tabla por etapa. Un trabajo sin `data` es nuevo en la pantalla: hoy todos
empiezan por «Cargar datos» (§8).

## 5. Configuración

### 5.1 La sección `comparison`

| Hoja | Tipo | Default | Esencial | Qué es |
|---|---|---|---|---|
| `comparison.runs` | lista de rutas, de 2 a 10 | — (obligatoria) | sí | Las corridas, en orden; la primera es la referencia |

Es la única hoja. La sección nace después de la 2.10.0: se serializa sólo cuando está declarada
(D-ESC-7), así que ningún YAML ni preset existente cambia.

### 5.2 Lo que NO se configura

- **Qué muestra se compara:** la regla de §3.2, la misma del resumen final.
- **La receta del PSI de la frontera:** la de fábrica para todas (§3.5); la tabla muestra también
  el PSI y la banda de cada corrida, y las bandas del CSI son las que cada una publicó.
- **Un peso entre cifras, un puntaje compuesto o un ganador:** §3.5; la institución elige.
- **El corte de la prueba de DeLong:** 0,05, el de la librería (D-VAL-15), nombrado en el informe.
- **Un umbral de diferencia importante o de concentración:** ninguna fuente lo da (§3.4).
- **La ponderación del índice:** por número; por exposición no se calcula (§3.4).
- **Qué variables se muestran:** todas las del modelo final de alguna corrida.
- **Los ejes de los gráficos:** AUC y PSI; Gini e índice del BCE.
- **El tope de corridas:** 10, constante, porque la tabla de variables pone una columna por modelo y
  con más no se lee en el informe; más es un error que lo dice.

### 5.3 Identidad

El `config_hash` de una comparación sale de la sección sin las rutas, de `report` y del resto, como
siempre (D-HASH-8). **Qué** se comparó vive en el lineage: la huella de cada resumen, en orden (§9).
La elección (`decisions`) queda fuera del hash, como toda decisión (D-DEC).

## 6. Contratos de datos

### 6.1 El resumen comparable (`comparable.json`)

Cada corrida **terminada** (`done`) de scorecard o de IFRS 9 lo escribe al cerrar: `bayesrisk.run` en
su `run_dir` —y por eso también la puerta guiada, en `<name>/run/`— y `runs.save` en `runs/<id>/`.
Una sola función lo arma desde el `Study`, para las tres puertas. JSON, nunca pickle; números, nunca
texto formateado; ningún identificador de operación:

```json
{
  "schema_version": 1, "bayesrisk": "2.15.0", "family": "scorecard",
  "name": "consumo_v02", "created_at": "…", "config_hash": "…",
  "data_hash": "…", "portfolio_hash": "…", "model_hash": "…", "currency": "CLP",
  "psi_recipe": {"bins": 10, "smoothing": 1e-06, "thresholds": [0.10, 0.25]},
  "samples": [{"sample": "oot", "n": 1008, "n_bad": 239, "auc": 0.658, "gini": 0.316, "ks": 0.249, "status": "ok"}],
  "evaluation_sample": "oot",
  "evaluation_scores": {"order": "index", "rows_hash": "…", "default_hash": "…",
                        "score": [612, 587, …], "default": [0, 1, …]},
  "score_psi": [{"comparison": "dev_vs_oot", "psi": 0.0078, "band": "stable"}],
  "score_psi_common": {"comparison": "dev_vs_oot", "psi": 0.0078, "band": "stable", "reason": null},
  "grades": {"k": 6, "share_by_sample": {"desarrollo": [0.18, …], "oot": […]}},
  "variables": [{"feature": "deuda_ingreso", "beta": -0.81, "sign_ok": true, "iv_development": 0.164,
                 "iv_by_sample": {"oot": 0.15}, "csi": [{"comparison": "dev_vs_oot", "csi": 0.004, "band": "stable"}]}],
  "validation": {"status": "pass", "reason": null}
}
```

- `portfolio_hash` es la huella de la cartera antes de etiquetar y particionar, con el mismo
  algoritmo que `data_hash` (§0.4-5); `model_hash`, la huella computacional de la tarjeta, la
  proyección campo por campo de §3.3, no su `bundle_hash`; `psi_recipe`, la receta con que la
  corrida evaluó su PSI (tramos, suavizado y cortes); `score_psi_common`, el PSI del puntaje
  Desarrollo → muestra de evaluación con la receta de fábrica, medido al escribir el resumen con las
  mismas funciones de `stability` y los mismos puntajes que ella leyó —igual al publicado cuando la
  receta es la de fábrica—, o nulo con su razón si la corrida no publicó `stability` (§3.5).
- `evaluation_scores` son el puntaje con que `performance` calculó el AUC y el desenlace de cada
  operación **efectivamente evaluada** de la muestra de evaluación, **en orden canónico por el índice
  y sin identificadores**; `rows_hash` es la huella de ese índice ordenado y `default_hash`, la del
  desenlace. Sirven sólo para la prueba pareada, y sólo cuando las dos huellas coinciden (§3.3,
  §12-2, §12-7). Una OOT de 100.000 operaciones son ~1 MB.
- Para IFRS 9, en lugar de `samples` … `variables`: `as_of`, `scenarios` (nombre y peso),
  `amount_columns` (los nombres de las columnas de exposición, saldo y límite, para la regla de la
  unidad de §3.7) y `by_stage` (etapa, operaciones, exposición, ECL, cobertura). `currency` es la
  de `report.currency`, nula si no se declaró o si la corrida no tiene `report`.
- **Quién lo escribe:** toda corrida terminada (`done`) de la familia scorecard que publicó
  `performance`, y toda de IFRS 9 que publicó su provisión. Cada campo que la corrida no tiene va en
  nulo con su razón —una corrida de «Validar un modelo existente» (puntajes y PD externos) no tiene
  tarjeta, variables ni `model_hash`; una sin escala, `grades`—, y la comparación los muestra «No
  aplica». Armarlo nunca hace fallar una corrida terminada: si algo inesperado lo impide, la corrida
  sigue `done`, el trail registra la advertencia y la comparación dice que esa corrida no tiene
  resumen (D-VIS: ningún error sin superficie). El flujo de puntajes externos tiene su test.
- Una corrida que no terminó, o que paró antes de `performance` (`until`), no lo escribe. Las
  guardadas antes de la versión que lo trae no lo tienen: la comparación lo dice y cómo obtenerlo
  (§8).

### 6.2 Artefactos de la corrida de comparación

| Clave | Contenido |
|---|---|
| `("comparison", "runs")` | Una fila por corrida: nombre, familia, versión, `config_hash`, huella del resumen, nivel de comparabilidad y su motivo, «el mismo modelo que …» |
| `("comparison", "models")` | Una fila por modelo: muestra de evaluación, AUC, Gini, KS, PSI común y su banda (y el propio, si otra receta), índice y `K`, número de variables, validación, si está en cada frontera y quién lo supera |
| `("comparison", "tests")` | Una fila por par: diferencia de AUC, si hubo prueba (pareada) o por qué no, estadístico y p-valor |
| `("comparison", "samples")` | Largo: modelo × muestra con `n`, malos, AUC, Gini, KS |
| `("comparison", "variables")` | Una fila por variable de la unión: por modelo, si entra, signo, si cumple el esperado, IV de Desarrollo y de evaluación, CSI y banda |
| `("comparison", "provision")` | IFRS 9: modelo × etapa con operaciones, exposición, ECL, cobertura y la diferencia contra la referencia |
| `("comparison", "reading")` | Las líneas de §3.6 |

### 6.3 Resumen, informe y Excel (capa B)

Una familia de resúmenes nueva, **«comparación»**, con una etapa («Comparación»): la lectura como
líneas, la tabla de modelos como tabla de decisión y las variables (o la provisión por etapa) como
tabla adicional; su `_repr_html_` lleva los dos gráficos, el mismo SVG del informe. El informe tiene
su capítulo, «Comparación de modelos» (las corridas y su comparabilidad; discriminación y estabilidad
con el gráfico AUC frente a PSI y la tabla de pruebas; concentración con Gini frente al índice; las
variables; la elección), su página ejecutiva con la lectura y su título («Informe de Comparación de
Modelos»). `comp.export_excel()` deja `excel/Comparación.xlsx`, un libro único: Resumen, Modelos,
Pruebas, Muestras, Variables (o Provisión por etapa) e Índice.

## 7. Algoritmo

1. Leer cada entrada: un objeto vivo se resume con la función de §6.1; una carpeta, su
   `comparable.json`. Copiarlo a `input/` con su huella.
2. Validar: entre 2 y 10; todas de la misma familia; ninguna repetida (misma huella de resumen);
   esquema conocido. Los nombres repetidos se distinguen con su posición («consumo (2)»).
3. Comparabilidad de cada una contra la referencia y el mismo modelo (§3.3).
4. Por modelo: la muestra de evaluación (§3.2), sus cifras y el índice de §3.4.
5. Por par con la misma muestra evaluada (§3.3): la prueba de DeLong pareada —el AUC y la varianza
   de `auc_sobre_tramos` con cada valor del puntaje como tramo, más la covarianza de los componentes
   de los dos modelos, emparejados por el orden canónico—; varianza cero con AUC distintos, «no
   evaluable». Sin la misma muestra evaluada, ninguna prueba.
6. Las dos fronteras con los empates de §3.5, como el núcleo de la relación.
7. La unión de variables, en el orden de la referencia y luego por primera aparición.
8. La lectura (§3.6). Publicar los artefactos; el trail registra las corridas y sus huellas.

Todo es aritmética sobre agregados y un vector por corrida: segundos, no minutos, aunque las corridas
hayan tardado horas.

## 8. Casos borde

- **Una corrida sin resumen** (guardada antes de la versión que lo trae, o que no terminó): error que
  dice cuál y cómo obtenerlo —volver a correrla con esta versión (mismo config, mismos resultados) o
  pasar el objeto vivo; si sólo queda la carpeta del estudio, `Study.load(ruta, trust=True)` y pasar el
  `Study`, que es la decisión de confianza explícita de quien lo carga—.
- **Familias mezcladas, una sola corrida, más de 10, una repetida:** error con el porqué.
- **Sin OOT ni Holdout:** cifras de Desarrollo, declaradas optimistas; fuera de gráficos y frontera.
- **Partición al azar:** el PSI de Desarrollo contra Holdout no mide deriva temporal (es la misma
  población); la lectura lo dice en vez de premiar al «más estable».
- **Sin escala maestra o con un solo tramo:** índice «No evaluable», fuera del segundo gráfico.
- **Una muestra no evaluable** (pocos malos): sus cifras vacías con la razón de la corrida; sin prueba.
- **Varianza nula en la prueba:** con los dos AUC iguales (dos modelos idénticos), empate sin
  estadístico; con AUC distintos (separación perfecta frente a un puntaje constante), «no evaluable»
  y se comparan las cifras (§3.5).
- **Un modelo deja filas fuera que otro no** (una regla de tratamiento rechaza operaciones): otra
  muestra evaluada de la misma cartera; sin prueba, las cifras, declarado.
- **Otro tamaño de Holdout con la misma OOT:** otra `data_hash`, la misma muestra evaluada; prueba
  pareada.
- **Una corrida con puntajes externos** («Validar un modelo existente»): sin tarjeta ni variables;
  se compara por muestra y, si comparte la muestra evaluada, con prueba.
- **Monedas o fechas de corte distintas** (IFRS 9): «otra cartera»; los montos no se restan.
- **Moneda sin declarar** (IFRS 9; las dos en nulo, o una sin `report`): no prueba la misma unidad
  (D-MON); los montos se restan sólo con la misma cartera y las mismas columnas de monto, y si no,
  se muestran por separado y se compara la cobertura (§3.7).
- **Otra receta del PSI** (otros tramos, suavizado o cortes): la frontera usa el PSI común de
  fábrica; la tabla muestra también el propio y la lectura lo avisa (§3.5).
- **Pantalla:** el trabajo sin `data` es el primero; la capa B mide qué pasos del front lo asumen
  (cargar datos, columnas, perfil) antes de programar.

## 9. Reproducibilidad y auditoría

Determinista: no hay azar ni ajuste. El lineage de la comparación agrega `comparison_hashes` (la
huella de cada resumen, en orden; omitido si vacío, como `bundle_hash`); el trail registra cada
corrida comparada (nombre, `config_hash`, versión, huella), la comparabilidad, los modelos repetidos y
la elección. Un resumen que cambia cambia su huella: la misma comparación con otro resumen es otra
identidad declarada. El canal de métricas no recibe nada (`comparison` entra a
`DOMAINS_WITHOUT_METRICS`, como el monitoreo).

## 10. Dependencias

Internas: `performance`, `stability`, `selection`, `model`, `validation`, `master_scale`,
`provisioning.ifrs9` (sus artefactos, sólo lectura), `monitoring.engine` (el AUC y su varianza),
`scorecard.bundle` (la huella de la tarjeta), `guided`, `report`. Externas: ninguna nueva.

## 11. Tests

- **Oráculo:** las cifras de §0.3 reproducidas por el motor desde corridas reales (subproceso,
  OptBinning real): los índices, las pruebas, las fronteras con y sin empates, los modelos repetidos,
  la comparabilidad y la lectura; y la tabla de IFRS 9.
- **El índice del BCE contra su plantilla:** un caso chico calculado con la fórmula de la hoja 4.0 y
  con `1 + ln(HHI)/ln(K)`.
- **La prueba pareada contra una implementación directa** de DeLong (par a par) en un caso chico; los contraejemplos de la pasada 1: la cartera
  reordenada (y permutada dentro de cada clase) da la misma prueba; AUC 1 frente a 0,5 con varianza
  cero, «no evaluable»; el mismo PSI con cortes 0,10 y 0,20 no cambia la frontera; los tres modelos
  repetidos de §0.3 se agrupan y `tramos_4` no; una elección hecha antes de reordenar o reemplazar
  corridas sigue en la misma huella o queda sin efecto. Y los de la pasada 2: los tres modelos A, B
  y C del empate no transitivo dan la frontera {A, C}; otro tamaño de Holdout con la misma OOT
  conserva la prueba pareada; dos muestras distintas no reciben prueba; dos corridas que sólo
  difieren en la procedencia del ancla tienen la misma huella computacional; el gate de clasificación
  de los campos del manifiesto en los dos sentidos; una corrida de puntajes externos deja su resumen
  y termina `done`. Y los de la pasada 3: el contraejemplo de 10 y 2 tramos (PSI propio 10,50 y 0,
  el mismo PSI común y la misma frontera); el PSI común igual al publicado con la receta de fábrica
  e igual con el puntaje reescalado; dos provisiones con la moneda en nulo, o una sin `report`,
  sobre carteras distintas no restan montos y sobre la misma cartera con las mismas columnas sí.
- **Las tres puertas** con el mismo config, el mismo `config_hash` y los mismos artefactos.
- **El resumen comparable** igual desde el objeto vivo, desde `bayesrisk.run` y desde `runs.save`; sin
  identificadores de operación.
- **Aditivo:** ninguna corrida existente cambia de resultados; el YAML sin la sección, idéntico
  (D-ESC-7); el lineage de una corrida que no compara, byte a byte.
- Controles negativos: un resumen alterado (huella), una corrida de otra cartera sin su alerta, una
  frontera sobre cifras puntuales, una prueba entre muestras evaluadas distintas, una frontera que no es el núcleo, el HHI crudo en
  vez del índice, el PSI propio en vez del común en la frontera, montos restados con las dos monedas
  en nulo sobre carteras distintas.

## 12. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 12-1 | Dónde vive la comparación | (a) **una corrida propia** (`bayesrisk.Comparison`, sección `comparison`, trabajo nuevo de la pantalla); (b) ampliar `Scorecard.compare` a N objetos, sin corrida | **(a)**: es la única que llega al informe, la pantalla y el Excel con las tres puertas y la misma identidad, como el monitoreo (D-MNT-1); (b) no tiene informe ni pantalla y sigue exigiendo objetos vivos |
| 12-2 | De dónde lee cada corrida (contractual: toca D-GOB-6/7) | (a) **un resumen comparable** (`comparable.json`) que toda corrida terminada de scorecard o IFRS 9 deja desde la versión que lo trae —en el `run_dir` de `bayesrisk.run` y en `runs/<id>/` de la pantalla—, con agregados, la huella computacional del modelo (proyección campo por campo del manifiesto, con su gate) y el puntaje de la muestra de evaluación en orden canónico, sin identificadores, con los campos que la corrida no tiene en nulo (una validación de puntajes externos no tiene tarjeta); y los objetos vivos; (b) además, carpetas viejas por `Study.load(trust=True)` en la puerta de código | **(a)**: una sola fuente para las tres puertas, sin pickle (la pantalla no puede deserializar, por gate) y portable (se sube a la pantalla); (b) ejecuta código al leer una carpeta que un YAML nombra y deja a la pantalla con otra fuente; las corridas viejas se comparan re-corriéndolas (mismo config, mismos resultados) o pasando el `Study` que su dueño cargó |
| 12-3 | Qué índice de concentración | (a) **el del BCE** (§2.5.5.3), `1 + ln(HHI)/ln(K)`, por número de operaciones, sobre los tramos de la escala maestra; (b) el HHI crudo que la escala ya publica; (c) la participación del tramo mayor | **(a)**: medido, el HHI crudo ordena al revés modelos con distinto número de tramos (§0.4-4), y el índice del BCE tiene fuente oficial doble; la escala sigue publicando su HHI |
| 12-4 | Una corrida sin escala maestra | (a) **índice «No evaluable»** para esa corrida, con la razón, y fuera del segundo gráfico; (b) formar tramos sólo para comparar | **(a)**: (b) sería un segundo motor de tramos; la puerta guiada ya corre la escala por defecto |
| 12-5 | Corridas que no se midieron sobre las mismas operaciones | (a) **comparar y avisar**, con los tres niveles de §3.3 y la prueba que corresponde a cada uno; (b) rechazar todo lo que no sean las mismas operaciones | **(a)**: comparar el modelo nuevo con el que está en uso sobre datos distintos es el caso real del redesarrollo; el comité tiene que verlo con su advertencia |
| 12-6 | Quién elige (contractual desde la pasada 1: extiende D-DEC) | (a) **la comparación no elige**: muestra la frontera y la institución registra su elección con motivo (`choose`, una decisión en el trail y en el informe), atada a la huella del resumen elegido y sin efecto si esa corrida ya no está (§4.1); (b) un puntaje ponderado que ordena los modelos; (c) frontera sin registro de la elección | **(a)**: el peso entre discriminación y estabilidad es política de la institución (b sería una perilla sin evidencia); SR 11-7 pide documentar por qué se eligió un modelo, y (c) deja esa razón fuera del informe |
| 12-7 | El ruido en la discriminación y la medida de la estabilidad (ampliada por las pasadas 1, 2 y 3) | (a) **prueba de DeLong pareada** sólo entre corridas con la misma muestra evaluada (sin prueba si no: la no pareada puede salir más significativa que la correcta, p = 0,023 frente a 0,102), en la frontera dos AUC empatan si p ≥ 0,05 y la frontera es el **núcleo** (sale sólo el superado por un modelo de la frontera: con empates no transitivos, «lo supera alguno» sacaba a un compromiso real); la estabilidad se compara por banda con un **PSI común de receta de fábrica para todas** (10 tramos, suavizado 1e-6, cortes 0,10 y 0,25), que el resumen mide con las funciones de `stability`, avisando si una corrida usó otra receta (pasadas 1 y 3); (b) como (a), pero exigiendo que todas usen la misma receta del PSI y dejando fuera del primer gráfico a la que no; (c) frontera sobre las cifras puntuales y el PSI de cada corrida, sin prueba | **(a)**: medido (§0.4-2, §0.4-3), sobre cifras puntuales una versión que pasa la validación queda «superada» por una diferencia de p = 0,71, y la no pareada no ve una caída real de 0,025 (p = 0,39 contra < 0,001); y con la receta propia el mismo puntaje da PSI 10,50 o 0 según los tramos (pasada 3), mientras que el común reproduce exacto el publicado con la receta de fábrica. (b) saca de la comparación lo que (a) puede medir. Exige guardar el puntaje de la muestra de evaluación y el PSI común en el resumen (§12-2) |
| 12-8 | IFRS 9 (ampliada por la pasada 3) | (a) **en la misma enmienda y las mismas capas**: ECL, exposición, conteo y cobertura por etapa, diferencias contra la referencia, sin gráficos; los montos se restan sólo con la misma unidad —por construcción (misma cartera y columnas de monto) o por declaración (la misma moneda)—, y si no se muestran por separado y se compara la cobertura (§3.7, D-MON); (b) después, aparte | **(a)**: es una tabla sobre el mismo mecanismo (§0.3: la diferencia de 4,6 % del horizonte está toda en Stage 2), y «cambios chicos, juntos» (RUNBOOK §12.3); la regla de la unidad respeta D-MON sin perder el caso típico (las tres provisiones de §0.3 no declaran moneda y se restan) |
| 12-9 | Capas y releases | (a) **A** —el resumen comparable en cada corrida, el motor, `bayesrisk.Comparison`, la sección y el resumen; experimental— en la **2.15.0**; **B** —pantalla, informe con su capítulo y los dos gráficos, Excel; estable— en la **2.16.0**; (b) A y B juntas | **(a)**: como H5 y H4; A deja que toda corrida hecha con la 2.15.0 ya sea comparable cuando llegue la pantalla |

**Respuestas de Cami (2026-10-14, S48, interactivas): la recomendación en las nueve.** Vigente:
D-CMP-1 (§12-1) una corrida de comparación propia —`bayesrisk.Comparison`, la sección `comparison`
con su única hoja `runs` y un trabajo nuevo en la pantalla, sin `data`—; D-CMP-2 (§12-2) cada
corrida terminada de scorecard o IFRS 9 deja su resumen comparable (`comparable.json`, §6.1) en su
`run_dir` y en `runs/<id>/` —agregados, la huella computacional del modelo campo por campo con su
gate y el puntaje de la muestra de evaluación en orden canónico, sin identificadores ni pickle; lo
que la corrida no tiene, en nulo; nunca la hace fallar—, y la comparación no abre carpetas con
`Study.load`; D-CMP-3 (§12-3) el índice de concentración del BCE, `1 + ln(HHI)/ln(K)`, por número
de operaciones y sin umbral; D-CMP-4 (§12-4) sin escala maestra, índice «No evaluable» con su
razón y fuera del segundo gráfico; D-CMP-5 (§12-5) comparar y avisar con los tres niveles de §3.3,
sin bloquear nunca; D-CMP-6 (§12-6) la comparación no elige: la institución registra su elección
con motivo (`choose`, extensión de D-DEC atada a la huella del resumen elegido); D-CMP-7 (§12-7)
la prueba de DeLong pareada sólo con la misma muestra evaluada, empate con p ≥ 0,05, la frontera
como núcleo de la relación y la estabilidad por banda de un PSI común con la receta de fábrica para
todas; D-CMP-8 (§12-8) IFRS 9 en la misma enmienda y las mismas capas, con los montos restados
sólo en la misma unidad (§3.7); D-CMP-9 (§12-9) capa A → 2.15.0 experimental y capa B → 2.16.0
estable.

## 13. Simplicidad (SDD-31)

- **Entrada mínima:** las corridas, en orden. Se infieren y se declaran: la referencia (la primera),
  la muestra de evaluación de cada una, la comparabilidad, los modelos repetidos y la prueba que
  corresponde.
- **Qué NO se configura:** §5.2.
- **Esenciales:** `runs` (1 ≤ 6); sin «Avanzado».
- **Presupuesto de perillas:** 1 hoja nueva (`comparison.runs`), la entrada de la institución; cero
  umbrales (el corte 0,05 y las bandas del PSI son los que la librería ya usa).
- **Resumen por etapa:** «Comparación»: la lectura de §3.6 (3–8 líneas), la tabla de modelos como
  tabla de decisión y las variables (o la provisión) como tabla adicional. Admite una decisión humana:
  la elección con su motivo (`choose`).
- **Notebook mínimo:** 3 líneas de usuario para comparar (`import`, `Comparison(...)`, `run()`); la
  guía arma antes una alternativa al scorecard de su ejemplo (2 líneas más).
- **Las cinco cifras (D-SIM-11)** —líneas del ejemplo · campos visibles de la sección · perillas ·
  segundos al primer resultado · conceptos—: **antes**, la comparación de N corridas no existe
  (medirla a mano son ~290 líneas de código propio, `medir_h2b.py` y `medir_h2b_delong.py`);
  **objetivo**, 3 · 1 · 1 · ≈ 1 s · 3 (corrida guardada, referencia, empate). Las del scorecard
  (15 · 37 · 414 · ≈ 1 s · 5) no cambian: el resumen comparable no agrega nada que configurar.

## 14. Lo que el código precisó (capa A)

Implementada en S49 (2026-10-14) sobre `af6c06a` + el arreglo de `Study.load` (`4711693`). Nada de
lo que sigue cambia una decisión de §12: son precisiones medidas al programar, con su evidencia en
el repo privado (`evidencia/s49/`: `humo_comparacion.py`, `humo_puerta.py`, `humo_ifrs9.py`,
`medir_oraculo_s49.py` y `salidas/`).

1. **Dónde se arma el resumen.** Al cierre de `Study.run`, después de marcar la corrida `done` —la
   tarjeta sólo se congela de una corrida terminada— y antes de `run_end`, con el registro de
   auditoría todavía abierto: un fallo inesperado se declara (`resumen_comparable_no_disponible`,
   con su causa) y la corrida sigue terminada (D-VIS). Después de `run_end` no se puede: el sink de
   MLflow cierra ahí y SDD-01 §11 fija el orden. La corrida lo guarda en el `Study`; `bayesrisk.run`
   lo escribe en su `run_dir` y `runs.save` en `runs/<id>/`, sin volver a armarlo. Costo medido en
   `consumo_comportamiento`: 0,29 s para congelar la tarjeta y 0,19 s para el PSI común, sobre
   corridas de 7–10 s. Un objeto vivo (`Scorecard`, `Ecl`, `Study`) usa el que armó su corrida o lo
   arma igual: `created_at` es el del lineage, así que el resumen es determinista y el del objeto
   vivo, el de `bayesrisk.run` y el de `runs.save` son el mismo byte a byte (test).
2. **El riesgo de la prueba pareada.** `evaluation_scores` guarda `risk`, el valor con que
   `performance` ordenó al calcular su AUC —la PD calibrada de fábrica, o el puntaje con su
   orientación si la corrida evalúa el puntaje—, con su `basis`; `performance` expone esa misma
   cadena (`performance.step.riesgo_evaluado`, sin una segunda regla) y el AUC calculado sobre esos
   valores es el publicado, exacto (test). Por eso los p-valores del oráculo no son los de §0.3, que
   S47 midió sobre el puntaje entero, con más empates: `tramos_4` 0,656 (0,83 en §0.3), `sin_mejor`
   0,717 (0,71) e `iv_005` < 0,001 (igual). Las conclusiones —dos empates y una caída real— no
   cambian.
3. **La huella de la cartera** es la de `("data", "special").frame`: la cartera validada y con sus
   especiales enmascarados, antes de etiquetar y particionar, con el algoritmo de `data_hash`. En
   una corrida de cartera (IFRS 9) coincide con `data_hash`; si los datos llegaron ya preparados
   (puntajes externos inyectados), es nula con su razón.
4. **Lo que falta, con su razón.** Un campo que la corrida no tiene va en nulo y su razón en
   `missing` (`{campo: razón}`); cada campo se calcula aparte, así que uno que falla no tumba al
   resto, y el armado comprueba al final que el JSON es canónico (sin números no finitos) para que
   escribirlo no pueda fallar por su contenido.
5. **La huella computacional**, campo por campo, con las tablas de `comparison.comparable`. Salen,
   además de la procedencia de §3.3: `schema_version` y `format` (la misma tarjeta en otro esquema),
   `model.score_column` (el nombre de la columna de salida, no su valor), los campos de ajuste de la
   calibración (`target_pd`, `anchor_kind`, `fit_partition`, la tolerancia y los diagnósticos: su
   efecto ya está en el método y sus parámetros) y `master_scale.source` (formados o fijados). El
   gate ata las tablas, en los dos sentidos, a las claves que `FittedScorecardBundle` exige
   —extraídas a `_MANIFEST_KEYS` y `_MODEL_KEYS`, sin cambiar su validación—, a
   `_MASTER_SCALE_KEYS` y a los campos de `CalibrationParameters`; un campo sin clasificar deja la
   huella nula con su razón. Las dos copias de §0.3 (`sin_stepwise`, `corr_050`) tienen la huella de
   la base con otro `config_hash` (oráculo).
6. **El PSI común** se mide con `stability.step.compute_stability` sobre el mismo frame que leyó la
   etapa, con la receta de fábrica y sólo la comparación de evaluación; la receta común es una
   constante atada por test a los defaults de `StabilityConfig`.
7. **El motivo de una validación que no pasa** es la primera prueba decisiva y cuántas más («Hosmer-
   Lemeshow en Fuera de tiempo (OOT) y 7 pruebas más»): la lista entera de `otra_cartera` volvía
   ilegible la línea 6 de la lectura. Sale de la misma lectura del resumen final, en su forma breve.
8. **`choose(nombre, reason=...)`**, con el nombre de argumento de toda la librería (`reason`), no
   `motivo=` como escribió §4.1. Vuelve a comparar en el acto —milisegundos—, como dice §4.1. La
   acción `choose` entra a `DecisionEntry` (su `value` es `{"comparison.choice": huella}`) y el
   cotejo de D-DEC lee las huellas de los resúmenes de `comparison.runs`: la última elección
   reemplaza a las anteriores, y una cuya corrida ya no está queda `decision_sin_efecto`, con su
   aviso en el resumen («la corrida elegida ya no está entre las comparadas»).
9. **Los errores.** El dominio levanta `ComparisonDataError`; la puerta guiada, `ComparisonInputError`
   y `ComparisonRunError`, como `MonitoringInputError` frente a `MonitorInputError`.
10. **`("comparison", "variables")` es largo** (variable × modelo, con `included`), no ancho: con diez
    modelos el ancho tendría 60 columnas. El resumen lo pinta ancho —una columna por modelo con su
    signo e IV de Desarrollo—, y es lo que el informe y el Excel leerán en la capa B.
11. **La lectura**, medida con el motor sobre §0.3 (oráculo): el ejemplo de §3.6 decía «Comparten
    tres variables», y son **dos** (`sin_mejor` quita `ingreso_mensual`, que §0.3 contó «en todas»);
    la línea de la validación nombra a todos los que fallan (también `iv_005`); la de la frontera
    agrega, cuando la frontera tiene más de un modelo, quién queda superado («en discriminación y
    estabilidad queda superada iv_005»); un nombre de corrida se escribe tal cual, también al
    comienzo de la línea; y una alternativa sin prueba dice si es por otras operaciones o por otros
    datos.
12. **Holdout y partición al azar** (§8): el resumen no guarda la estrategia de partición, así que
    toda corrida evaluada en Holdout lleva la advertencia de que, si la muestra se separó al azar,
    su PSI no mide deriva en el tiempo.
13. **Las puertas en la capa A.** La guiada y la completa dan el mismo `config_hash`, las mismas
    huellas y los mismos artefactos (test); la de la pantalla es de la capa B, con el trabajo
    «Comparar modelos». La puerta guiada no declara `report` en la capa A: el capítulo es de la B.
    Y la sección no lleva todavía sus marcas de pantalla —`runs` esencial, su widget—: llegan con
    la pantalla y el espejo del front, como en la capa A del monitoreo.
14. **Nombres repetidos**: todos los de un nombre repetido llevan su posición en la lista
    («consumo (1)», «consumo (3)»), no sólo el segundo.
15. **IFRS 9**: `by_stage` suma por etapa las filas de cada cartera del escenario ponderado (`all`,
    el único que publica la provisión) y `total` va aparte; los escenarios salen de la ficha con su
    peso. El oráculo reproduce §0.3 al peso: −221.355 (−4,6 %), todo en Stage 2; −68.545, con
    +39.110 en Stage 1 y −107.655 en Stage 2.
16. **Sin prueba, las cifras.** Entre dos corridas sin la misma muestra evaluada (o con la prueba no
    evaluable) la frontera compara el AUC por su valor y lo declara: la tabla de pruebas dice
    `no_test` u `not_evaluable` con su razón y la lectura, «sin prueba».
17. **Las cinco cifras, después** (la línea base de §13): 3 líneas de usuario para comparar
    (`import`, `Comparison(...)`, `run()`), 1 campo visible de la sección, 1 perilla, 0,37 s para tres
    resúmenes desde `bayesrisk.run` y 3 conceptos. Las del scorecard no cambian.
