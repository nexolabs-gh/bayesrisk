# Enmienda CIFRAS-EN-PANTALLA — la pantalla escribe las cifras como el informe

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda de **presentación** de la pantalla (panel de Resultados, gráficos, ficha, preflight) y de los textos con cifras que arma el backend. No toca el motor, el config, los números de `results`, los exports de datos ni ninguna identidad |
| **Decisiones** | **D-PAN-1…6** |
| **Módulos** | `web/src/lib` (`results-format`, `model-card`, `datasets`, nuevo `cifras`), `web/src/components` (`ResultsTab`, `charts/`, `DatosTab`, `PreflightNotice`, `FieldRenderer`, `LandingLauncher`), `bayesrisk.report.cifras`, `bayesrisk.guided.summaries`, `bayesrisk.report.prose`, `bayesrisk.methodology`, `bayesrisk.ui.routes` |
| **Fase** | F1 (primera de la FASE B de S23) |
| **Estado** | **APROBADA por Cami el 2026-09-27** (S23, interactivo): «Aprobar y programar», tras tres pasadas de Codex (§11). Recaptura de la demo **«Con la próxima release»** (§8-2, opción a) |
| **Depende de** | D-INF-1…4 (la regla numérica del informe, `bayesrisk.report.cifras`), D-MON-4/5 (la convención cuelga del idioma; el símbolo de moneda no se inventa), D-CPY-4 (p-valores «< 0,001») |
| **Release** | Ningún número, `config_hash`, `data_hash` ni artefacto de cálculo cambia. Cambia el texto de los resúmenes por etapa (`summaries`), un rótulo del backend y los textos de auditoría del informe; la API de la pantalla gana campos aditivos (`*_legible`) y el resultado del EDA, `numeric_profiles` ⇒ «Corregido» en la próxima release, con su OK propio |
| **Autor / Fecha** | Claude Code (writer) / 2026-09-27 |

---

## 0. De dónde sale

Del cierre de S22: al revisar la prueba con el SBA quedaron **elevados tres hallazgos** de la
pantalla y de los resúmenes, que D-INF no cubría (su alcance era el informe). Cami fijó el orden de
la FASE B de S23: **primero la pantalla**. El borrador de tres puntos que salió de ahí se quedó corto;
todo lo que sigue está **medido el 2026-09-27** sobre `bayesrisk` 2.0.0 (`main` `71520cd`), con un
censo exhaustivo del front y del backend y la demo publicada abierta en el navegador interno.

**La demo publicada** (`demo.bayesadvisory.cl`, pestaña Resultados con todas las secciones
abiertas; texto visible más el texto de los gráficos SVG; expresiones regulares en §4):

| Qué | Scorecard | IFRS 9 |
|---|---|---|
| Cifras con **punto decimal** (`0.7123`, `19.423268`) | **565** (+ 32 en gráficos) | **144** |
| Cifras con **coma de miles** (`3,961`, `114,325,315`) | **172** | **97** |
| Porcentajes **sin espacio** (`23.8%`) | **177** | **136** |
| Cifras con coma decimal (las que arma el backend) | 264 | — |

La misma pantalla de IFRS 9 escribe `6.000` (el backend, miles en es-CL) y `6,000` (el front, miles
en convención anglo): **el mismo número de dos formas que en español se leen distinto**. En el
scorecard, `3,961` es un conteo y `0,013` una tasa. El informe de la misma corrida escribe en es-CL
sus tablas y cifras desde la 1.20.0, **salvo el texto de auditoría del motor** (§1.4): su tabla
«Criterios de selección por variable» publica `iv=0.00292241 < min_iv=0.02` (`report-f1.html` de la
demo).

## 1. Qué está mal

1. **La pantalla tiene cuatro convenciones a la vez.** Los once formateadores numéricos de
   `web/src/lib/results-format.ts` suman **178 llamadas** (ResultsTab 127, charts 42, ficha 2,
   el propio módulo 7):

   | Formateador | Hoy | Llamadas |
   |---|---|---|
   | `formatMetric` | `toFixed(4)`, punto decimal | 46 |
   | `formatPValue` | `1.2e-5` bajo 1e-4; si no, `toFixed(4)` | 5 |
   | `formatPercent` | `23.8%` | 40 |
   | `formatPercentValue` | `8.63%` | 1 |
   | `formatCount` | coma de miles, `3,961` | 51 |
   | `formatAmount` / `formatMoney` / `formatMoneyCompact` | coma de miles (`MONEY.thousands = ","`), `$2.3 M` | 19 |
   | `formatCut` | `String(x)` con punto | 3 |
   | `formatClp` / `formatClpCompact` | **ya es-CL** (`$388.732.916`) | 13 |

   Por fuera de ellos: **24 `toFixed`** en 12 gráficos, el formato por defecto de `ChartTooltip`
   (`toFixed(4)`), **7 ejes numéricos sin `tickFormatter`** (pintan `String(v)`), 2 ejes en
   millones sin miles, **4 `toLocaleString("es-CL")`** —que dependen de ICU y conviven con
   `formatCount` (el tooltip de Lift dice `n = 3.961` junto a una tabla con `3,961`)—, y
   `model-card.formatNumber` con su propio corte exponencial.
2. **Los umbrales se redondean.** `selectionThresholdRows` (`formatMetric(raw, 2)`),
   `stabilityThresholdLabels` (`toFixed(2)`) y el umbral de estabilidad del EDA escriben un corte
   del config redondeado: un `min_iv = 0.025` se lee `0.03`. El informe ya los escribe exactos
   (`cifras.corte`, «cortes por procedencia»).
3. **Los resúmenes por etapa no aplican la regla del informe.** `guided/summaries.py` escribe en
   es-CL pero con `prose._num` (39 usos: decimales fijos, sin la regla del cero final, sin dos
   cifras significativas bajo 0,001) y un `_pvalor` propio; un PSI de `0.24996` junto a su corte
   de `0,25` se lee `0,2500 → Revisar`. Su `_formatear` agrupa en miles **toda** columna entera,
   así que un año de cohorte saldría `2.024` (lo que `cifras.es_columna_de_conteo` evita). El
   «Resumen de la corrida» del informe reproduce esos textos. En `report/prose.py` quedan dos `_num`.
4. **El texto de auditoría del motor llega crudo.** El `detail` de la selección
   (`selection/selector.py`: `iv=2.94993e-05 < min_iv=0.02`, `|rho|=0.93 > threshold=0.9`,
   `vif=5.1234 > threshold=5`) y los valores del rastro del modelo (`model/estimator.py`:
   `iv_contribution=…`, `wald_p=…, lr_p=…`, con `:.6g`) se pintan tal cual **en la pantalla y en
   el informe**: la tabla «Criterios de selección por variable» (`selection.selection_table`, cuerpo)
   y la traza del stepwise (`model.stepwise_trace`, anexo) llevan el `detail`
   (`report/builder.py:129,134`, `report/document.py:227,298`), y el renderer escribe los textos
   tal cual. **El formato no se puede tocar en el motor**: `model/step.py` vuelve a leer
   `iv_contribution=` con `float()` para la auditoría del stepwise.
5. **La ficha escribe sus umbrales como métricas.** `model-card.modelCardDecisionRows` pasa `umbral`
   por `describeValue` → `formatNumber`, que redondea a cuatro decimales; el motor registra ahí
   umbrales efectivos (`selection/step.py:198`, `model/step.py:300`). Un umbral `0.24994` pasado a
   `cifra` se leería `0,2499`: otra política.
6. **Rótulos del backend con otra convención.** `methodology._scenario_label` escribe
   «Base 33.33 %»; los perfiles del EDA rotulan sus tramos con `str(pd.Interval)` →
   `(0.5, 1.25]`; el preflight de insumos externos (`ui/routes.py`) escribe conteos sin miles y una
   lista con `repr` de Python; el mensaje que rechaza fracciones de partición que no suman 1
   (`data/config.py`) escribe `suma observada = 0.9870`.
7. **Copy fijo que miente o desentona.** ResultsTab afirma «Los p-valores de la tabla se muestran
   con cuatro decimales» (con `< 0,001` deja de ser cierto); «Wilson 95%» (4 veces), «azar (1.0×)»,
   el `{v}%` de la landing y el texto del slider del formulario (`{min}`, `{num}`, `{max}` crudos).

## 2. Decisiones propuestas

### D-PAN-1 — Una sola regla numérica, con un espejo atado por golden

La regla de `bayesrisk.report.cifras` (D-INF-1) es la de la pantalla. El front **no la reimplementa
a ojo**: `web/src/lib/cifras.ts` es su **espejo**, atado a Python por un **golden bidireccional**.

- **Funciones** (mismos nombres que en Python): `cifra(x, decimales = 4)`, `pvalor(x)`,
  `corte(x, minimo = 2)`, `conteo(n)`, y dos que hoy viven sueltas en `report/prose.py` y pasan a
  `cifras.py` **sin cambiar su salida**: `porcentaje(p, decimales)` (la de `_pct`: coma decimal y
  espacio, `23,8 %`) y `monto(x, simbolo)` (la de `_money`/`_clp`: punto de miles, sin decimales).
  El compacto de los gráficos (`$2,3 M`, `$80 k`) queda en el front, construido sobre `cifra`.
- **El exacto es decimal.** Python parte de `repr(x)`; el espejo, de `Number.prototype.toString()`.
  Las dos son la representación **más corta** que vuelve al mismo `float64` y, entre las más cortas,
  la más cercana (ECMAScript `Number::toString`, paso 5; el `repr` de Python desde 3.1): dan los
  mismos dígitos, con otra sintaxis del exponente (`1e-07` / `1e-7`) que el espejo normaliza. El
  redondeo es **al par más cercano sobre esos dígitos**, en aritmética de cadenas —sin `toFixed`,
  que redondea el binario, ni `Intl`, que depende de ICU—.
- **El golden.** Python genera `web/src/lib/__golden__/cifras.json`: para cada función, pares
  entrada → texto sobre los casos de borde (ceros finales, `0.001`, `1e-6`, `999.99995`, `1000`,
  negativos, cortes con muchos decimales) **y 2.000 `float` sembrados** en todas las magnitudes. Un
  test de Python exige que el archivo sea exactamente lo que genera el código (un cambio en Python
  sin regenerar → rojo); vitest exige que el espejo dé cada texto (un cambio en el espejo → rojo).
  Mismo patrón que ya ata las bandas del PSI. **Las entradas van tipadas**, porque JSON no las
  representa todas: `{"float": "<repr>"}` (el espejo la lee con `Number(…)`; `-0` se reconoce con
  `Object.is`), `{"especial": "nan" | "inf" | "-inf"}` y `{"entero": "<dígitos>"}`.
- **El dominio del espejo, declarado.** (a) **Un cero se escribe sin signo en todas las funciones**:
  hoy `corte(-0.0)` da `-0,00` en Python; se corrige ahí y el golden lo fija. (b) `conteo` recibe
  enteros seguros de JavaScript (`|n| ≤ 2^53 − 1`); fuera de ese rango el espejo devuelve el entero
  sin agrupar, y el golden prueba el borde (una cartera no cuenta 9 × 10^15 operaciones). (c) **La
  pantalla recibe `float`, no `Decimal`**: el serializer convierte (`ui/serializers.py:534-542,
  827-850`). Para un `Decimal` con hasta 15 cifras significativas —todo corte escrito a mano—,
  `repr(float(d))` es el mismo decimal y el texto es idéntico al del informe; un test lo exige sobre
  todos los `Decimal` de los presets y de los defaults. Más allá de 15 cifras la pantalla escribe el
  `float` que recibe: la paridad con el informe se declara acotada a ese dominio, sin cambiar el
  contrato de `results.json`.
- **Los formateadores del front conservan sus nombres** (las 178 llamadas no cambian de forma) y
  pasan a ser envoltorios del espejo: `formatMetric` → `cifra`, `formatPValue` → `pvalor`,
  `formatPercent` → `porcentaje`, `formatPercentValue(x)` → `porcentaje(x / 100)`, `formatCount`
  → `conteo`, `formatCut` → `corte`, `formatAmount`/`formatMoney`/`formatClp` → `monto`. La
  constante `MONEY.thousands` desaparece (el separador cuelga del idioma, D-MON-5); `MONEY.symbol`
  sigue siendo la única constante de moneda.

### D-PAN-2 — Toda cifra de la pantalla pasa por el espejo

- **Gráficos**: los 24 `toFixed`, el formato por defecto de `ChartTooltip` y los rótulos sobre las
  barras usan los formateadores. **Todo eje** (`XAxis`/`YAxis`) declara `tickFormatter`: los ejes
  numéricos escriben el **valor exacto del tick** (`corte(v, minimo = 0)`: `0,25`, `0,5`, `1.200`
  —los ticks de Recharts son decimales «redondos», y un tick redondeado describiría otro punto—);
  los de categoría usan la identidad declarada. Los ejes en millones, `monto` compacto.
- **Umbrales exactos**: `selectionThresholdRows`, `stabilityThresholdLabels` y el umbral del EDA
  escriben con `corte` (el valor del config, exacto), no con `cifra`.
- **Conteos e identificadores**: los enteros que cuentan (filas, operaciones, casos) van con
  `conteo`; los que **identifican** (semilla, año, período, cohorte, número de tramo, etapa, banda)
  con `String`, nunca agrupados —la misma dirección segura que `cifras.es_columna_de_conteo`—. Los
  31 enteros interpolados que hoy no pasan por un formateador se clasifican uno por uno en la
  implementación con ese criterio.
- **Los cuatro `toLocaleString("es-CL")`** pasan a `conteo` (determinista, sin ICU).
- **La ficha del modelo**: sus `umbral` y `valor` los escribe el backend (D-PAN-4); el front sólo
  cae a `model-card.formatNumber` —ya sobre el espejo— con un fixture anterior a la recaptura.

### D-PAN-3 — Los resúmenes y los rótulos del backend, con la misma regla

- `guided/summaries.py` usa `cifras.cifra` (con los decimales que cada frase ya pedía),
  `cifras.pvalor`, `cifras.porcentaje` y `cifras.conteo` en vez de `_num`, su `_pvalor`, `_pct` y
  `_miles`. Su `_formatear` **conserva la semántica declarada** en cada `formats` (`"int"` es un
  conteo: «Malos», «Filas» siguen con miles); sólo cambia la inferencia para una columna entera
  **no declarada**, que deja de agruparse salvo que `cifras.es_columna_de_conteo` la reconozca. Los
  dos `_num` que quedan en `report/prose.py` pasan a `_cifra`.
- **Los cortes de los resúmenes, por procedencia, con `corte`.** Cada uso de `_num` se clasifica:
  una **observación** va con `cifra`; un **corte del config o efectivo** va con `corte`, exacto. Los
  medidos hoy: el umbral del stepwise (`summaries.py:1229`, hoy dos decimales: un umbral efectivo
  `0.24994` se leería `0,25`), el umbral de deterioro de la tasa en el EDA (`786-793`) y el WoE
  declarado para categorías no vistas (`665`). La implementación clasifica los 39 usos, uno por uno,
  y la clasificación queda en el test que los recorre.
- **Qué texto cambia, censado.** Ningún número cambia; el texto cambia por cuatro causas y sólo por
  ellas: (1) la regla del cero final agrega decimales; (2) un valor bajo 0,001 pasa a dos cifras
  significativas o a `< 0,001` si es un p-valor; (3) un valor desde 1.000 pasa a dos decimales con
  miles —la regla de `cifra`, aunque la frase pidiera uno o ninguno: el AIC `1234,6` se lee
  `1.234,56`, como en las tablas del informe—; (4) una columna entera no declarada deja de
  agruparse. La implementación entrega la tabla antes/después de **cada frase** de los resúmenes
  sobre las corridas F1 e IFRS 9 de la demo y la del YAML SBA, con la causa de cada cambio; un
  cambio sin causa de esa lista es un defecto.
- `methodology._scenario_label` usa `cifras.porcentaje` («Base 33,33 %»).
- El preflight de insumos externos (`ui/routes.py`) escribe los conteos con `conteo` y los nombres
  como lista en prosa, no como `repr`; el mensaje de las fracciones de partición
  (`data/config.py`), con `cifra`.

### D-PAN-4 — El texto de auditoría del motor, legible sin tocarlo

El `detail` de la selección y los valores del rastro del modelo **no cambian** en el motor: son
texto de auditoría, viajan tal cual en `results.json` y en los exports, y `model/step.py` los vuelve
a leer. **El texto legible no se obtiene parseando el `detail`**: el `detail` ya redondeó a seis
cifras significativas (`:.6g`), y con `iv=0.2499402` y `min_iv=0.2499404` diría
`iv=0.24994 < min_iv=0.24994` —una comparación imposible, y un corte que no es el ejecutado—. Se
**compone desde los valores originales**, con **una sola implementación, en Python**
(`bayesrisk.report.cifras.motivo_legible`): el motivo de la fila (`reason`, conjunto cerrado), la
observación de la propia fila (`iv`, `max_abs_corr`, `vif`, a precisión completa) en `cifra`, y el
umbral efectivo de `selection.thresholds` en `corte` —«IV 0,0000295 < mínimo 0,02», «|ρ| 0,93 >
máximo 0,9», «VIF 5,1234 > máximo 5»—; en el rastro del modelo, desde el `valor` estructurado
(`p_value`, `lr_stat`) y el `umbral` de la decisión. **Una razón sin su valor estructurado se
muestra con el `detail` crudo**, sin inventar, y la implementación mide primero que cada razón lo
tenga (si el `vif` de la fila no fuera el de la iteración que excluyó, se eleva). La contribución de
IV del stepwise es una **observación**, no un corte: su seis cifras significativas bastan para
`cifra`. La usan:

- **el informe** (HTML, PDF y Word): la columna `detail` de «Criterios de selección por variable» y
  la de la traza del stepwise se escriben con ella; la tabla sigue siendo la misma;
- **el serializer de la pantalla**, que añade campos **aditivos** a la respuesta de la API
  (`detail_legible` en las decisiones de selección; `umbral_legible` y `valor_legible` en las
  decisiones de la ficha, con `corte` para el umbral —la procedencia manda, como en D-INF— y
  `cifra`/`motivo_legible` para el valor, campo a campo si es anidado). El front muestra el
  campo legible y, si falta (un fixture anterior), el crudo.

**Los rótulos de tramo del EDA**, igual y también en el informe. **La procedencia no se deduce
del rótulo ni de su tipo**: el perfilador guarda el tramo numérico ya como texto
(`eda/univariate._interval_label` → `str`), indistinguible de una categoría literal
`(0.5, 1.25]`. La decide quien la sabe: `_profile_feature` elige el perfil numérico por el dtype de
la columna (`univariate.py:146`), y `UnivariateResult` gana el campo **aditivo**
`numeric_profiles` (las columnas perfiladas como numéricas) —ningún número cambia; `results.json`
gana ese campo—. Sólo los tramos de esas columnas, que produjo `_interval_label` o
`_constant_numeric_label` con forma conocida, se reescriben, con los comparadores **del EDA**,
cerrado a la derecha: `(0.5, 1.25]` → «> 0,5 y ≤ 1,25»; un tramo constante `[a, a]` → «= a». Una sola función,
`core/tramos.rotulo_de_intervalo` (`core/tramos.rotulo_de_rango` es el de OptBinning, cerrado a la
izquierda, y no se reutiliza), que usan **el serializer** (campo aditivo `tramo_legible`; el rótulo
crudo sigue siendo la clave de la fila en `results.json`), **las tablas del informe** que publican
los perfiles (hoy el renderer escribe el rótulo tal cual, `report/renderer.py:1294`) y **el
eje del gráfico de perfiles** (`report/charts.py:893`, hoy `str(record["tramo"])`).

**Gate de catálogo, en los dos sentidos, todo en Python.** Cada `reason` de exclusión tiene su
composición legible y cada composición, su `reason`: un motivo nuevo sin composición → rojo; una
composición sin motivo → rojo. Los **productores** del texto de auditoría se declaran en el test,
por función —los sitios del selector que asignan `detail`/`.detail` (`selector.py:890, 898, 902,
1021, 1207`), `_criterion_detail` (`estimator.py:1615-1622`, que arma `wald_p=…` y `lr_p=…` con
`parts.append` y los une) y el productor de `iv_contribution=…`—, y un censo de `selector.py` y
`estimator.py` exige que ninguna otra función escriba un `detail`: un productor nuevo obliga a
decidir su composición legible. Cada composición, aplicada a una fila real de la demo, da un texto
sin punto decimal ni operador ASCII sin su palabra, y con el umbral idéntico al de
`selection.thresholds`.

### D-PAN-5 — El copy fijo dice lo que la pantalla hace

«Los p-valores de la tabla se muestran con cuatro decimales» se reescribe con la regla real
(«tres decimales; bajo 0,001 se escribe < 0,001»); «Wilson 95 %», «azar (1,0×)», el `{v}%` de la
landing con `porcentaje`, y el texto del slider del formulario con `cifra` (sólo lo que se **lee**:
el campo de entrada no cambia, D-PAN-6).

**Gate de censo del front** (vitest, sobre `web/src`, fuera de tests): prohíbe `.toFixed(`,
`.toExponential(`, `.toPrecision(`, `toLocaleString(` e `Intl.NumberFormat` fuera de
`lib/cifras.ts`, y exige `tickFormatter` en todo `XAxis`/`YAxis` de `components/charts/`. Lo que el
censo no puede ver —un entero interpolado en una plantilla— lo cubre el conteo en la demo viva (§4).

### D-PAN-6 — Qué exige de la demo

El formato de los números se aplica en el front sobre lo que ya traen los fixtures, así que
**D-PAN-1, 2 y 5 se ven en la demo con el deploy, sin recaptura**. **D-PAN-3 y D-PAN-4** cambian o
añaden texto que viaja **dentro** de la respuesta capturada (`summaries`, el rótulo del escenario,
los campos `*_legible`) y el informe de la demo es un archivo capturado: la demo publicada los
muestra sólo tras una **recaptura**, que exige su OK propio (§8). Hasta entonces el front cae al
texto crudo, como hoy.

## 3. Lo que NO cambia

- Ningún número de `results`, de los exports (CSV/XLSX) ni del `data_hash`; ningún `config_hash`;
  ningún artefacto de cálculo; el texto del `detail` y del rastro en el motor.
- **La entrada de números** en el formulario sigue aceptando punto decimal: es la sintaxis del YAML
  y de Python, y el config que se exporta es YAML. Por la misma razón, las `description` de los
  campos que citan un valor de ejemplo del config (`0.02`) lo escriben como se escribe en el YAML.
- Los identificadores (semilla, `config_hash`, años, períodos, números de tramo o etapa).
- La etiqueta cruda de OptBinning que `core/tramos.py` usa **sólo cuando faltan los bordes**: se
  mide en la implementación si aparece en alguna corrida de la demo; si aparece, se eleva.
- Los mensajes de excepción que llegan a `results.error` o a `eda.failed_analyses` (texto del
  motor para diagnosticar; no se reescriben).
- La landing, que ya escribe es-CL a mano (salvo el `{v}%`, D-PAN-5).

**Presupuesto de perillas: cero** (SDD-31 §13). No se configura el idioma de las cifras (cuelga del
idioma del informe, hoy sólo español) ni el número de decimales.

## 4. Evidencia exigida al implementar

1. **Golden** Python ↔ TypeScript en los dos sentidos, con un control negativo en cada lado (un
   caso cambiado en el espejo → vitest rojo; la regla cambiada en Python sin regenerar → pytest
   rojo; restaurados byte a byte → verdes).
2. **Gate de censo del front** y **gate de catálogo** de D-PAN-4, cada uno con su control negativo
   (un `toFixed` inyectado en un gráfico; una plantilla `detail=f"…"` nueva en el selector).
3. **Casos adversariales con prueba propia**: un umbral `0.24994` en la ficha escrito `0,24994`
   (no `0,2499`); un `Decimal` de corte que pasa por el serializer y se escribe igual que en el
   informe; `-0.0` sin signo en las cinco funciones; `2^53 − 1` y `2^53` en `conteo`; una
   categoría literal `(0.5, 1.25]` que **no** se traduce y un tramo numérico **con el mismo rótulo
   literal** que sí, en la pantalla **y en la tabla y el eje del informe**; una exclusión con
   `iv=0.2499402` y `min_iv=0.2499404` escrita con los dos valores distintos; «Malos» con miles en un resumen; el AIC `1234.56`
   escrito `1.234,56`; un umbral efectivo `0.24994` del stepwise y del deterioro del EDA escrito
   `0,24994` en el resumen, junto a una observación cercana; y un control negativo por productor
   del texto de auditoría (cambiar la plantilla de cada uno pone rojo el gate de catálogo).
4. **Conteo en la demo viva**, con las mismas expresiones que la línea base de §0 sobre el texto
   visible y el SVG de Resultados con todas las secciones abiertas —punto decimal
   `(?<![\d.,])\d+\.\d+(?![\d.])`, coma de miles `(?<![\d.,])\d{1,3}(,\d{3})+(?![\d,])`,
   porcentaje sin espacio `\d%`—: tras el deploy, **cero** fuera de campos de entrada e
   identificadores (con la lista de los que queden y por qué); tras la recaptura, cero también en
   los resúmenes y en los textos de auditoría. Además, **ningún tick ni rótulo de eje con más de
   seis decimales** (el riesgo de §5, que las otras expresiones no ven en es-CL), y el mismo conteo
   sobre el HTML del informe de la demo recapturado.
5. El caso `0.24996` junto a su corte `0,25` escrito `0,24996` en el resumen, en la pantalla y en el
   informe; un año de cohorte sin agrupar en un resumen.
6. Los goldens del informe que muevan los resúmenes se re-anclan **probando «sin X» = golden
   anterior** (la trampa de S19): el cambio de hash sale sólo de las frases afectadas.
7. vitest, la suite completa (después de los fixtures, si hay recaptura) y la revisión de Codex
   sobre el código.

## 5. Riesgos declarados

- **Un espejo es una segunda implementación.** Lo contiene el golden, no la disciplina: 2.000
  `float` sembrados más los bordes. Un caso que el golden no cubra puede divergir; por eso el
  conteo en la demo viva es parte del cierre, no un extra.
- **`corte` en los ejes** escribe el tick exacto: si una versión de Recharts generara ticks como
  `0.30000000000000004`, el eje lo escribiría entero. Hoy sus ticks «redondos» salen de
  `decimal.js-light` (Recharts 3.9.2); el conteo en la demo lo vigila.
- **Traducir el `detail` al presentarlo** duplica el conocimiento de sus plantillas, aunque sea en
  Python y en un solo módulo; el gate de catálogo es lo que impide que se desincronicen.
- **La paridad pantalla ↔ informe es la del `float`** (D-PAN-1 c): un `Decimal` con más de 15
  cifras significativas puede escribirse distinto en los dos. Ningún corte del producto las usa.

## 8. Decisiones para Cami

1. **Aprobar la enmienda** (D-PAN-1…6) para programarla.
2. **Recaptura de la demo** para que los resúmenes corregidos (D-PAN-3) se vean publicados:
   **(a)** junto con la próxima release (recomendado: una sola recaptura firma la versión publicada,
   como en la 1.20.0); **(b)** aparte, apenas se integre; **(c)** no recapturar por ahora (la demo
   muestra el front corregido y los resúmenes con la regla anterior).

## 11. Revisión adversarial

**Pasada 1 de Codex (2026-09-27, sobre `3cfc9b2`): `needs-attention`, seis hallazgos, los seis
verificados contra el código y corregidos en el documento.** (1) El informe **sí** publica el
`detail` crudo (el censo previo lo había dado por sólo-pantalla): D-PAN-4 pasa a una sola
implementación en Python que usan el informe y el serializer. (2) La pantalla recibe `float`, no
`Decimal`: paridad declarada y probada hasta 15 cifras significativas (D-PAN-1 c). (3) Los umbrales
de la ficha se habrían escrito como métricas: los escribe el backend con `corte`. (4) Una categoría
con forma de intervalo se habría traducido, y el EDA cierra a la derecha: `tramo_legible` sólo para
un `pd.Interval`, con comparadores propios. (5) El golden no codificaba `-0`, no finitos ni enteros
grandes: entradas tipadas y dominio declarado (y `corte(-0.0)` = `-0,00` se corrige). (6) La
migración de los resúmenes tenía cambios no censados («Malos» perdía los miles; el AIC ganaba
decimales): se conserva la semántica declarada y se censa cada frase con su causa.

**Pasada 2 (sobre `752e334`): `needs-attention`, tres hallazgos, los tres verificados y corregidos.**
(1) Los resúmenes escribían cortes efectivos con `cifra`/`_num` (el umbral del stepwise a dos
decimales): se clasifican por procedencia y van con `corte`. (2) Los tramos del EDA seguían crudos
en la tabla y en el eje del informe: una sola función por tipo, usada por serializer, tablas y
gráfico. (3) El gate de catálogo no veía las plantillas de `_criterion_detail` (`parts.append`): los
productores se declaran por función y se censa que no haya otros.

**Pasada 3 (sobre `a7823e5`, tope de tres alcanzado): `needs-attention`, dos hallazgos, los dos
verificados y corregidos en el documento, sin cuarta pasada.** (1) La procedencia de los tramos del
EDA no la da el tipo: el perfilador ya los guarda como texto; pasa a declararse en
`numeric_profiles`, que escribe quien elige el perfil. (2) El `detail` ya redondeó a seis cifras:
el texto legible se compone desde la observación y el umbral efectivo originales, no parseando.
Estas dos correcciones no tuvieron revisión adversarial propia del documento; la tendrán en la
revisión del código, que es obligatoria al implementar.

**Implementación (S23, 2026-09-27), con lo que se ajustó al programar.** (a) El texto legible del
stepwise en la ficha viaja como un solo campo aditivo, `detalle_legible`, y no como
`umbral_legible`/`valor_legible`: el front ya sabe que el umbral es un corte y lo escribe con
`corte`; lo único que necesita del backend es el `detail`, que no puede componer sin duplicar la
regla. (b) La correlación se escribe «correlación 0,93 > máximo 0,90»: el `|ρ|` del borrador lo
rechaza el lint (carácter ambiguo) y un modelador lee mejor la palabra. (c) Se añadió
`cifras.frente_al_corte`: al componer una comparación, la observación lleva los decimales que la
dejan del lado correcto del corte (con cuatro decimales, `0.249958` frente a `0,24996` se leía
«0,24996 < 0,24996»). (d) El front tiene cuatro formateadores propios cubiertos por vitest y no por
el golden, porque Python no los tiene: `marca` (el tick exacto de un eje), `entero`, `montoCompacto`
y `puntosPorcentuales`. (e) Los módulos que el informe o la capa ui cargan al importarse
(`methodology`, `ui/routes`, `data/config`) importan `cifras` de forma perezosa (D-HASH-5). (f)
`corte(-0.0)` escribe `0,00` y un monto negativo pone el signo antes del símbolo (`-$1.200`).
(g) `.gitattributes` fija LF para `ts`, `tsx` y `css`: con `core.autocrlf` el checkout en Windows
dejaba los guardrails estáticos de vitest leyendo vacío.

**Pasada 1 de Codex sobre el código (sobre `e68be0e`): `needs-attention`, tres hallazgos, los tres
verificados y corregidos.** (1) En la igualdad (`iv == max_iv`), la cifra escrita también tiene que
decir el corte: `frente_al_corte` la extiende hasta el exacto. (2) La contribución de IV sólo
existe en el `detail`, con seis cifras: el motor la registra cuando supera el corte, y si esas seis
cifras no lo muestran no se afirma la comparación (queda el texto del motor); traer el valor exacto
exigiría cambiar la traza, que la enmienda no toca. (3) Los resúmenes escriben la observación
frente a su corte (deterioro de la tasa del EDA, p-valor del stepwise), y el umbral de concentración
de IV como porcentaje exacto (`corte_porcentual`), no redondeado a entero.

**Pasada 2 sobre el código (sobre `d7c092d`): `needs-attention`, un hallazgo, verificado y
corregido.** El panel del análisis exploratorio escribía la observación de estabilidad sin la regla
de orden junto a su corte. `frente_al_corte` pasa al espejo (`frenteAlCorte`), con 828 casos de
pares observación-corte en el golden, y la pantalla lo usa en ese panel y en los p-valores de la
calibración por grado frente a los dos cortes del semáforo (el mismo defecto, no señalado). Además,
«< 0,001» se conserva cuando ya queda del lado de su corte. La ficha emite `detalle_legible` siempre
(`null` si no aplica) y el espejo D-GOB-16 lo declara como clave de presentación, no del modelo.
Las salidas del cuaderno publicado se regeneraron: sus cambios caen todos en las cuatro causas de
D-PAN-3.

## 13. Simplicidad (SDD-31)

- **Entrada mínima**: ninguna nueva.
- **Qué NO se configura**: el idioma de las cifras, el separador de miles, el número de decimales,
  el formato de los ejes.
- **Perillas**: cero; se retira una constante (`MONEY.thousands`).
- **Resúmenes**: los mismos textos, con la regla del informe en sus cifras.
- **Cinco cifras**: sin cambios numéricos; su texto sigue la regla.
- **Tres puertas**: la guiada (resúmenes, D-PAN-3), la completa (el informe, que gana los textos
  de auditoría, D-PAN-4) y la de pantalla (D-PAN-1, 2, 4, 5) quedan con una sola convención.
