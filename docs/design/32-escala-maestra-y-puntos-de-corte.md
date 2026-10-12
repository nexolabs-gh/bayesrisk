# SDD-32 — Escala maestra y puntos de corte (`bayesrisk.master_scale`)

> **Estado: APROBADO por Cami el 2026-10-11** (S41, interactivo), con la recomendación de cada una
> de las nueve decisiones de §12: tramos que forman los datos; la PD del tramo desde su tasa
> observada llevada al ancla; un corte; una sección nacida ausente no entra a la identidad; la etapa
> corre por defecto; sin escala de la institución; capa A en la 2.11.0 y B en la 2.12.0 con la demo;
> los tramos invertidos se igualan con alerta; y la tarjeta respeta `clip` en todo bundle nuevo.
> Diseño sin código: **la capa A se programa en la sesión siguiente** (S42), con tests nacidos rojos,
> controles negativos y Codex sobre el código; cada release y la recaptura piden su OK aparte. Es el
> hito **H5** del ROADMAP, el segundo eslabón de la cadena del banco
> que Cami puso primero el 2026-10-07 (IFRS 9 firmable → **H5** → H4; H2b al final), y el «módulo
> propio» que la decisión 8-3 de [`_ENMIENDA-FLUJO-GUIADO-SCORECARD.md`](_ENMIENDA-FLUJO-GUIADO-SCORECARD.md)
> (Cami, 2026-09-18) separó del scorecard.
>
> **Corregida tras la pasada 1 de Codex** (tres high y cuatro medium, los siete reales; dos
> contractuales): la tarjeta usa los estados que el bundle ya publica (`"scored"`/`"not_scorable"`)
> (§4.3); el corte sigue la dirección del puntaje, con una sola regla para asignación, tabla, corte de
> la institución y bundle, y la aprobación crece al aprobar más tramos, no con el puntaje (§3.2,
> §3.5, §6.3); el suavizado puede invertir el orden de tramos chicos, y qué hacer es la decisión
> nueva §12-8 (contractual); las celdas con denominador cero quedan vacías y cada fila publica sus
> conteos (§3.5); una decisión sin efecto avisa como manda D-DEC-3, no falla (§4.2, §11); la garantía
> de identidad se precisa —hash y YAML iguales, resultados iguales por la proyección canónica, la
> procedencia real— (§5.3, §12-4, contractual); y la comparación de reglas de §12-1 se rehízo con la
> PD propuesta —el rojo que citaba era de la otra PD— y con el Gini que conserva cada escala (§0.3).
> Informe: `evidencia/s41/codex_p1_raw.txt`.
> **Pasada 2** (un high y tres medium, los cuatro reales; uno contractual): una sola regla de corte
> —`s ≥ c` al lado de puntaje mayor en las dos direcciones— y rótulos derivados de la tarjeta, porque
> `⌊c⌋` con dirección invertida y un corte entero aprobaba una solicitud que la asignación dejaba
> fuera (§3.2, §3.5, §4.2); el contraste en Desarrollo es un diagnóstico real cuando la PD se aparta
> de la tasa (igualación o ancla externa) y se alerta (§3.4); §12-4, §4.3 y §11 dicen la misma
> garantía de identidad, con `bundle_hash` como procedencia (contractual); y el oráculo de la PD es
> uno nuevo que calcula D-ESC-2, porque `medir_h5.py` asigna la PD descartada (§11). Informe:
> `evidencia/s41/codex_p2_raw.txt`.
> **Pasada 3, la última del tope declarado** (un high y un medium, reales): las entradas de la etapa
> se completan —la tabla y la ficha de la tarjeta para los rótulos, `calibration.parameters` para el
> ancla efectiva— (§2, §6.1, §3.3); y un **defecto preexistente** de la tarjeta —con límites de
> puntaje declarados y `clip=False`, la corrida no recorta y `apply` sí— se eleva a Cami como §12-9.
> Cada pasada encontró menos y más acotado (7 → 4 → 2); con esto se cierra la revisión del documento
> sin cuarta pasada, por el criterio declarado. Informe: `evidencia/s41/codex_p3_raw.txt`.
>
> **Base medida:** `main` = `e6bba24` (bayesrisk 2.10.0). Las cifras «después» se midieron **fuera
> del motor**, con las reglas exactas que propone este documento, sobre las corridas de la puerta
> guiada `bayesrisk.Scorecard` con sus defaults en cuatro carteras: dos del paquete y dos externas
> y reales (§0). Script y salidas, sólo agregados, en el repo privado `evidencia/s41/`
> (`medir_h5.py` y `salidas/h5_*.txt`). Datos externos fuera de los repos (`%TEMP%\nkr\s41\ext`,
> borrados al cierre; sus huellas en §0). La normativa citada se cotejó contra dos fuentes
> oficiales (§3.6).
>
> **No toca:** el binning, la selección, el modelo, la escala de puntos (`scorecard`), la
> calibración, `performance`, `stability`, `validation`, IFRS 9, CMF ni el arnés H9R. Sin la sección
> nueva, ninguna corrida, artefacto, YAML ni `config_hash` cambia (§5.3). **No autoriza** bump, tag,
> PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **SDD** | 32 |
| **Módulo** | `bayesrisk.master_scale` (dominio y etapa nuevos); toca `guided/scorecard.py` y `guided/summaries.py`, `scorecard/bundle.py` (`apply`), `core/config` (la sección), `core/decisions` (dos acciones), `report`, `ui/jobs.py` + `web/` (capa B) y `docs_site/` |
| **Fase** | F1 (el scorecard, en operación) |
| **Tanda de producción** | T9 (SDD-31: un módulo a la vez, con su §13) |
| **Estado** | Aprobado por Cami el 2026-10-11 (§12) |
| **Depende de** | SDD-09 (`scorecard`: el puntaje), SDD-10 (`calibration`: la PD calibrada), SDD-22 (`validation`: el contraste de Jeffreys por grado, reutilizado), SDD-31, FLUJO-GUIADO-SCORECARD (D-FLU), HL-Y-DECISIONES-EN-EL-YAML (D-DEC) |
| **Lo consumen** | La guía del scorecard, el trabajo `scorecard_pd` de la pantalla, el informe, el bundle de aplicación; H4 (monitoreo: la tasa de malos por tramo en el tiempo), H2b (comparar modelos), H8 (originación) |
| **Autor / Fecha** | Claude Code / 2026-10-11 |

## Recomendación ejecutiva

Una etapa nueva, **«Escala maestra»**, al final del scorecard, que corre sola y no pide nada:

1. **Tramos de puntaje que forman los datos** (D-ESC-1): monótonos, con al menos el 5 % de Desarrollo
   cada uno, tasas de malos de tramos vecinos distintas con p ≤ 0,05 y hasta diez. Medido: 5, 7, 6 y
   10 tramos en las cuatro carteras, monótonos fuera de Desarrollo salvo donde la población cambió de
   verdad (§0.3); sin la regla de separación, la cartera del paquete da diez tramos que **se invierten**
   en Holdout y OOT.
2. **La PD de cada tramo** (D-ESC-2): la tasa de malos observada del tramo en Desarrollo, llevada al
   ancla de la calibración —Basilea II §447 y el flujo del banco—. En las dos carteras reales ajusta
   mejor fuera de muestra que la media de la PD del modelo (SBA: error 1,08 frente a 1,87 puntos y
   ningún tramo rojo frente a uno); es la decisión metodológica de §12-2.
3. **Cada tramo en cada muestra y la tabla de puntos de corte** (D-ESC-3, D-ESC-4): por cada límite,
   cuánto se aprueba, la tasa de malos de los aprobados, **los malos que se evitan y los buenos que se
   rechazan** —el objetivo de la librería en dos cifras—; con solicitudes sin desenlace, también la
   aprobación sobre todas las solicitudes.
4. **Dos decisiones humanas, no perillas** (D-ESC-5): `set_grades` (los cortes de la institución) y
   `set_cutoff` (su puntaje de aprobación), con motivo, al trail y al YAML.
5. **Viaja con la tarjeta** (D-ESC-6): el bundle congela la escala y `apply` devuelve tramo, PD del
   tramo y decisión; la puerta guiada gana `apply` para puntuar solicitudes nuevas, que hoy no tiene.
6. **Sin la sección, nada se mueve** (D-ESC-7): hoy una sección vacía entra al `config_hash` y al YAML
   de toda corrida; la regla nueva la deja fuera mientras no esté declarada.

Cero perillas además de las dos decisiones; esenciales 2; el notebook mínimo no cambia (15 líneas,
5 conceptos). Capa A (motor, puerta guiada, tarjeta, resumen, guía) → 2.11.0; capa B (pantalla,
informe, Excel; estable) → 2.12.0. Nueve decisiones para Cami en §12.

## 0. El estado, medido

### 0.1 Lo que hay hoy (sobre `e6bba24`)

Censo de `src/bayesrisk`, `web/src` y `docs/` (lectura, con fan-out):

| Pieza | Dónde | Lo que hace | Lo que le falta para operar la tarjeta |
|---|---|---|---|
| Tabla de deciles | `("performance", "performance_table")` | Cuantiles iguales de riesgo, **recalculados en cada muestra**; tasa de malos, PD media, KS por decil | Los cortes no son fijos entre muestras ni monótonos por construcción; no es una escala |
| Corte del KS | `("performance", "discriminant_metrics")` | Un corte por muestra, en la escala de riesgo (`ks_cutoff_score` es `None` con la fuente de fábrica) | No es una política: maximiza una distancia, no dice qué se aprueba |
| PSI por tramo de puntaje | `("stability", "psi_table")` | Cuantiles fijados en Desarrollo | Sin malos ni tasa de malos |
| Contraste por grado | `validation`, `binomial_by_grade` | Jeffreys/binomial por grado con semáforo | El grado lo trae **el archivo del usuario** (`grade_col`); apagado en la pantalla y en el preset F1 porque el panel no lo trae |
| Bandas de score | `provisioning_internal` (`score_band`, experimental) | Cuantiles de PD por cartera para provisionar | Sin monotonía, sin PD por tramo para operar |
| La tarjeta | `FittedScorecardBundle` + `bayesrisk.apply` | Puntaje, PD cruda y calibrada por solicitud | Sin tramo, sin decisión; **ni la puerta guiada ni la guía** muestran cómo puntuar solicitudes nuevas |

**No existen:** tramos de puntaje con PD, tabla de cortes, tasa de aprobación, malos evitados y
buenos rechazados, ni nada de eso en el bundle, el resumen, el informe, la pantalla o el Excel. La
decisión 8-3 de FLUJO-GUIADO-SCORECARD (2026-09-18) lo dejó para este módulo.

### 0.2 Lo que necesita un banco chico para operar la tarjeta

Medido sobre el patrón del flujo de modelación que Cami operó en un banco (SDD-31 §0.3; se toma el
**patrón**, no el código ni sus parámetros): tras la tabla de rendimiento por deciles
(`tdr_paso_1`), el paso 2 agrupa el puntaje en **pocos tramos monótonos** —un binning óptimo del
puntaje contra el incumplimiento, con participación mínima y máxima por tramo, o con los cortes que
la institución fija a mano— y les asigna su PD; el entregable es una «calculadora»: **límite inferior
y superior del puntaje y PD de cada tramo**, que el sistema del banco aplica. Lo que el banco decide
con eso: el punto de corte (cuánto aprueba y con qué tasa de malos), y lo que lleva a su sistema:
la tabla de tramos. Las cuatro necesidades —tramos con límites en puntos, PD por tramo, la tabla
para elegir el corte y la tarjeta que lo aplica— son el alcance de este SDD; el seguimiento mensual
de esos tramos es H4.

### 0.3 Medido con las reglas de este documento

`bayesrisk.Scorecard` con sus defaults sobre cuatro carteras; los tramos se formaron fuera del motor
con OptBinning sobre el puntaje y el desenlace de Desarrollo (`medir_h5.py`, tres reglas: **A** la
propuesta; **B** la del banco —hasta 5 tramos, entre 10 % y 70 % cada uno—; **C** la A sin la
separación). Monotonía sólo sobre tramos con al menos 30 operaciones en la muestra.

| Cartera | Operaciones (Des. / Hold. / OOT; sin desenlace) | Tasa de malos | Tramos A · B · C | Tasa de malos por tramo en Des. (A) | Monotonía fuera de Des. (A) | Tramo mayor · HHI (Des.) | Segundos |
|---|---|---|---|---|---|---|---|
| `consumo_comportamiento` (paquete) | 3.961 / 1.031 / 1.008 | 23,3 % | **5** · 5 · 10 | 4,7 % → 53,6 % | sí y sí (C: **no** y **no**) | 35,3 % · 0,244 | 0,13 |
| `consumo_drift` (paquete) | 3.955 / 1.000 / 1.045 | 33,2 % (OOT 48,5 %) | **7** · 5 · 10 | 4,9 % → 78,1 % | sí; OOT sí (la única inversión, un tramo de 6) | 23,9 % · 0,171 | 0,04 |
| German Credit (UCI, real) | 802 / 198 (azar) | 28,9 % | **6** · 5 · 8 | 2,5 % → 79,6 % | sí | 26,4 % · 0,195 | 0,04 |
| SBA 7(a) FY2000–2009 (real) | 32.770 / 8.384 / 2.620; 6.225 | 24,1 % (OOT 14,7 %) | **10** · 5 · 10 | 1,5 % → 76,0 % | Holdout sí; OOT **no** (tramos 3–5 en 8,0 %, 7,3 %, 6,3 %) | 18,0 % · 0,117 | 0,06 |

Lo que dicen:

- **La separación hace el trabajo**: sin ella (C), el paquete forma diez tramos cuyas tasas se
  invierten en Holdout y OOT; con ella, cinco que no se invierten. En la SBA, con 32.770 operaciones,
  todas las separaciones son significativas y **manda el tope** de diez.
- **La escala aguanta un cambio de población**: en `consumo_drift` la tasa de OOT sube de 33 % a
  48,5 %, pero cada tramo conserva su PD (Jeffreys sin rojos): lo que cambió es la composición —los
  tramos 6 y 7 pasan del 19,7 % al 48,3 % de la muestra— y la tabla de cortes lo muestra (con el mismo
  corte, la aprobación cae del 82 % al 51,7 %).
- **Una inversión real se ve**: la OOT de la SBA (préstamos del FY2009, tras la crisis) tiene tasas
  planas en los tramos 3–5; es la alerta que el resumen tiene que dar.
- **La PD del tramo** (§12-2): con la media de la PD calibrada, la SBA deja dos tramos rojos en
  Desarrollo (el 7: 43,0 % observado frente a 38,8 %) y uno en Holdout; con la tasa observada del
  tramo, ninguno. Error absoluto medio fuera de Desarrollo, ponderado (puntos): SBA Holdout 1,08
  (tasa observada) frente a 1,87 (media del modelo); German 4,14 frente a 4,68; en las dos del
  paquete, que se generan con una logística, la media del modelo gana por poco (1,71 frente a 1,93 y
  4,09 frente a 4,85) (`pd_tramo_alternativas.py`; la tasa sin suavizar ni `δ`, que la mueven menos
  de 0,011 en logit).
- **Lo que conserva cada regla** (con la PD propuesta, `reglas_con_pd_propuesta.py`): el Gini de la
  escala —el tramo como predictor, con empates dentro del tramo— frente al de la regla del banco
  (B): Holdout SBA 0,717 frente a 0,700, German 0,647 frente a 0,638, `consumo_drift` 0,358 frente a
  0,350 y `consumo_comportamiento` 0,363 frente a 0,369; OOT, A por encima en las tres que la tienen
  (SBA 0,470 frente a 0,457; `consumo_drift` 0,401 frente a 0,369; `consumo_comportamiento` 0,310
  frente a 0,303). Con la PD propuesta ninguna de las tres reglas deja tramos rojos en Desarrollo ni
  en Holdout; C gana algo de Gini con más tramos, al precio de invertirse fuera de Desarrollo.
- **La concentración** queda bajo el 37 % en el tramo mayor y el HHI entre 0,12 y 0,25 en
  Desarrollo, sin regla que la limite más allá de la participación mínima.
- **Rápido**: formar la escala toma 0,04–0,13 s; la corrida guiada, 9–21 s.

Una fila de la tabla de cortes, para leerla (SBA, Holdout): aprobar desde 538 puntos (tramos 1–4)
aprueba el 58,5 %, con 6,1 % de malos entre los aprobados, evita el 85,4 % de los malos y rechaza el
27,2 % de los buenos; desde 507 (tramos 1–6), aprueba el 71,1 % con 9,4 % de malos, evita el 72,9 %
y rechaza el 14,6 %. Las 6.225 solicitudes sin desenlace caen sobre todo en los tramos de menor
riesgo (el 54,4 % en los tramos 1–3, frente al 44,9 % de las que tienen desenlace en Desarrollo).

Huellas de los datos externos: German `german.data` sha256 `b21f3d81…` (el de S20); SBA
`FOIA_7a_FY2000_FY2009_asof_260630.csv` sha256 `66674e18…` (el de S21), muestra de 49.999 filas
con `armar_dataset_sba.py`; OOT desde el 2008-10-01.

### 0.4 Dos hallazgos de la medición

- **Una sección nueva movería toda identidad.** `config_hash` y el YAML serializan todas las
  secciones de dominio, también las vacías: el preset F1 lleva trece en `null` (`explain`, `forward`,
  `markov`, …). Una sección `master_scale` con `None` de fábrica cambiaría el hash de todo config
  existente. D-ESC-7 (§5.3) lo evita.
- **La puerta guiada no puntúa solicitudes nuevas.** El bundle y `bayesrisk.apply` existen, pero ni
  `Scorecard` ni la guía los muestran: quien construyó su tarjeta con la puerta guiada no tiene cómo
  aplicarla. Sin eso, una escala «exportable a la tarjeta» no llega a operar (D-ESC-6).

## 1. Propósito y responsabilidad

**Qué resuelve.** Que el modelador de un banco chico pase de «tengo un scorecard validado» a
«opero la tarjeta»: en qué **tramos de riesgo** cae cada solicitud, **qué PD** tiene cada tramo,
**dónde pongo el corte** de aprobación sabiendo cuántos malos evito y cuántos buenos rechazo, y
cómo llevo todo eso a su sistema. Hoy el scorecard termina en un puntaje por operación y una tabla
de deciles que se recalcula en cada muestra; el paso que el flujo del banco llamaba `tdr_paso_2`
—tramos de puntaje monótonos y la PD de cada uno, en una «calculadora» con los límites— no existe
(§0.1).

**Sí hace.**

- Forma, sobre la muestra de Desarrollo, **tramos de puntaje monótonos**: contiguos, ordenados de
  menor a mayor riesgo, con una participación mínima y tasas de malos de tramos vecinos
  estadísticamente distintas (§3.2). El número de tramos sale de los datos; la institución puede
  fijar sus cortes con motivo (decisión humana, §4.2).
- Asigna a cada tramo **su PD**: su tasa de malos observada en Desarrollo, llevada al ancla de la
  calibración (§3.3).
- Mide cada tramo **en cada muestra** —participación, tasa de malos observada frente a la PD del
  tramo con el contraste de Jeffreys que ya usa la validación, monotonía— y la **concentración** de
  la escala (§3.4).
- Publica la **tabla de puntos de corte**: por cada límite entre tramos y por muestra, qué
  proporción se aprueba, la tasa de malos de los aprobados, qué proporción de los malos se evita y
  qué proporción de los buenos se rechaza; también sobre las solicitudes que quedaron fuera del
  ajuste, como las que aún no tienen desenlace (población TTD) (§3.5). La institución puede declarar su corte con motivo
  (§4.2).
- **Viaja con la tarjeta**: el bundle de aplicación congela los tramos, sus PD y el corte, y
  `apply` devuelve por solicitud el tramo, su PD y —con corte— la decisión (§4.3).

**No hace** (y quién lo hace):

- No calibra ni reestima nada: el puntaje es el de `scorecard` y la PD la de `calibration`
  (SDD-09, SDD-10). Un cambio de ancla se hace en la calibración y la escala lo hereda.
- No sigue los tramos en el tiempo con datos nuevos (migraciones, PSI por tramo, historia por
  período): eso es el monitoreo, **H4**.
- No corrige el sesgo de la muestra aprobada (inferencia de rechazados): **H8**. La tabla de cortes
  de una cartera aprobada mide la tasa de malos de quien ya pasó la política anterior, y lo dice
  (§8).
- No pone precio ni mide rentabilidad por tramo: exige márgenes, costos y LGD de la institución; no
  hay default que funcione (§12, candidatos).
- No impone una escala maestra común a varios modelos (grados con límites de PD fijos para toda la
  institución): §12-6.
- No forma tramos sobre una PD sin puntaje (un modelo de ML retador o una PD externa): la escala de
  la v1 vive donde hay tarjeta. Cuando H6 traiga un retador, la misma regla se aplica sobre su PD
  (§12, candidatos).
- No exporta la tarjeta a SQL: candidato transversal del ROADMAP.
- No conecta los tramos a `validation` (su contraste por grado sigue leyendo la columna de grado
  del archivo): la escala publica su propio contraste por tramo con la misma función (§3.4); unir
  las dos fuentes es de H4.

## 2. Contexto y ubicación en la arquitectura

- **Un dominio y una etapa nuevos**, `master_scale` («Escala maestra»), en el pipeline del
  scorecard **después de `validation` y antes de `report`**. Consume lo que ya publican
  `("scorecard", "score")`, `("scorecard", "out_of_model_score")`, `("scorecard", "scorecard")` y
  `("scorecard", "card")` (los puntos posibles y los límites de la tarjeta, para los rótulos de
  §3.2), `("calibration", "calibrated_pd_frame")` y `("calibration", "parameters")` (el ancla efectiva
  de §3.3), todos declarados en su `requires` y exigidos antes de correr; no consume ni modifica nada
  más (CT-1, CT-2). Va al
  final porque es la capa operativa del modelo ya validado y porque así sólo el libro de
  decisiones cambia de número en el Excel (§6.4).
- **Las tres puertas** (SDD-31 D-SIM-1): la guiada (`Scorecard` la corre por defecto, §4.1), la
  completa (la sección `master_scale` del config, §5) y la pantalla (la sección en los trabajos
  `scorecard_pd` y `pd_y_lgd`, capa B, §11).
- **La tarjeta**: `FittedScorecardBundle.from_study` ya congela binning, coeficientes, escala de
  puntos y calibración; gana el bloque de la escala (§4.3).
- **Lo que reutiliza en vez de reimplementar:** el binning monótono óptimo que la librería ya usa
  para las variables (OptBinning, Apache-2.0, en `binning`) para formar los tramos;
  `validation.calibration_tests.binomial_by_grade` para el contraste por tramo; `core/tramos.py`
  para rotular los límites; `report.exports` para el Excel; el mecanismo de decisiones con motivo
  de D-DEC para los cortes de la institución.

## 3. Conceptos y fundamentos

### 3.1 Notación

Por operación `i`: el puntaje `sᵢ` de `("scorecard", "score")` —entero con el redondeo de fábrica
`nearest_integer`—, la PD calibrada `pᵢ` de `("calibration", "calibrated_pd_frame")`, el desenlace
`yᵢ ∈ {0, 1}` y la muestra `m` (Desarrollo, Holdout, OOT). `D` son las operaciones de Desarrollo con
desenlace. Una **escala** son `K − 1` cortes `c₁ < … < c_{K−1}` sobre el puntaje, que forman `K`
tramos contiguos. El **tramo 1 es el de menor riesgo**: con la dirección de fábrica («más puntaje,
menos riesgo», `scorecard.score_direction`), el tramo 1 es `s ≥ c_{K−1}` y el tramo `K` es
`s < c₁`; con la dirección invertida, al revés. La dirección la declara quien fabrica el puntaje
(D-INV-1); la escala la lee, no la configura.

### 3.2 Cómo se forman los tramos (D-ESC-1)

Sobre `D`, con el binning monótono óptimo que la librería ya usa para las variables (OptBinning,
con su solver y su pre-segmentación de fábrica: CART en hasta 20 grupos de al menos 5 %), con
cuatro restricciones **constantes**:

1. **Monotonía**: la tasa de malos sube del tramo 1 al `K` (el sentido sale de la dirección del
   puntaje).
2. **Participación mínima**: cada tramo tiene al menos el **5 %** de `D` —la misma cota que usa la
   puerta guiada para los tramos de cada variable (`min_bin_size=0.05`)—. Basilea II §409 pide que
   cada grupo tenga operaciones suficientes para cuantificar y validar su pérdida.
3. **Separación**: las tasas de malos de dos tramos vecinos son distintas con **p ≤ 0,05** (prueba
   Z de OptBinning entre tramos consecutivos). Es la «diferenciación significativa del riesgo» de
   Basilea II §410 y de 12 CFR 217.122(b)(1)(i): dos tramos que no se distinguen son uno.
4. **Tope**: hasta **10** tramos.

El número de tramos **no se configura**: es el que los datos sostienen con esas cuatro reglas
(§0.3 mide cuántos salen). Si la institución ya opera con sus cortes —la `lista_ptos_corte` del
flujo del banco—, los fija con motivo (§4.2) y la escala usa esos.

**Una sola regla de corte, exacta** (la lección de D-CPY-3, `_ENMIENDA-COPY-PRUEBA-REAL-SBA.md`
§11-2). Todo corte `c` —los que forma OptBinning (puntos medios entre puntajes observados, en
float32), los de la institución (`set_grades`) y el de aprobación (`set_cutoff`)— separa con **el
mismo predicado en las dos direcciones**: `s ≥ c` va al lado de puntaje mayor y `s < c` al de
puntaje menor, como ya hace OptBinning. La dirección del puntaje sólo dice cuál de los dos lados es
el de menor riesgo y, por tanto, el que se aprueba. La asignación, la tabla de cortes, el corte de
la institución y el bundle guardan y comparan `c` exacto, nunca un valor redondeado:

| Dirección del puntaje | Lado de menor riesgo (y aprobado) de `c` | Rótulo cuando la tarjeta sólo produce enteros | Rótulo en otro caso |
|---|---|---|---|
| `higher_is_lower_risk` (fábrica) | `s ≥ c` | «desde ⌈c⌉ puntos» | «desde c puntos» |
| `higher_is_higher_risk` | `s < c` | «hasta ⌈c⌉ − 1 puntos» | «menos de c puntos» |

«La tarjeta sólo produce enteros» se lee de la propia tarjeta, no de los datos ni sólo de
`rounding_method`: todos sus puntos por atributo, sus ajustes manuales (`point_overrides`) y sus
límites de recorte son enteros. Entonces todo puntaje posible es entero y `⌈c⌉` (o `⌈c⌉ − 1`) separa
exactamente los mismos puntajes que `c`, sea `c` un punto medio `x,5` (exacto en float32) o un
entero (un punto medio entre puntajes no consecutivos, o un corte de la institución); si no, el
rótulo dice `c` con la representación decimal más corta que vuelve al mismo `float`. Para la
institución, «aprobar desde 541» con la dirección de fábrica es `set_cutoff(541)`; con la invertida,
`set_cutoff(541)` aprueba los puntajes **menores** que 541 («hasta 540»). Los rótulos salen de
`core/tramos.py` y viajan por posición del tramo, no por su texto. Un test fija, en las dos
direcciones, los vecinos del borde —el corte, el entero anterior y el siguiente, y `nextafter` a
cada lado— para cortes `x,5` y enteros, y comprueba que «aprobar los tramos 1…k» y aplicar el corte
publicado seleccionan las mismas operaciones.

### 3.3 La PD de cada tramo (D-ESC-2; §12-2)

**Propuesta: la tasa de malos observada del tramo en Desarrollo, llevada al ancla de la
calibración.** Con `n_g` operaciones de `D` en el tramo y `d_g` malos:

```
r_g  = (d_g + ½) / (n_g + 1)                       la tasa del tramo (media de Jeffreys: nunca 0 ni 1)
PD_g = logit⁻¹( logit(r_g) + δ )                    con δ único tal que  Σ_g (n_g/|D|) · PD_g = ancla
```

El ancla es la tendencia central que fijó la calibración (SDD-10), leída de
`("calibration", "parameters")`: con la de fábrica,
`development_observed`, la tasa de malos de Desarrollo, y `δ` sólo corrige el suavizado (≈ 0); con un
ancla de negocio o regulatoria, ésa, y `δ` traslada toda la escala como el `intercept_offset` traslada
cada operación. Por qué esta regla:

- **Es la que pide la norma y la que usa el banco**: Basilea II §447 —la PD de un grado es un
  promedio de largo plazo de las tasas de incumplimiento **de los deudores del grado**— y la
  «calculadora» del flujo del banco (PD por tramo desde su tasa). El largo plazo lo aporta la
  calibración; la escala lo conserva.
- **Ajusta mejor fuera de muestra en las dos carteras reales** (§0.3): una logística suele estar
  descalibrada en las colas, y la PD del grado tiene que corregir eso, no heredarlo.
- **Es monótona con los tramos de D-ESC-1, medido**: la tasa de Desarrollo es monótona y vecinos
  distintos con p ≤ 0,05, el desplazamiento común `δ` conserva el orden, y en las cuatro carteras y
  las tres reglas de §0.3 las PD resultan estrictamente crecientes (`δ` entre −0,011 y −0,0002 en
  logit). **Pero el suavizado no conserva el orden en general**: con tramos de tamaños muy distintos
  y tasas cercanas a cero puede invertirlo (contraejemplo de la revisión: `(n, d) = (30, 0)` y
  `(300, 1)` tienen tasas 0 % y 0,33 % y suavizadas 1,61 % y 0,50 %), y unos cortes de la institución
  pueden además invertir la propia tasa observada. Qué hacer entonces es una decisión de Cami
  (§12-8); la propuesta: **igualar** —los tramos vecinos que invierten comparten la PD que les da la
  regresión isotónica (el algoritmo PAVA, ponderado por `n_g`) sobre las tasas suavizadas, antes de
  `δ`—, con la alerta «los tramos 3 y 4 no se distinguen en Desarrollo: comparten PD; conviene
  unirlos». La PD queda no decreciente y reconciliada con el ancla, y la corrida no se detiene.

**Alternativa (§12-2 (b)): la media de la PD calibrada de las operaciones del tramo.** Hereda el
ancla y es monótona siempre, y es la que mejor ajusta en las dos carteras sintéticas del paquete
—generadas con una logística—; pero arrastra la descalibración local del modelo: en la SBA deja dos
tramos rojos en Desarrollo y uno en Holdout. Descartada también: la PD del punto medio del tramo
(arbitraria en los tramos extremos, que son abiertos).

La PD de cada operación (`pd_calibrated`) no cambia: la escala publica las dos —la de la operación
y la de su tramo— y la guía dice cuál usa cada cosa (la del tramo, para operar la política; la de la
operación, para lo que ya la consume, como la provisión con `Ecl(pd=…)`).

### 3.4 Cada tramo en cada muestra (D-ESC-3)

Por tramo `g` y muestra `m`, sobre las operaciones con desenlace: operaciones `n_{g,m}`,
participación `n_{g,m} / N_m`, malos `d_{g,m}` y tasa de malos `d_{g,m} / n_{g,m}`; la PD del tramo
`PD_g`; y el **contraste de Jeffreys** de esa PD —el de la validación, `binomial_by_grade`, con la
forma literal del BCE: `p = Beta(PD_g; d + ½, n − d + ½)`, unilateral, la hipótesis nula «la PD del
tramo no subestima»— con el semáforo de la validación (verde `p ≥ 0,05`, ámbar `0,01 ≤ p < 0,05`,
rojo `p < 0,01`; D-VAL-5/15). **En Desarrollo** el contraste se publica como diagnóstico dentro de
muestra: con los tramos formados y el ancla observada casi no se mueve (la PD sale de esa tasa), pero
**no es trivial** cuando la PD se aparta de la tasa del tramo —tramos igualados por §12-8 o un ancla
de negocio o regulatoria por debajo de la tasa observada—: con dos tramos de la institución `(n, d)
= (1000, 500)` y `(1000, 100)`, la igualación y el ancla dejan 30 % en los dos y el primero sale
rojo. Un tramo rojo en Desarrollo se alerta en «Qué revisar» («la PD final subestima el tramo 1 en
Desarrollo: lo causa la igualación o el ancla»). **Holdout y OOT** son la evaluación independiente.
Un tramo con menos de 30 operaciones en la muestra (el mínimo de la validación,
`min_rows_per_group`) queda «No evaluable».

Por muestra, además: si la tasa de malos sigue el orden de los tramos, **sobre los tramos
evaluables** (la misma alerta que el binning da por variable, D-FLU-6; medido: sin esa condición,
un tramo de 6 operaciones de la OOT de `consumo_drift` daba una inversión espuria), y la
**concentración**: el índice de Herfindahl `HHI_m = Σ_g (n_{g,m} / N_m)²` y la participación del
tramo mayor (Basilea II §403 y §409, «sin concentraciones excesivas»). La concentración **se publica
y no se alerta**: ninguna de las dos fuentes da un umbral, la participación mínima y el tope ya la
acotan al formar, y un umbral propio sería una perilla sin evidencia (medido: el tramo mayor entre
18 % y 37 % en Desarrollo).

### 3.5 La tabla de puntos de corte (D-ESC-4)

Aprobar los tramos `1…k` es aprobar el lado de menor riesgo del corte `c` entre `k` y `k + 1`, con
la regla única de §3.2. Por cada `k = 1…K` y cada muestra `m`
—«Aprobados» sobre todas las operaciones puntuadas de la muestra; el resto, sobre las que tienen
desenlace—:

| Columna | Fórmula | Lo que responde |
|---|---|---|
| Puntaje mínimo | el corte inferior del tramo `k` | «aprobar desde N puntos» |
| Aprobados | `Σ_{g≤k} n_g / N` | cuánto se aprueba |
| Tasa de malos de los aprobados | `Σ_{g≤k} d_g / Σ_{g≤k} n_g` | el riesgo que se acepta |
| PD esperada de los aprobados | `Σ_{g≤k} n_g · PD_g / Σ_{g≤k} n_g` | lo mismo según la escala |
| Malos evitados | `Σ_{g>k} d_g / Σ_g d_g` | **créditos que no debieron darse** y no se dan |
| Buenos rechazados | `Σ_{g>k} (n_g − d_g) / Σ_g (n_g − d_g)` | **créditos negados a quien sí podía pagar** |

Las dos últimas columnas son el objetivo de la librería en dos cifras («menos créditos que no
debieron darse, menos negados a quien sí podía pagar», `ESPECIFICACIONES.md` §1.1): cada corte las
pone una frente a la otra, y el comité elige sabiendo lo que cuesta.

**Las operaciones fuera del ajuste** —las solicitudes sin desenlace de D-TTD y las que una regla
excluyó, que el scorecard ya puntúa en `("scorecard", "out_of_model_score")`, partición «Fuera del
ajuste» de D-CPY-1— entran como una muestra más: «Aprobados» dice qué proporción de ellas aprueba el
corte, que es la aprobación que el banco vería sobre las solicitudes que hoy no tienen desenlace; las
demás columnas se calculan sólo sobre las que tienen desenlace, con su denominador declarado, y
quedan en «—» si ninguna lo tiene (la regla de D-CPY-1). En las tres muestras del ajuste todas las
operaciones tienen desenlace y las dos bases coinciden.

**El corte de la institución** (§4.2), si lo declara, entra como una fila más con las mismas
columnas calculadas exactamente en su puntaje y con el mismo predicado —no tiene que coincidir con un
límite de tramo—.

**Denominadores.** Cada fila publica sus conteos —operaciones puntuadas, con desenlace, aprobadas y
aprobadas con desenlace, malos y buenos de la muestra— y una columna cuyo denominador es cero queda
vacía («—»), nunca en cero: la tasa de malos y la PD esperada de los aprobados sin aprobados con
desenlace (un corte que rechaza todo, o que sólo aprueba solicitudes sin desenlace); los malos
evitados sin malos en la muestra; los buenos rechazados sin buenos. Un cero sólo se publica cuando
se midió.

### 3.6 Lo que dice la norma (cotejado contra dos fuentes oficiales)

- **Basilea II** (BCBS, *International Convergence of Capital Measurement and Capital Standards*,
  versión completa, junio 2006; PDF del BIS, sha256 `2543a00c…`, texto extraído con `pypdf`):
  §403, distribución significativa entre grados «sin concentraciones excesivas»; §404, **al menos
  siete grados** para deudores sin incumplimiento y uno para los incumplidos —en las carteras
  corporativa, soberana y bancaria del método IRB—; §409, para la cartera minorista, operaciones
  suficientes en cada grupo para cuantificar y validar, distribución significativa y ningún grupo
  con una concentración indebida; §410, criterios que resulten en una diferenciación significativa
  del riesgo; §447, la PD de un grado es un promedio de largo plazo de tasas de incumplimiento a un
  año; §285/§331, piso de 0,03 % para la PD corporativa y minorista bajo IRB.
- **Estados Unidos**, 12 CFR 217.122 (eCFR, Reserva Federal, métodos avanzados): (b)(1)(i), un
  sistema que diferencie el riesgo de forma «precisa, confiable y significativa»; (b)(2)(i), al menos
  siete grados para deudores mayoristas sin incumplimiento y uno para los incumplidos.

Lo que el módulo toma: la separación entre tramos (§410) y la participación mínima (§409) como
reglas de formación, y la concentración como medida publicada. **Lo que no impone:** los siete
grados (§404 rige el rating de deudores mayoristas bajo IRB, no el scorecard minorista de un banco
chico; el resumen dice cuántos tramos salieron y la guía cita la regla), ni el piso de 0,03 %
(regulatorio de capital, no de la escala). La normativa local no entra (D-JUR).

## 4. API pública (contrato)

### 4.1 La puerta guiada

`Scorecard(...)` no cambia de firma. `run()` corre la etapa «Escala maestra» al final, con su
resumen, y `results["master_scale"]` es su tabla de decisión (los tramos). `summary("master_scale")`
la muestra.

### 4.2 Las dos decisiones humanas (D-ESC-5)

```python
sc.set_grades([563, 541, 520, 498], reason="los cortes de la política vigente")
sc.set_cutoff(541, reason="apetito: tasa de malos de los aprobados bajo 4 %")
sc.resume()
```

- `set_grades(cuts, *, reason)`: fija los cortes de los tramos en puntos (en cualquier orden; se
  ordenan), escribe `master_scale.grade_edges` y la decisión con autor y motivo (D-SIM-6). Es el
  `set_bins` de la escala.
- `set_cutoff(score, *, reason)`: declara el corte de aprobación, escribe
  `master_scale.approval_cutoff`; se aprueba su lado de menor riesgo con la regla de §3.2 (con la
  dirección de fábrica, el puntaje mínimo: `s ≥ score`). El corte no tiene que ser un límite de
  tramo.
- Las dos van a la sección `decisions` del YAML (D-DEC) como acciones nuevas `set_grades` y
  `set_cutoff`, con su efecto en esas hojas, y el cotejo de D-DEC-3 las trata igual que a las demás
  (sin efecto: aviso y registro conservado, no error).

### 4.3 La tarjeta (D-ESC-6)

- `FittedScorecardBundle.from_study(study)` congela, si la corrida tiene escala, sus cortes, la PD
  de cada tramo, el corte de aprobación (si hay) y la dirección del puntaje. Sin escala, el bundle
  no gana ningún bloque y `apply` devuelve las mismas columnas y los mismos valores computacionales
  que hoy; la procedencia sigue siendo la real: el manifest y el `bundle_hash` de cada fila llevan,
  como siempre, la versión, el commit y la huella de distribución de la corrida que construyó el
  bundle, y cambian de una versión a otra.
- `apply(frame)` / `bayesrisk.apply(bundle, frame)` agregan `grade` (entero, 1 = menor riesgo),
  `grade_pd` y, con corte, `decision` (`"approve"` / `"reject"`): identificadores en inglés, como
  `scoring_status`; los rótulos en español van al Excel y a la pantalla. Una fila que no se puntúa
  (`scoring_status == "not_scorable"`; las puntuadas son `"scored"`, los dos valores que el bundle ya
  publica y que no cambian) no tiene tramo ni decisión.
- `Scorecard.apply(frame)` (nuevo en la puerta guiada): puntúa solicitudes nuevas con la tarjeta de
  su última corrida —el mismo `apply`—. Hoy la puerta guiada no tiene cómo puntuar archivos nuevos
  (el bundle existe pero no está en la guía): sin esto la escala no llega a operar la tarjeta.

### 4.4 La puerta completa

La sección `master_scale` del config (§5). Sin ella, la etapa no corre.

### 4.5 De punta a punta

```python
sc = Scorecard(data=datos, target="bad_flag", id="loan_id", cohort="cohorte",
               oot_cohorts=["2024Q2"], name="consumo_v01")
sc.run()                         # … la última etapa dice los tramos, su PD y los cortes
sc.set_cutoff(541, reason="tasa de malos de los aprobados bajo 4 % en OOT")
sc.resume()
nuevas = sc.apply(solicitudes)   # puntaje, tramo, PD del tramo y decisión por solicitud
```

## 5. Configuración

### 5.1 La sección `master_scale` (`MasterScaleConfig`)

| Hoja | Tipo | Default | Qué es |
|---|---|---|---|
| `grade_edges` | `tuple[float, ...] \| None` | `None` | Los cortes de la institución (decisión humana); `None` = formados por D-ESC-1 |
| `approval_cutoff` | `float \| None` | `None` | El puntaje mínimo de aprobación (decisión humana); `None` = sin decisión, sólo la tabla |

Validación: `grade_edges` con al menos un corte, finitos y distintos (se ordenan); `approval_cutoff`
finito. Un corte que deja un tramo sin operaciones de Desarrollo se rechaza al correr, con el tramo
y el rango del puntaje (§8). Ambas en el `config_hash` (son decisiones que cambian resultados).

### 5.2 Lo que NO se configura

Las cuatro reglas de formación (participación 5 %, separación p ≤ 0,05, monotonía, hasta 10
tramos), el método de formación, la regla de la PD del tramo, el contraste por tramo y su semáforo
(los de la validación), las columnas de la tabla de cortes, la medida de concentración, la
numeración de los tramos (1 = menor riesgo) y la base (el puntaje). §13 da la razón de cada una.

### 5.3 Una sección nueva no mueve ninguna identidad (D-ESC-7)

Medido sobre `e6bba24`: `config_hash` serializa **todas** las secciones de dominio, también las
vacías (`"markov": null`), y `dump_config` vuelca el YAML completo. Una sección nueva con `None` de
fábrica cambiaría el `config_hash` de **todo** config existente —también los de los usuarios, que
lo usan como identidad de su inventario— y el YAML de toda corrida. Regla propuesta: **una sección
de dominio nacida después de la 2.10.0 se serializa sólo cuando está declarada**. La garantía,
precisa: con `master_scale` ausente, (1) el `config_hash` y el YAML del config son los de la 2.10.0
byte a byte; (2) los resultados computacionales son iguales —la proyección canónica de los artefactos
de una corrida F1 del preset (`tests/unit/_proyeccion_canonica.py`), como en cada capa desde S17—;
y (3) la **procedencia sigue siendo la real**: el lineage y el manifest del bundle registran, como en
toda release, la versión, el commit y la huella de distribución de quien corrió, y por eso cambian
de una versión a otra. Es una regla de identidad (SDD-01 §5, D-HASH): la decide Cami (§12-4).
Alternativa descartada: aceptar que todo hash se mueva en un minor.

## 6. Contratos de datos

### 6.1 Entrada

`("scorecard", "score")` (puntaje, muestra, desenlace), `("calibration", "calibrated_pd_frame")`
(la PD calibrada, con el mismo índice), `("scorecard", "out_of_model_score")` (las operaciones fuera
del ajuste, opcional), `("scorecard", "scorecard")` y `("scorecard", "card")` (todos los puntos
posibles por atributo —también los de tramos que ninguna muestra trae—, los ajustes manuales y los
límites de recorte: de ahí sale si la tarjeta sólo produce enteros, §3.2) y
`("calibration", "parameters")` (el ancla efectiva: su fuente, su tipo y su valor; la media de
`pd_calibrated` sólo la aproxima dentro de `target_tolerance`, así que `δ` se resuelve contra el
valor publicado, §3.3). La dirección del puntaje, del config de `scorecard`. Sin alguno de los
obligatorios, la etapa no corre y dice cuál falta.

### 6.2 Salida (`("master_scale", clave)`)

| Clave | Contenido |
|---|---|
| `grades` | Una fila por tramo: `grade`, `score_min`, `score_max` (abierto en los extremos), `pd`, `n_development`, `share_development`, `bad_rate_development`, `source` (`formed` / `institution`) — la «calculadora» |
| `grade_table` | Por muestra y tramo: `n`, `share`, `n_bad`, `bad_rate`, `pd`, `jeffreys_p_value`, `traffic_light` |
| `cutoff_table` | Por muestra (incluida «Fuera del ajuste», si hay) y corte (cada límite y el de la institución): `cutoff_score`, `n_scored`, `n_with_outcome`, `n_approved`, `n_approved_with_outcome`, `n_bad`, `n_good`, `approved_share`, `approved_bad_rate`, `approved_expected_pd`, `bads_avoided_share`, `goods_rejected_share` (vacías cuando su denominador es cero, §3.5); `declared` marca el de la institución |
| `assignment` | Por operación (mismo índice que `score`): `partition`, `score`, `grade`, `grade_pd` |
| `result`, `card` | El resultado y la sección de la ficha: número de tramos, su origen, el corte, la concentración y la monotonía por muestra, los tramos en rojo; `metric_sections` (CT-2) |

### 6.3 Invariantes

Los tramos cubren todo el puntaje sin huecos; `pd` no decrece en `grade` y sólo empata entre tramos
que la regla de §12-8 igualó, con su alerta; la media de `pd`
ponderada por `share_development` es el ancla de la calibración (a la tolerancia del solver de `δ`);
en `cutoff_table`, al aprobar más tramos (`k` creciente) `approved_share` crece y
`bads_avoided_share` y `goods_rejected_share` decrecen —con la dirección de fábrica eso es **bajar**
el puntaje mínimo: de 538 a 507 puntos la aprobación sube de 58,5 % a 71,1 % en la SBA—; las
particiones son las de `score`.

### 6.4 Excel y numeración

El Excel opcional gana `11 Escala maestra.xlsx` —los tramos, la tabla por muestra y la de cortes—
y el libro de decisiones pasa de `11` a `12 Decisiones.xlsx` (la regla de D-ECL-10: el número es la
posición de la etapa; aquí la etapa va al final para mover sólo ese). Se declara en el CHANGELOG.

## 7. Algoritmo

1. Leer puntaje, PD calibrada, muestra y desenlace; alinear por índice (mismo índice o error).
2. Tomar `D`; si hay `grade_edges`, usarlos; si no, formar los tramos con D-ESC-1 (§3.2).
3. Asignar tramo a toda operación (y a las solicitudes sin desenlace) con la regla exacta de §3.2.
4. `PD_g` sobre `D` (§3.3): tasas suavizadas; si alguna invierte el orden, la regla de §12-8
   (propuesta: PAVA ponderado y alerta); `δ` por bisección sobre la reconciliación con el ancla.
5. Por muestra: tabla por tramo, Jeffreys, monotonía, concentración (§3.4).
6. Tabla de cortes por muestra, con la fila de la institución si hay corte (§3.5).
7. Publicar artefactos, resumen, decisiones al trail (`master_scale_grades`, `master_scale_cutoff`)
   y la ficha.

Rendimiento: un binning de una variable sobre Desarrollo; medido 0,04–0,13 s en las cuatro
carteras (§0.3), frente a 9–21 s de la corrida guiada.

## 8. Casos borde

- **El puntaje no separa**: si ninguna partición cumple las cuatro reglas, la escala tiene **un**
  tramo. Se publica igual (la tabla de cortes queda con una fila) y «Qué revisar» lo dice: el modelo
  no distingue grupos de riesgo con diferencias significativas. La corrida no se detiene: la escala
  es operativa, no un gate del modelo.
- **Cortes de la institución inconsistentes** (`set_grades`): un corte que deja un tramo sin
  operaciones de Desarrollo detiene la etapa con el tramo vacío y el rango del puntaje, como
  `set_bins` con cortes inválidos; las etapas anteriores y sus resúmenes quedan. Cortes que invierten
  el orden de la tasa de malos en Desarrollo, o cuya tasa suavizada lo invierte, se tratan con la
  regla de §12-8 (propuesta: los tramos invertidos comparten PD y se alerta). Cortes que respetan el
  orden pero no son significativamente distintos se aceptan —son decisión de la institución— y se
  alertan.
- **Corte de aprobación fuera del rango del puntaje**: se acepta (aprueba todo o nada), se calcula
  y se alerta.
- **Un tramo sin malos o sin buenos en Desarrollo**: la media de Jeffreys de §3.3 lo deja en una
  PD finita; con D-ESC-1 no ocurre en las cuatro carteras medidas.
- **Ancla de negocio lejos de la tasa observada**: `δ` traslada toda la escala; los contrastes fuera
  de Desarrollo pueden quedar rojos, y es la señal correcta (la calibración lo dice primero).
- **Un tramo chico fuera de Desarrollo**: con menos de 30 operaciones en una muestra (el mínimo de
  la validación, `min_rows_per_group`), su contraste queda «No evaluable», como en la validación.
- **Sin OOT** (`partition="random"`): las muestras son Desarrollo y Holdout; la tabla y el contraste
  se publican para las que hay.
- **Sin operaciones fuera del ajuste**: la muestra «Fuera del ajuste» no aparece en la tabla.
- **Cartera de comportamiento**: «aprobar» se lee como «quedar sobre el corte» (una oferta, un
  aumento de cupo, una gestión de cobranza que no se hace). La guía lo dice; el motor no cambia.
- **Muestra aprobada (sesgo de selección)**: en un scorecard de admisión entrenado sólo con
  aprobados, la tabla mide la tasa de malos de quien pasó la política anterior; el resumen lo
  declara en «Supuestos» y la corrección es H8.
- **`apply` con puntajes fuera del rango de Desarrollo**: caen en los tramos extremos, que son
  abiertos. Una fila que no se puntúa no recibe tramo ni decisión.

## 9. Reproducibilidad y auditoría

Determinista: el solver de OptBinning ya lo es para las variables con la misma entrada, y la
etapa no tiene componente aleatorio. Al trail: la regla de formación y sus cortes (origen
`formed` o `institution`, con autor y motivo cuando es de la institución), el corte de aprobación
y cada tramo en rojo o invertido fuera de Desarrollo. Sin la sección, ningún evento nuevo.

## 10. Dependencias

Ninguna nueva: OptBinning (Apache-2.0) y SciPy (BSD) ya vienen con el extra `scoring`. La sección
pertenece al extra `scoring` como el resto del pipeline F1.

## 11. Estrategia de tests

- **Canónicos a mano**: un frame de veinte operaciones con puntajes y desenlaces dados y cortes de la
  institución; tramos, PD por tramo y cada columna de la tabla de cortes calculados a mano.
- **Propiedades** (Hypothesis): la PD por tramo no decrece y empata sólo donde §12-8 igualó (con
  el contraejemplo `(30, 0)`, `(300, 1)` como caso fijo); su media ponderada es el ancla de la
  calibración; los tramos cubren el puntaje sin huecos; en la tabla, al aprobar más tramos los
  aprobados crecen y los malos evitados y buenos rechazados decrecen, y malos aprobados + malos
  evitados = malos; las celdas con denominador cero quedan vacías (rechazo total, una muestra sin
  malos o sin buenos, un corte que sólo aprueba solicitudes sin desenlace); las dos direcciones del
  puntaje dan la misma tabla espejada.
- **Oráculos**: sobre `consumo_comportamiento`, el motor reproduce (i) los cortes y los conteos por
  tramo y muestra de la regla A de `medir_h5.py` (§0) —sólo eso: ese guion asigna como PD la media
  de la PD calibrada, la alternativa descartada—, y (ii) la PD de cada tramo, su `δ` y sus
  contrastes de `oraculo_pd_tramo.py` (repo privado, `evidencia/s41/`), que calcula D-ESC-2 tal cual
  —conteos enteros, suavizado, PAVA, `δ` por bisección y Jeffreys—; los dos, fijados en un golden.
  Casos fijos: el contraejemplo `(30, 0)`, `(300, 1)` y el de §3.4 `(1000, 500)`, `(1000, 100)`.
- **Sin la sección** (D-ESC-7): el `config_hash` y el YAML del preset F1 iguales byte a byte a los
  de la 2.10.0; la proyección canónica de una corrida F1 del preset, igual; `apply` del bundle de esa
  corrida, mismas columnas y valores por una proyección que excluye `bundle_hash`, y aparte, que el
  `bundle_hash` de cada fila es el del bundle que la puntuó.
- **La tarjeta**: guardar y cargar el bundle; `apply` sobre las operaciones de Desarrollo devuelve
  el tramo y la PD de `assignment`, y la decisión con el predicado de §3.2 en las dos direcciones;
  filas `"scored"` y `"not_scorable"` mezcladas.
- **Decisiones**: `set_grades`/`set_cutoff` por la puerta guiada y por la sección `decisions` del
  YAML dan el mismo config; con D-DEC-3 tal cual, una decisión cuyo efecto ya no está en el config
  (p. ej., `approval_cutoff` retirado a mano del YAML) emite `decision_sin_efecto`, avisa, no se
  atribuye y se conserva en el registro, y la corrida sigue sin corte.
- **Tres puertas** (capa B): guiada, YAML y pantalla con el mismo `config_hash` y los mismos
  artefactos.
- **Copy y códigos internos** sobre el resumen, la pantalla y el informe (gates existentes).
- Un **control negativo por regla**, en paralelo (RUNBOOK §6): la participación mínima, la
  separación, la monotonía, la PD del tramo y su ancla, el contraste, la regla exacta del corte, la
  fila de la institución, la muestra «Fuera del ajuste», la sección ausente fuera del hash, el bloque
  del bundle.
- ⚠️ **OR-Tools revienta el proceso de pytest** (medido en S20): los tests que forman tramos con
  el solver corren en subproceso o con un doble del binning, como los del pipeline F1 in-process.

## 12. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 12-1 | Cómo se forman los tramos (D-ESC-1) | (a) **los datos deciden cuántos**: ≥ 5 % de Desarrollo, vecinos distintos con p ≤ 0,05, monótonos, hasta 10; (b) la regla del banco: hasta 5 tramos, entre 10 % y 70 % cada uno; (c) siete tramos fijos (Basilea II §404) | **(a)**: es la única que no inventa un número —5, 7, 6 y 10 tramos en las cuatro carteras— y su separación es la que impide las inversiones fuera de Desarrollo (§0.3); (b) junta tramos que se distinguen —en la SBA, uno de tasa 51 % reúne los tramos de 43 % y 56 % de (a)— y conserva menos discriminación fuera de Desarrollo en 3 de 4 Holdout y en las 3 OOT (Gini de la escala, §0.3); (c) parte tramos que no se distinguen en carteras chicas y junta los que sí en las grandes |
| 12-2 | La PD de cada tramo (D-ESC-2) | (a) **la tasa de malos observada del tramo en Desarrollo, llevada al ancla de la calibración**; (b) la media de la PD calibrada de sus operaciones | **(a)**: Basilea II §447 y el flujo del banco; ajusta mejor fuera de muestra en las dos carteras reales (SBA Holdout 1,08 frente a 1,87 puntos, ningún tramo rojo frente a uno) y corrige la descalibración del modelo en las colas en vez de heredarla. (b) gana por poco en las sintéticas, que se generan con una logística |
| 12-3 | El corte de aprobación (D-ESC-5) | (a) **un corte**: aprobar o rechazar; (b) dos cortes, con una zona de revisión manual entre ellos | **(a)**: la tabla ya muestra todos los cortes posibles, y una zona de revisión se expresa en el sistema del banco con los tramos («del 5 al 6, a comité»); (b) es una perilla más sin un caso que la pida |
| 12-4 | Identidad de una sección nueva (D-ESC-7) | (a) **una sección de dominio nacida después de la 2.10.0 se serializa sólo cuando está declarada**: sin `master_scale`, el `config_hash` y el YAML del config son los de la 2.10.0 byte a byte, los resultados computacionales son iguales (la proyección canónica de los artefactos y de `apply`), y la procedencia —versión, commit y huella de distribución en el lineage, en el manifest y en el `bundle_hash` de cada fila de `apply`— sigue siendo la real de cada versión (§5.3); (b) aceptar que se mueva el `config_hash` de todo config en un minor | **(a)**: el `config_hash` es la identidad del inventario de los usuarios; moverlo entero por una sección que no usan rompe esa promesa. Es regla general: vale también para H4 y lo que venga |
| 12-5 | ¿Corre por defecto? (D-ESC-8) | (a) **sí**: la puerta guiada y los trabajos del scorecard de la pantalla la corren sin pedirla (cambia el `config_hash` de esas corridas, no el de ningún preset); (b) sólo si se pide | **(a)**: «el escaparate se juzga por lo que funciona sin tocar nada» (SDD-31); cuesta 0,1 s y no pide nada; quien no la quiere la quita del config |
| 12-6 | Una escala maestra de la institución (límites de PD comunes a varios modelos) | (a) **fuera de esta versión**: candidato, con su evidencia pendiente; (b) dentro, como hoja opcional (los límites de PD de cada grado) | **(a)**: el ROADMAP pide tramos por modelo; una escala común tiene sentido cuando el banco opera dos o más modelos, y ningún caso medido la pide aún (SDD-31 D-SIM-3) |
| 12-7 | Capas, releases y la demo (D-ESC-9) | (a) **A** —motor, puerta guiada con `apply`, tarjeta, resumen, guía— en la **2.11.0**; **B** —pantalla, informe, Excel; la etapa deja de ser experimental— en la **2.12.0**, y la demo del scorecard gana la escala en B (recaptura, con su OK); (b) A y B juntas en la 2.11.0; (c) como (a), pero la demo queda igual | **(a)**: A ya cambia cómo se opera la tarjeta y merece salir sola; B mueve front, informe y goldens. Que la demo la muestre es parte del escaparate |
| 12-8 | Tramos que invierten el orden en Desarrollo (D-ESC-2; elevada por la revisión adversarial) | (a) **igualar**: los tramos vecinos invertidos comparten la PD de la regresión isotónica (PAVA ponderado por operaciones) sobre las tasas suavizadas, con alerta, y la corrida sigue; (b) detener la etapa y pedir que se unan los tramos | **(a)**: vale igual para los tramos formados y para los de la institución, nunca detiene la corrida por un detalle de suavizado, es el estimador monótono estándar y la alerta deja la decisión de unirlos a la persona. Con los tramos formados no ocurrió en ninguna de las cuatro carteras; es la salvaguarda de los cortes de la institución y de los tramos chicos |
| 12-9 | El recorte del puntaje en la tarjeta (elevada por la pasada 3; defecto preexistente) | (a) **la tarjeta respeta `clip` como la corrida en todo bundle nuevo**: congela `clip` y recorta sólo si está encendido; los bundles ya guardados, sin esa clave, conservan su comportamiento (recortar siempre). Excepción declarada a D-ESC-7: cambia `apply` sólo con límites de puntaje declarados y `clip=False`; (b) corregirlo sólo en los bundles con escala; (c) dejarlo y declarar el abierto | **(a)**: hoy, con límites declarados y `clip=False`, la corrida publica 475,58 y `apply` recorta a 490 (el caso de `test_scorecard_scaler.py`, sin redondeo y con límites 490–500): con la escala, la tabla rechazaría una operación que la tarjeta aprobaría. Es un defecto de la tarjeta, no de la escala, y corregirlo sólo con escala dejaría dos tarjetas que puntúan distinto. Ni el preset ni la puerta guiada declaran límites: sin ellos nada cambia |

**Respuestas de Cami (2026-10-11, interactivas): la recomendación (a) en las nueve.** Vigente:
D-ESC-1 (los datos deciden cuántos tramos), D-ESC-2 con la tasa observada del tramo llevada al ancla
y, ante inversiones, la igualación por regresión isotónica con alerta (§12-8), un solo corte
(D-ESC-5), D-ESC-7 (una sección de dominio nacida después de la 2.10.0 se serializa sólo cuando está
declarada) con la excepción de §12-9 (la tarjeta respeta `clip` en todo bundle nuevo; los ya
guardados conservan su comportamiento), D-ESC-8 (corre por defecto en la puerta guiada y en los
trabajos del scorecard de la pantalla), la escala común de la institución fuera de esta versión, y
D-ESC-9: capa A → 2.11.0, capa B → 2.12.0 con la demo del scorecard ganando la escala (recaptura
con su OK). La capa A se programa en S42.

**Riesgos y mitigación.** (1) Dos PD por solicitud —la de la operación y la de su tramo— pueden
confundir: la guía dice cuál usa cada cosa y la tarjeta publica las dos con nombres distintos. (2) La
tabla de cortes de una cartera aprobada subestima la tasa de malos de quien hoy se rechaza: se
declara en «Supuestos» y la corrección es H8. (3) OR-Tools revienta el proceso de pytest (S20): los
tests de formación corren en subproceso o con un doble del binning. (4) Una escala que se recalcula
en cada corrida cambia de cortes si cambian los datos: los cortes van al trail y al bundle, y quien
opera fija los suyos con `set_grades`.

**Candidatos anotados, no adoptados** (cada uno espera su caso): la escala común de la institución
(§12-6); los tramos sobre una PD sin puntaje (un retador de H6); precio y rentabilidad por tramo
(márgenes, costos y LGD de la institución); la zona de revisión (§12-3); la exportación de la escala
a SQL (transversal del ROADMAP).

## 13. Simplicidad (SDD-31)

- **Entrada mínima:** ninguna nueva. La escala corre sobre lo que el scorecard ya tiene —el
  puntaje, la PD calibrada, el desenlace y las muestras—. Se infieren y se declaran al trail: los
  tramos (cuántos y sus cortes, con la regla que los formó), la PD de cada uno con el `δ` del ancla y
  la dirección del puntaje.
- **Qué NO se configura**, y por qué cada cosa es una constante:
  - las cuatro reglas de formación (5 %, p ≤ 0,05, monotonía, hasta 10): el 5 % es la cota que ya
    usa la puerta guiada para los tramos de las variables; la separación y la monotonía son la
    «diferenciación significativa» de la norma; el tope de 10 mantiene la escala operable y sólo
    obligó en la SBA (32.770 operaciones de Desarrollo). §0.3 midió que funcionan en cuatro
    carteras;
  - la regla de la PD del tramo (§3.3) y su ancla, que es la de la calibración;
  - el contraste por tramo, su semáforo y su mínimo de 30 operaciones: los de la validación;
  - las columnas de la tabla de cortes y la medida de concentración (sin umbral, §3.4);
  - la numeración (1 = menor riesgo) y la base (el puntaje).
- **Campos esenciales:** `master_scale` **2** —`grade_edges` y `approval_cutoff`, las dos decisiones
  humanas— (tope 6). No hay «Avanzado»: la sección no tiene más hojas.
- **Presupuesto de perillas:** **dos hojas**, y ninguna es una perilla de método: son las dos
  decisiones de la institución, con motivo. Evidencia de que no tienen default: el corte de
  aprobación es apetito de riesgo —ningún valor de fábrica es defendible—, y el flujo del banco
  fijaba sus cortes de tramo a mano (sus cortes eran un argumento, con el corte automático apagado
  por defecto). Mismo criterio que `user_splits` (FLUJO-GUIADO-SCORECARD §8-9, la única excepción al
  presupuesto cero del scorecard, también una decisión humana).
- **Resumen de la etapa «Escala maestra»** (3–8 líneas y su tabla): cuántos tramos y con qué regla
  («5 tramos de puntaje, del 1, de menor riesgo, al 5; cada uno con al menos el 5 % de Desarrollo y
  una tasa de malos distinta de la de sus vecinos»); la PD de punta a punta y su ancla («de 4,7 % a
  53,6 %; su promedio es el de la calibración, 23,3 %»); fuera de Desarrollo («en Holdout y OOT la
  tasa de malos sigue el orden de los tramos; ningún tramo subestima su PD», o el tramo y la muestra
  que fallan); la concentración («el tramo mayor tiene el 35 % de Desarrollo»); y el corte —el de la
  institución con sus cuatro cifras en la última muestra, o «sin corte declarado: la tabla de cortes
  muestra, para cada límite, cuánto se aprueba, la tasa de malos, los malos evitados y los buenos
  rechazados»—. **Tabla de decisión:** los tramos (desde/hasta en puntos, PD, participación y tasa de
  malos por muestra, semáforo). **Tablas adicionales:** la de cortes por muestra. **Decisiones
  humanas:** `set_grades` y `set_cutoff`. «Qué revisar»: tramos rojos o no evaluables, inversiones
  fuera de Desarrollo, un solo tramo, el corte fuera del rango. «Supuestos»: la PD del tramo es la
  tasa de Desarrollo llevada al ancla; en una cartera aprobada, la tabla mide a quien pasó la
  política anterior.
- **Notebook mínimo:** **no cambia** —15 líneas, 5 conceptos—: la etapa corre y habla dentro de
  `run()`. La guía del scorecard gana un bloque «Escala maestra y puntos de corte», ejecutado en CI
  (unas 6 líneas: `set_cutoff`, `resume` y `apply` sobre solicitudes nuevas).
- **Las cinco cifras** (golden `test_simplicidad_scorecard.py`):

| Cifra | Hoy (`e6bba24`) | Después |
|---|---|---|
| Líneas de usuario | 15 | 15 |
| Esenciales visibles a la vez | 35 (máx. 6 por sección) | **37** (`master_scale` 2) |
| Perillas de las secciones del scorecard | 411 (12 secciones) | ≈ **414** (13; `grade_edges` cuenta además su fila; se mide en la capa A) |
| Segundos al primer resumen (paquete) | ≈ 1 | ≈ 1 (el primero es el de datos; la escala suma 0,1 s al final) |
| Conceptos antes del primer resultado | 5 | 5 |

Las tres puertas (D-SIM-1): la guiada y la completa en la capa A —experimentales, marcadas—; la
pantalla en la B, con el gate de las tres puertas (mismo `config_hash` y mismos artefactos), y
entonces la etapa deja de ser experimental.

## 14. Capa A implementada (S42) — lo que el código precisó

Implementada el 2026-10-11 sobre `77a873b` (2.10.0), sin publicar. Nada de esto reabre una
decisión de §12; son precisiones de implementación, medidas.

- **D-ESC-7 en un solo punto.** Un `model_serializer` envolvente de `BayesRiskConfig`, **sin
  anotación de retorno**, omite las secciones de `SECCIONES_NACIDAS_DESPUES_DE_2_10_0` (hoy sólo
  `master_scale`) cuando valen `None`: ninguna serialización del config las ve —`config_hash`,
  `dump_config`, el `config.yaml` de la evidencia, los defaults del schema de la pantalla— y los
  schemas JSON de validación y de serialización siguen siendo uno, como en la 2.10.0. Con `-> Any`
  Pydantic vaciaba el de serialización (pasada 1 de Codex); `Field(exclude_if=…)` existe recién
  desde Pydantic 2.12 y la librería declara `pydantic>=2.5` (pasada 2). Medido igual en Pydantic
  2.5.3, 2.11.10 y 2.13.4 (`evidencia/s42/prueba_pydantic.py`). Un gate exige la lista en los dos
  sentidos —toda sección nueva de la raíz está en ella y la lista sólo nombra secciones nuevas—,
  otro que los dos schemas sean uno y otro que nada use lo que el piso de Pydantic no trae. Medido sobre `77a873b` y
  reproducido: el `config_hash` y el YAML (completo y de los campos provistos) de los cuatro
  presets y del config vacío, iguales byte a byte; la proyección canónica de una corrida F1 del
  preset, 0 diferencias (`evidencia/s42/`). El YAML **completo** depende de qué capas importó el
  proceso —preexistente y documentado en `dump_config`—, así que su literal se mide en un
  intérprete fresco con las capas de dominio cargadas.
- **El solver de la formación es el de la librería** (`mip`/`bop`), no el `cp` por omisión de
  OptBinning que usó la medición de S41: `cp` está vetado en la librería porque se cuelga en
  variables continuas (D-ABA-5). Medido en S42 sobre las dos carteras del paquete: los mismos cortes
  (`consumo_comportamiento` 493,5 · 511,5 · 526,5 · 555,5; `consumo_drift` seis cortes), estado
  `OPTIMAL`, en la mitad del tiempo. El oráculo de §11 (cortes, conteos por tramo y muestra, PD,
  `δ` y semáforos de S41) se reproduce exacto con OptBinning real, en un subproceso.
- **PAVA agrupa también los empates exactos**: dos tramos vecinos con la misma tasa suavizada no se
  distinguen y comparten PD con la misma alerta, de modo que la PD sólo empata donde §12-8 igualó
  (§6.3; lo encontró una propiedad de Hypothesis). El ajuste no cambia y ningún caso medido tiene
  empates.
- **Columnas de los artefactos (aditivas a §6.2).** `grades` gana `label` (el tramo en puntos, con
  la regla de §3.2) y `n_bad_development`; `grade_table`, `sample` y `n_with_outcome`;
  `cutoff_table`, `sample` y `grades_approved` (vacío en la fila de la institución). Una celda sin
  denominador queda vacía (`NaN`, el vacío de pandas), nunca en 0. En la muestra «Fuera del
  ajuste» la participación es sobre todas sus operaciones puntuadas y la tasa de malos y el
  contraste, sólo sobre las que tienen desenlace.
- **Las dos decisiones** (`set_grades`, `set_cutoff`) tienen como sujeto la columna del puntaje
  (`scorecard.score_column`) y se cotejan en familias propias (`escala_tramos`, `escala_corte`):
  un `set_cutoff` posterior no reemplaza un `set_grades`. La línea de la decisión dice los cortes o
  el corte.
- **La tarjeta se guarda con el esquema 3**: `model.clip` congelado (§12-9) y el bloque opcional
  `master_scale` (`cuts`, `grade_pd`, `approval_cutoff`, `source`). Un bundle de esquema 1 o 2 se
  lee y aplica como antes (recorta siempre); una versión anterior de la librería rechaza el esquema
  3 con su mensaje de esquema no soportado. `Scorecard.apply` exige una corrida terminada y sin
  decisiones pendientes (si no, la tarjeta no llevaría la última decisión).
- **«Fuera del rango del puntaje»** (§8) se lee sobre Desarrollo: el corte de la institución aprueba
  todo o nada de Desarrollo. **Cortes de la institución que no se distinguen** se alertan con el Z de
  dos proporciones de OptBinning (bilateral, agrupado). **Un solver sin partición utilizable** (o
  que falla) deja la escala en un tramo con la causa en el trail y en «Qué revisar»: la corrida no
  se detiene.
- **Sin canal de métricas** (`DOMAINS_WITHOUT_METRICS`, con su razón): la lectura de la escala
  vive en sus artefactos y su resumen; el SDD no pide escalares al canal.
- **Capa A sin pantalla**: la sección no entra al formulario, no lleva marcas de esencial y el Excel
  no gana libro (las tres cosas son de la capa B, D-ESC-9). Por eso las cinco cifras de la capa A
  son las de la 2.10.0 —**15 · 35 · 411 · ≈ 1 s · 5**—; medido, la sección pinta **3** nodos en el
  barrido del formulario (`grade_edges`, su fila y `approval_cutoff`), así que la B lleva las
  perillas a **414** y los esenciales a **37**, como estimó §13. Los tres métodos nuevos de
  `Scorecard` y el dominio se declaran experimentales (`bayesrisk.testing.stability`, sus
  docstrings, `api.md` y el CHANGELOG).
- **Pasada 1 de Codex sobre el código** (`500f242`; cinco hallazgos, uno high, ninguno
  contractual; cada uno con su test nacido rojo y su control negativo): `Scorecard.apply` tras una
  corrida parcial (`run(until=…)`) puntuaba sin el corte declarado —ahora exige una corrida completa
  con su escala—; el schema de serialización vacío (arriba); el `δ` con anclas extremas (el
  intervalo sale del ancla y de las tasas; un error de la etapa es de dominio, no un `ValueError`);
  una huella de decisión editada con texto abortaba la corrida (ahora queda sin efecto, D-DEC-3); y
  el resumen afirmaba «sigue el orden» de una muestra sin tramos evaluables (ahora dice «sin
  contraste»).
- **Pasada 2 de Codex** (`4225b09`; cuatro hallazgos, uno high, ninguno contractual; cada uno con
  su test nacido rojo y su control negativo): `exclude_if` no existe en las versiones de Pydantic
  que la librería admite (arriba); la PD del tramo con anclas al borde de (0, 1) —una sigmoide que
  no desborda ni pierde los subnormales, y la PD acotada a los vecinos interiores de 0 y 1, que la
  tarjeta exige—; las huellas de `set_grades`/`set_cutoff` viajan enteras en el trail (no son
  listas de variables) y su cotejo es total (texto, listas anidadas, enteros gigantes); y dos tramos
  de la institución con la misma tasa sin varianza (los dos sin malos) también se alertan como
  indistinguibles, sin inventar un p-valor.
- **Pasada 3 de Codex, la última del tope declarado** (`a25efde`; dos hallazgos medium, ninguno
  contractual; confirma cerrados los de la pasada 2 sobre D-ESC-7 y los vecinos): la brecha del
  ancla se acumula por tramo y compensada (`fsum`), porque con pesos que en `float` no suman 1 un
  ancla de 0,9999999999999999 no se alcanzaba; y la línea de una decisión histórica con una huella
  ilegible se escribe tal cual en vez de tumbar el resumen final del informe y de Resultados. Los
  dos con su test nacido rojo y su control negativo; sin cuarta pasada, por el criterio declarado.
  En el mismo cierre, el CI de Windows acusó que el oráculo en subproceso decodificaba en UTF-8 la
  salida de un hijo que escribía en cp1252: el hijo corre ahora con UTF-8 (reproducido en local con
  el padre en cp1252: 1 error antes, verde después).

## 15. Capa B implementada (S43) — lo que el código precisó

Implementada el 2026-10-12 sobre `422fe0f` (2.11.0 publicada), sin publicar. Nada de esto reabre
una decisión de §12; son precisiones de implementación, medidas.

- **La pantalla (D-ESC-8).** `master_scale` entra a los trabajos `scorecard_pd` y `pd_y_lgd`, tras
  `validation`, sembrada en blanco (`grade_edges` y `approval_cutoff` en `None`: los tramos los
  forman los datos y no hay corte); validada, es la misma sección que siembra la puerta guiada. La
  sección declara sus dos esenciales (`declara_esenciales` y `ui_essential`; `grade_edges` como
  lista de números, `approval_cutoff` como número, cada una con su ayuda) y no tiene «Avanzado».
  La `description` de `approval_cutoff` se acortó a 136 caracteres —el tope del placeholder es 160—
  y el detalle bajó a `ui_help`. Un ejemplo publicado sin la sección (el preset F1) carga sin ella
  y su corrida no la corre: su `config_hash` no cambia (D-ESC-7).
- **Resultados** gana «Escala maestra y puntos de corte» tras la validación formal: las líneas, las
  alertas, la tabla de los tramos y la de puntos de corte del **mismo resumen** de la etapa
  (`StageSummary.to_dict`), sin formato propio en el front.
- **El informe** gana la subsección «Escala maestra y puntos de corte» dentro de «Resultados» (no un
  capítulo nuevo: no mueve la numeración de ningún informe sin la escala). Su cuerpo son las líneas
  y las alertas («Qué revisar») del resumen y sus dos tablas, las del resumen ya escritas
  (`master_scale.scale`, `master_scale.cutoffs`), las arma
  `guided.summaries.master_scale_report_extras` —una sola fuente, como las de escenarios de
  IFRS9-FIRMABLE—. Los artefactos completos (`grades`, `grade_table`, `cutoff_table`) van al anexo
  de tablas; `assignment` (una fila por operación) no. La sección del config va al anexo de
  parámetros. Sin la etapa no hay card ni subsección: el informe es el de siempre (medido con su
  control negativo).
- **El Excel** gana `11 Escala maestra.xlsx` —resumen, tramos, tabla de cortes y las tablas
  completas del informe— y las decisiones pasan a `12 Decisiones.xlsx`. Las dos tablas que el
  informe arma desde el resumen no se repiten como texto en el libro: ya son sus hojas «Decisión» y
  «Tabla de puntos de corte», con sus números.
- **Las tres puertas** (D-SIM-1): la guiada, el YAML por `bayesrisk.run` y la pantalla
  (`/api/config/from-yaml` → `/api/run`) dan el mismo `config_hash`, los mismos artefactos de la
  escala (`grades`, `grade_table`, `cutoff_table`, `assignment`, iguales por `assert_frame_equal`),
  el mismo resumen en Resultados y la misma subsección del informe. Con las tres cerradas, la
  etapa y `set_grades`/`set_cutoff`/`apply` son **estables** (`STABLE_DOMAINS`).
- **Las cinco cifras después:** **15 · 37 · 414 · ≈ 1 s · 5** —la sección suma 2 esenciales y 3
  nodos (`grade_edges`, su fila y `approval_cutoff`, enumerados contra la 2.11.0)—. Censos movidos:
  `HOJAS_DEL_FORMULARIO` 633 → 636, `HOJAS_CON_DEFAULT_EFECTIVO` 517 → 520, secciones del
  formulario 18 → 19, esenciales en 16 secciones y 59 caminos, el sidebar del ejemplo F1 12 → 13,
  la política de invariantes (`master_scale` exenta: no lee columnas del archivo), el golden de
  campos de `ReportInputBundle` y el cuaderno publicado (12 libros).
