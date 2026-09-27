# Enmienda corta del informe — cifras que se leen y un ancho que usa la pantalla

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda de **presentación** del informe generado (HTML, PDF, Word y `.qmd`). No toca el motor, el config, `results`, los exports de datos ni ninguna identidad |
| **Decisiones** | **D-INF-1…4** y dos **elevaciones** que no entran (§6) |
| **Módulos** | `nikodym.report` (`renderer`, `charts`, `docx`, `prose`, `templates/`) |
| **Fase** | F1 |
| **Estado** | **APROBADA por Cami el 2026-09-26** (S22, interactivo). Primero pidió **«resuelve lo de la foto primero»**: el primer punto de D-INF-3 se implementó y se integró solo (§11; `main` `b778ec5`, CI 18/18). Con eso en `main`, aprobó el resto: **«Sí, todo lo que falta (Recomendado)»**, con la regla del cero final. La release 1.20.0 sale cuando todo esté integrado, y con ella la recaptura de la demo (**«Sí, junto con la 1.20.0»**) |
| **Depende de** | D-REP-1…8 (el HTML es la representación canónica), D-MON-5 (la convención numérica cuelga del idioma), D-CPY-4 (p-valores «< 0,001») |
| **Revierte** | La excepción de `1.4.0`: *«las tablas de detalle y los ejes de los gráficos conservan el punto a propósito: son volcado técnico»* (CHANGELOG 1.4.0, comentario en `renderer._format_float`) |
| **Release** | Ningún número, `config_hash`, `data_hash` ni artefacto cambia; sólo el render ⇒ entra en la **1.20.0** como «Corregido» |
| **Autor / Fecha** | Claude Code (writer) / 2026-09-26 |

---

## 0. De dónde sale

Cami revisó el informe de la prueba con el SBA y escribió: *«la del informe que los decimales se
ven mal y que no se adapta bien la documentación a distintos tamaños de pantalla, sobre todo las
muy grandes»*. Todo lo que sigue está medido el 2026-09-26 sobre `f7c149c`, con el informe de la
corrida de la pantalla (`config_hash` `08cf3076…`) abierto en el navegador interno.

| Qué | Hoy |
|---|---|
| Tablas del informe | 47 |
| Celdas con punto decimal (`0.042677`, `452.337071`, `0.000000`) | **2.189** |
| Celdas con coma decimal | 11 (las que ya arma la prosa) |
| Celdas enteras sin agrupar (`30316`, `23102`) | 1.254, de ellas todas las de conteo ≥ 1.000 |
| Celdas `true`/`false` | **214** |
| Columnas numéricas alineadas a la derecha | **0** (la regla `td.num` existe en el CSS y nadie la emite) |
| p-valores en tabla | `0.000000` en los 9 coeficientes; `0.000096` en Hosmer-Lemeshow |
| **Cifras partidas carácter por carácter** (captura de Cami, 2026-09-26) | **874 celdas numéricas en 23 tablas** a 938 px; **765 en 21 tablas** a 1.440 px, y las mismas 765 a 2.560 px |
| Pantalla de 2.560 px | la caja del documento se queda en **1.360 px** y la columna de contenido en **756 px**; 10 de las 45 tablas no caben y se desplazan dentro de su caja (la más ancha pide 1.700 px) |
| Celular de 375 px | la página mide **825 px** de ancho: se desplaza entera hacia el lado |

**La causa del celular no son las tablas** —esas se desplazan dentro de su propia caja, como
promete el CSS—, sino las dos listas del resumen de la corrida (`dl.summary-files` y
`dl.summary-states`): su rejilla `minmax(150px, 260px) 1fr` deja la columna del valor en 59 px y
una ruta de archivo, que no tiene dónde partirse, la empuja hasta 388 px.

**Las cifras partidas son el defecto más visible, y la primera medición no lo vio.** Contaba tablas
que se desbordaban, no tablas **aplastadas**. `tbody td { overflow-wrap: anywhere }` —puesto para
que una celda larga no empuje la tabla fuera de la hoja del PDF— también rige en pantalla, y ahí
le permite al navegador achicar una columna hasta el ancho de un carácter: el ancho mínimo de una
celda que puede partirse en cualquier punto es una letra. Con un encabezado corto (`iv`, `js`),
la columna queda del ancho del encabezado y `0.094802` se escribe en seis renglones. Ocurre en
toda pantalla, porque la caja no pasa de 1.360 px. **El PDF no lo sufre**: renderizado el de la
demo, sus tablas anchas van en hoja apaisada con `white-space: nowrap` y ninguna cifra está partida.

**La regla de 2026-07-20 tenía una razón que ya no se sostiene.** El punto decimal se conservó para
que las tablas se pudieran copiar a una herramienta de análisis. Hoy esas cifras crudas tienen tres
caminos mejores que copiar HTML: `results.json` de la corrida, los libros por etapa de
`export_excel()` y las tablas de la puerta guiada (`TablaDeEtapa`, números intactos). Y el informe es
copy público: una persona lo lee, y lo lee junto a una prosa que ya dice `23,80 %` y `30.316`.

---

## 1. D-INF-1 — Todo número que el informe imprime va en es-CL, y ninguno se hace pasar por un corte

Una sola función de formato, compartida por las tablas, las listas de clave y valor, los bloques del
anexo de parámetros, el linaje, los gráficos y las cifras de la página ejecutiva (§1.4). Sus decimales base son los de los resúmenes por
etapa (D-FLU), no una regla nueva. La única superficie del informe que no pasa por ella es el
**resumen de la corrida**, que reproduce palabra por palabra los resúmenes por etapa de la puerta
guiada (una sola fuente, D-FLU) y sigue su regla; se eleva en §6-3.

| Valor | Base | Ejemplo |
|---|---|---|
| Real, `0,001 ≤ |x| < 1.000` | cuatro decimales, coma | `0.042677` → `0,0427`; `452.337071` → `452,3371` |
| Real, `|x| ≥ 1.000` (tras redondear) | miles con punto, dos decimales | `697376973.922913` → `697.376.973,92`; `999.99999` → `1.000,00` |
| Real, `10⁻⁶ ≤ |x| < 0,001` | **dos cifras significativas** | `0.000015` → `0,000015`; `0.00049` → `0,00049` |
| Real, `0 < |x| < 10⁻⁶` | notación científica con coma, mantisa de dos cifras | `2.3e-09` → `2,3e-09` |
| Cero, también `-0.0` | sin signo | `0,0000` |
| p-valor (columna `p_value`, `pvalue`) | D-CPY-4: `< 0,001` o tres decimales | `0.000096` → `< 0,001`; `0.0342` → `0,034` |
| Entero en una columna **que cuenta** | miles con punto | `30316` → `30.316` |
| Cualquier otro entero | tal cual | `2005` (un año en `tramo`), `20260920` (la semilla) |
| Booleano | D-INF-2 | |
| Ausente, `NaN` | `—` (sin cambio) | |
| `±inf` | sin cambio (`inf`, `-inf`) | |

### 1.1 La regla del cero final: un número redondeado nunca se hace pasar por un corte

🔴 Sobre esa base manda una regla más: **si la cifra redondeada termina en cero y no es el valor
exacto, se agregan decimales hasta que el último no sea cero**; como máximo, se llega a la
representación exacta.

**Qué es «el exacto».** La regla opera en decimal, nunca en binario: el exacto de un `float` es
`Decimal(repr(x))` —la representación más corta que lo reproduce, la misma de `prose._cut`—, y el
de un `Decimal` es **el propio `Decimal`, sin pasar por `float`**. Hoy `_display_scalar` y
`_display_json_value` convierten el `Decimal` de las provisiones a `float` antes de formatear, y
`Decimal("0.24999999999999999999")` se vuelve `0.25`: la regla lo daría por exacto y escribiría
`0,2500`. Con la ruta decimal se escribe `0,24999999999999999999`, y un `Decimal("1E-400")`, que en
`float` es cero, sale `1,0e-400`. El redondeo es al par más cercano (`ROUND_HALF_EVEN`) sobre ese
decimal, para `float` y `Decimal` por igual. **Termina siempre**: el exacto tiene una cantidad
finita de decimales, y al llegar a ella la cifra es el exacto.

| Exacto | Con la base | Con la regla |
|---|---|---|
| PSI `0.24996`, corte de redesarrollo `0.25` | `0,2500` —se lee «en el corte»— | `0,24996` |
| p-valor `0.04996`, corte rojo `0.05` | `0,050` | `0,04996` |
| corte institucional `0.05004` en el anexo | `0,0500` | `0,05004` |
| corte `0.25`, exacto | `0,2500` | `0,2500` (es exacto: no se agrega nada) |
| `0.1` (el float `0.1000000000000000055…`) | `0,1000` | `0,1000` (el exacto es `repr` = `0.1`) |

**Qué garantiza, y qué no.** Una cifra que termina en un dígito distinto de cero, con `p`
decimales, queda **del mismo lado que el valor exacto de todo corte con menos de `p` decimales**:
el corte es múltiplo de `10^-(p-1)`, la cifra no lo es, y la cifra es el múltiplo de `10^-p` más
cercano al exacto, así que ningún múltiplo de `10^-(p-1)` cabe entre los dos. Los cortes por
defecto de `validation`, `stability`, `selection` y `binning` tienen una o dos cifras decimales
(`0,01`, `0,02`, `0,05`, `0,10`, `0,25`, `0,50`, `0,75`; medido en sus `config.py`): las cifras de
cuatro decimales respetan cualquier corte de hasta tres, y los p-valores de tres decimales,
cualquiera de hasta dos. Un corte institucional con tantos decimales como la cifra mostrada
(`0,125` frente a un p-valor `0,1251`, que se escribiría `0,125`) sigue pudiendo coincidir: por
eso la prosa conserva que *el color de cada grado se decidió sobre el valor exacto*, y el
veredicto de cada fila sigue escrito en su propia columna.

**Por qué no por tabla.** La alternativa era conocer, celda por celda, contra qué corte se compara
cada cifra (el PSI con sus umbrales de la misma fila, el p-valor con los cortes del semáforo que
viven en el config, el IV con sus bandas…): una lista que hay que recordar ampliar, y que falla en
silencio. La regla del cero final no necesita saber cuál es el corte.

**Lo que cuesta.** Cerca de una de cada diez cifras de cuatro decimales termina en cero, y ésas
salen con uno o más decimales extra (`0,12304` junto a `0,5678`). Es el precio de no afirmar una
igualdad que no existe.

### 1.2 Las demás decisiones de §1

**Por qué dos cifras significativas bajo 0,001.** Con cuatro decimales fijos, 153 celdas del SBA
—componentes del PSI, IV de tramos chicos, JS— se leerían `0,0000` y afirmarían un cero que no es.
Seis decimales, la regla de hoy, lo evitaban a costa de ensanchar todas las columnas. La excepción
cubre justo esas celdas.

**Por qué científica bajo una millonésima.** Una LGD modelada consume el frame crudo (contrato del
proyecto): un coeficiente por peso de monto puede valer `3e-09`, y escribirlo en posicional pide
diez ceros. Mostrar `0,0000` o `< 0,000001` borraría un coeficiente real.

**Qué es una columna que cuenta.** El nombre, sin distinguir mayúsculas, es `n`, empieza por `n_`
o `cum_`, termina en `count` o `_rows`, o es `event`, `non-event`, `observaciones`, `filas`,
`cardinality` u `observed_defaults`. 🔴 La lista va en esa dirección **a propósito**: un conteo que
no esté en ella sale `12345` —legible y correcto—, mientras que agrupar un identificador escribiría
un año `2.005` o una semilla `20.260.920`, que es un error. El SBA trae un año entero en la columna
`tramo` del perfil de `anio_fiscal`; la semilla del linaje pasa por la misma función. Medido sobre
los nombres de columna de `src/nikodym`: los que identifican —`period` (257 apariciones),
`cohort`, `stage`, `seed`, `year`, `*_id`— no casan con la lista.

### 1.3 Los gráficos

Hoy `charts._numeric_formatter` escribe los ejes con dos o tres decimales fijos y punto, y cinco
leyendas redondean con `f"{x:.3f}"` (`Brier=`, `ECE=`) o `f"{x:.2f}"` («Revisión: 0.10 ≤ índice <
0.25», «Redesarrollo: índice ≥ 0.25»). Cambiar sólo el separador dejaría dos defectos:

- **Un eje de coeficientes de `3e-09` se rotularía `0,00`** en todas sus marcas. Las marcas de un
  eje se escriben **todas con los mismos decimales**, los que pide el **paso entre marcas** y nunca
  menos que los base del eje: un paso de `0,05` pide dos, uno de `5e-10` pide diez. Si el paso es
  menor que una millonésima, las marcas van en la notación científica de §1. El ruido de coma
  flotante del localizador (`0.30000000000000004`, o `2.8e-17` donde va el cero) se limpia
  **relativo al paso**, no con un redondeo absoluto: redondear a doce decimales fijos convertía en
  cero todas las marcas de un eje de `3e-13`. Una marca que queda en cero sale sin signo.
- **`Brier=0.0004` se leería `0,000`, y un corte configurado `0,125` se leería `0,12`.** Brier y
  ECE pasan por la función de §1 (`0,00040`); los umbrales de las leyendas se escriben **exactos**,
  como `prose._cut` escribe los cortes en la prosa (`0,125`, `0,10`, `0,25`).

### 1.4 La prosa del informe que escribe un corte o una métrica junto a su banda

La página ejecutiva (`prose.executive_view`, que el HTML, el PDF y el Word pintan igual) escribe
AUC, KS, Gini y el PSI con `_num(..., decimals=4)` junto a su banda, y la nota de umbrales con
`_num(..., decimals=2)`: un PSI `0.24996` sale `0,2500` con la banda de revisión, y un umbral
configurado `0.125`, `0,12`. Dos cambios:

- Las cifras de la página ejecutiva pasan por la función de §1, con la regla del cero final.
- **Toda frase del informe que escribe un corte del config lo escribe exacto**, con `prose._cut`,
  la regla que ya usan los cortes del semáforo de calibración: la nota de umbrales de la página
  ejecutiva y las frases de metodología que citan el IV mínimo y máximo, el umbral de
  correlación, los cortes del PSI, el nivel de significancia y los p-valores de entrada y salida
  del stepwise. Con los valores por defecto el texto no cambia: `_cut` escribe `0,10`, `0,25`,
  `0,05` y `0,02` igual que `_num(..., decimals=2)`.

El resto de la prosa —conteos, porcentajes, montos, el VIF máximo— no cambia: no compara una
cifra con un corte.

**La prosa que describe la tabla se corrige.** `prose.py` dice hoy *«Los p-valores de la tabla se
muestran redondeados a seis decimales»*; pasa a decir que se muestran con tres decimales, `< 0,001`
bajo ese corte y con los decimales que hagan falta para no confundirse con un corte, y conserva que
el color de cada grado se decidió sobre el valor exacto.

## 2. D-INF-2 — `sí`/`no` y columnas numéricas a la derecha

- Un booleano en una tabla o una lista se escribe `sí` o `no`, como en los resúmenes. En los
  bloques JSON del anexo de parámetros sigue siendo `true`/`false`: ahí es sintaxis, no copy.
- Una columna cuyos valores presentes son todos números (no booleanos) se alinea a la derecha con
  cifras tabulares: en el HTML y el PDF con la clase `num` que el CSS ya define, y en el Word con la
  alineación del párrafo de la celda. El encabezado se alinea con su columna.

## 3. D-INF-3 — En pantalla, una cifra no se parte y el informe usa el ancho

- 🔴 **Una cifra nunca se parte, y una palabra sólo entre palabras.** En `@media screen`, las
  celdas y los encabezados vuelven a `overflow-wrap: normal` y las columnas numéricas (D-INF-2)
  llevan `white-space: nowrap`. Una tabla que no cabe se desplaza **dentro de su caja**, que es lo
  que el CSS ya prometía. El PDF conserva su `overflow-wrap: anywhere` (en el papel no hay
  desplazamiento) y su hoja apaisada. Simulado sobre el informe del SBA a 938 px: **0 celdas
  numéricas partidas** (hoy 874), la página sin desplazamiento lateral, y los textos largos
  («Sin alertas», «Fuera de tiempo (OOT)») en dos renglones, entre palabras.
- La caja del documento pasa de `max-width: 1360px` a **`1920px`**. En 2.560 px la columna de
  contenido crece de 756 px a ~1.316 px.
- El índice de la derecha («En esta página») aparece desde **1.600 px** y no desde 1.080 px. Sus 13
  enlaces son los capítulos que el índice de la izquierda ya lista entre sus 41; en un portátil de
  1.440 px esos 236 px valen más para las tablas.
- En pantalla, una tabla toma **el ancho de su contenido** (`width: auto`), no el de la columna: con
  una columna de 1.316 px, una tabla de tres columnas estirada al 100 % se lee peor que hoy. La
  regla va **dentro de `@media screen`**: hoy `width: 100%` es una regla general que `@media print`
  no redeclara, así que ponerla fuera alcanzaría al PDF.
- La prosa conserva su tope de `68ch`: una línea de texto más larga no se lee mejor.
- Lo que siga sin caber se desplaza **dentro de su caja**, como hoy. No se achica la letra.
- En el PDF no cambia la maquetación de las tablas: siguen a `width: 100%` (la regla general, que
  la de pantalla no toca), con `table-layout: fixed` y la hoja apaisada de `table-block--wide`.
  **Sí cambian** sus cifras (más cortas) y su alineación (D-INF-2), así que el PDF del SBA se
  compara antes y después, página por página, incluidas las tablas apaisadas (§7).

**Por qué 1.920 y no sin tope.** Sin tope, en un monitor ultra ancho las tarjetas de tres columnas
de la portada y del resumen se separarían más de lo que se leen.

**Simulado sobre el informe del SBA** (el formato de §1 y este CSS inyectados en el navegador
interno; se vuelve a medir sobre el código, §7):

| Viewport | Tablas que se desplazan dentro de su caja, hoy | Con D-INF-1…4 |
|---|---|---|
| 1.440 px (portátil) | 10 de 45 | 4 |
| 2.560 px | 10 de 45 | 1 (la de desempeño por tramo, 20 columnas) |

## 4. D-INF-4 — En un celular, la página no se desplaza hacia el lado

- Bajo 720 px, las listas de clave y valor pasan a una columna: la clave arriba y el valor debajo.
- En todo ancho, el valor de una lista puede partirse en cualquier punto (`overflow-wrap:
  anywhere`), como ya lo hace una celda de tabla: una ruta de archivo deja de empujar la página.
- Criterio de cierre, medido en 375 px y en 768 px: el ancho desplazable del documento es igual al
  del viewport. Simulado: 375 → 375 px y 768 → 753 px (el viewport sin barra), frente a 825 px hoy.

## 5. Qué NO cambia

- `results`, `results.json`, los exports CSV/XLSX, los libros de `export_excel()`, el `config_hash`,
  el `data_hash` y el bit a bit de los artefactos computacionales: el formato es sólo render.
- Los encabezados de columna siguen siendo los nombres de `results` (`n_total`, `bad_rate`).
  Traducirlos es otra conversación: tocan el contrato de los nombres públicos de tabla.
- Las tasas siguen escritas como fracción (`0,2380`), no como porcentaje: el encabezado es el
  nombre crudo de la columna y reescalarla por el nombre (`rate`, `pct`) es la heurística que esta
  enmienda retira.
- La maquetación de las tablas en el PDF (§3); sí sus cifras y su alineación.
- `inf` y `-inf`.

## 6. Elevaciones que no entran

1. **La pantalla usa otra convención.** `web/src/lib/results-format.ts` escribe, a propósito y
   comentado, la convención anglo: `formatCount` → `3,961`, `formatMetric` → `0.7534`,
   `formatPercent` → `23.8%`. Tras esta enmienda el informe, los resúmenes y la prosa dirían
   `30.316`, `0,7534` y `23,80 %`, y la pantalla lo contrario. Llevar la pantalla a es-CL es su
   propia enmienda: toca el panel entero y sus pruebas de vitest.
2. **El resumen de la calibración escribe `-0,0000`.** `summaries.py` imprime el desplazamiento del
   intercepto con `_num(..., decimals=4)`; un valor diminuto negativo sale con signo. Es la regla
   de D-INF-1 aplicada a la prosa, que es otra superficie; se anota para la próxima enmienda de
   copy.
3. **Los resúmenes por etapa escriben la métrica junto a su banda con decimales fijos**
   (`_num`, `_pct`), en la puerta guiada, en la pantalla y en el resumen de la corrida del
   informe. La regla del cero final cabe ahí igual que en §1.4, pero cambia la puerta guiada; va
   con la enmienda de la pantalla del punto 1.

**La demo.** `web/src/fixtures/demo/report-f1.html` y `report-ifrs9.html` son informes versionados
de la demo: seguirán con el formato anterior hasta una recaptura, que pide un OK propio de Cami.

## 7. Pruebas y controles negativos

- **Formato**: una prueba por fila de la tabla de §1, más `-0.0`, `Decimal`, un año en `tramo`, la
  semilla del linaje, un conteo agrupado, un p-valor en `validation.calibration` y un booleano.
- **Render**: el informe F1 de prueba no tiene ninguna celda de tabla con punto decimal, ninguna
  `true`/`false` y sí la clase `num` en sus columnas numéricas; el Word alinea a la
  derecha la misma columna. El extractor de celdas se prueba aparte para que no nazca verde.
- **Cortes, a ambos lados** (§1.1): `0.24996`, `0.25`, `0.25004`, `0.04996`, `0.05004` y un
  `repr` de `0.1`, en una celda de tabla, en el anexo y en una leyenda; el cero final nunca se
  agrega a un valor exacto.
- **Gráficos**: el SVG de estabilidad dice `Revisión: 0,10 ≤ índice < 0,25` y, con un corte
  configurado `0.125`, `0,125`; un forest de coeficientes de `3e-09` no rotula ninguna marca
  `0,00`, ni uno de `3e-13`; `Brier=0.0004` se escribe `0,00040`.
- **`Decimal`**: `Decimal("0.24999999999999999999")` → `0,24999999999999999999`;
  `Decimal("1E-400")` → `1,0e-400`; un monto `Decimal("4338485154.07")` → `4.338.485.154,07`.
- **Página ejecutiva**: con un PSI `0.24996` y umbrales configurados `0.125`/`0.25`, la cifra, la
  banda y la nota se leen juntas en el HTML y en el Word: `0,24996`, la banda de revisión, `0,125` y `0,25`;
  con los umbrales por defecto la nota no cambia.
- **Ancho**, medido en el navegador interno sobre el informe del SBA en 375, 768, 938, 1.440, 1.920
  y 2.560 px: **cero celdas numéricas en más de un renglón** (medido con los rectángulos de línea
  de su texto, no con la altura de la fila), ancho desplazable = viewport, y tablas que se
  desplazan dentro de su caja, antes y después. Se guarda como evidencia; el CSS no tiene prueba unitaria que valga como oráculo.
- **Controles negativos**: (a) devolver `.6f` en `_format_float` pone rojo el censo de puntos
  decimales; (b) quitar la regla de dos cifras significativas pone rojo el caso `0.000015`;
  (c) agrupar todos los enteros pone rojo el año de `tramo`; (d) quitar el `dl` a una columna deja
  el celular en 825 px, medido; (e) quitar la regla del cero final pone rojo el PSI `0.24996`;
  (f) volver a pasar el `Decimal` por `float` pone rojo `Decimal("0.24999999999999999999")`;
  (g) redondear las marcas a doce decimales fijos pone rojo el eje de `3e-13`; (h) devolver
  `overflow-wrap: anywhere` a las celdas en pantalla vuelve a partir las 874 cifras, medido.
- **PDF**: el del SBA antes y después, con su número de páginas y las tablas apaisadas revisadas
  una a una en el render.
- Suite completa sin `-W ignore`, `mypy`, `ruff`, y el HTML, el PDF y el Word del SBA abiertos.

## 8. La revisión adversarial de este documento

Tope declarado: **dos pasadas**, porque es una enmienda de presentación acotada.

**Tope alcanzado sin `approve`.** Las dos pasadas encontraron defectos reales, y las correcciones
de la pasada 2 —y el primer punto de D-INF-3, que nació de la captura de Cami después del tope—
quedan **sin revisar por Codex**. Se eleva así a Cami y la implementación abre con
una pasada de Codex sobre el código antes de integrar, como en D-CPY.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (a) **alto**: redondear puede contradecir el semáforo —un PSI `0.24996` se leería `0,2500` frente a su corte `0,25`— y un corte institucional `0.05004` del anexo se leería `0,0500`. (b) **alto**: cambiar sólo el separador de los gráficos deja un eje de `3e-09` rotulado `0,00`, `Brier=0.0004` como `0,000` (usa `.3f`, no `.2f` como decía el texto) y un corte `0,125` en la leyenda como `0,12`. (c) **medio**: `width: 100%` es una regla general que `@media print` no redeclara; poner `width: auto` fuera de pantalla alcanzaría al PDF | (a) §1.1: la regla del cero final, con su garantía y su límite escritos. (b) §1.3: marcas del eje con los decimales que necesiten, Brier/ECE por la función de §1 y umbrales de leyenda exactos. (c) §3: `width: auto` sólo en `@media screen`, y el PDF se compara página a página. Los tres, con casos en §7 |
| 2 | (a) **alto**: la página ejecutiva escribe el PSI con `_num(..., decimals=4)` junto a su banda y los umbrales con `_num(..., decimals=2)`: `0.24996` sale `0,2500` con la banda de revisión y un umbral `0.125`, `0,12`. (b) **alto**: `_display_scalar` pasa el `Decimal` por `float`; `Decimal("0.24999999999999999999")` se vuelve `0.25` y la regla lo daría por exacto. (c) **medio**: redondear las marcas a doce decimales fijos vuelve a rotular cero un eje de `3e-13` | (a) §1.4: la página ejecutiva por la función de §1 y todo corte del config escrito exacto con `_cut`; el resumen de la corrida, que reproduce los resúmenes por etapa, queda declarado y elevado (§6-3). (b) §1.1: la regla opera en decimal; el `Decimal` no pasa por `float`. (c) §1.3: decimales por el paso entre marcas y limpieza relativa al paso. Con casos y controles negativos en §7 |

## 11. Implementado por pedido de Cami: una cifra no se parte en pantalla

Cami respondió a la aprobación con una captura —una tabla del informe del SBA con `0,0948` escrito
en cinco renglones— y **«resuelve lo de la foto primero»**. Se implementó sólo eso, en CSS, sin
adelantar ninguna otra decisión de esta enmienda:

- `overflow-wrap: anywhere` sale de la regla general de `tbody td` y queda en `@media print`, junto
  a la de `thead th` (tema `nikodym`); en el tema `plain`, igual. En pantalla una celda se parte
  sólo entre palabras y una tabla que no cabe se desplaza dentro de su caja; en el PDF, donde no
  hay desplazamiento, la celda y el encabezado siguen partiéndose.
- **Medido en el artefacto** (el HTML del SBA con el CSS nuevo, abierto en el navegador interno;
  se obtiene sustituyendo en el HTML sólo la hoja, porque el golden prueba que el CSS es lo único
  que se mueve): **0 celdas numéricas en más de un renglón** a 375, 938, 1.440 y 2.560 px, frente
  a 874 (938 px) y 765 (1.440 y 2.560 px) antes. Tablas que se desplazan dentro de su caja: 26 a
  938 px, 12 a 1.440 y 2.560 px.
- **Gate**: `test_en_pantalla_una_cifra_no_se_parte_y_en_el_pdf_la_celda_si`, para los dos temas,
  con un parser mínimo de la hoja. **Controles negativos**: devolver `overflow-wrap: anywhere` a
  `tbody td` fuera de `print` → rojo (`[('', 'tbody td')]`) y el golden también; quitarlo de las
  reglas de papel del tema `plain` → rojo. Revertidos con copia y sha256.
- **Golden del HTML** recalculado (`8da29d80…`): sustituyendo en el HTML nuevo la hoja nueva por la
  anterior, el digest vuelve exactamente a `3f0720b6…`.
- **Codex sobre el código, dos pasadas.** La 1 encontró dos defectos reales: la tabla de
  adjuntos —fuera de `.table-block`, con nombres de archivo sin espacios en `<code>`— podía
  ensanchar la página, y el oráculo del test clasificaba `@media not print` como papel. Se
  corrigió con `td code { overflow-wrap: anywhere }` (un nombre de archivo no es una cifra),
  `@media screen { .data-exports, .exec-metrics-slot { overflow-x: auto } }` en los dos temas, y
  un intérprete de la media query (`not`, `only`, listas, anidadas) probado con ocho hojas que
  violan o cumplen el contrato. Medido con un adjunto de nombre largo inyectado: el bloque cabe a
  375, 938, 1.440 y 2.560 px. La pasada 2: **approve**, sin hallazgos.
- **Suite completa** sobre `9cbdfb2`: 7.281 passed, 18 skipped, 0 rojos.
- **Lo que queda igual y ya estaba**: a 938 px la página sigue midiendo 1.097 px de ancho, también
  en el informe original. No son las tablas: son las rutas de archivo del resumen de la corrida,
  el defecto de D-INF-4, que espera su aprobación.

## 12. Implementación del resto (D-INF-1…4) — lo que el código precisó

Aprobado el resto, se implementó en `4a976ef` y `0880276`:

- **Una sola regla**, en `nikodym.report.cifras` (`cifra`, `pvalor`, `corte`, `conteo`,
  `es_columna_de_conteo`, `es_columna_de_pvalor`), que usan el renderer, la prosa, los gráficos y el
  Word. Opera en decimal: el exacto de un `float` es `Decimal(repr(x))` y el de un `Decimal` es él
  mismo. **Con precisión local**: el contexto por defecto de 28 dígitos redondeaba en `quantize`,
  `normalize`, `abs` y `format`, y `Decimal("1E+24")` levantaba `InvalidOperation` (pasada 1 de
  Codex sobre el código); se usan `localcontext`, la tupla del Decimal y `copy_abs`.
- **La prosa, más de lo que decía §1.4.** La pasada 1 mostró que el cuerpo de estabilidad y las
  conclusiones también escribían el PSI con `_num` junto a su banda. Regla final: **toda métrica que
  la prosa del informe escribe junto a una banda o un corte** (PSI, AUC/KS/Gini, IV, correlación,
  VIF, pseudo-R², los parámetros de calibración y del escalado) pasa por `_cifra` con sus decimales
  de siempre como base, y todo corte del config por `_cut` (exacto). Siguen con `_num` sólo el
  rango teórico de puntaje (enteros). `cifra` admite `decimales` para esa base.
- **Conteos.** Los adjuntos ya se agrupaban (`_thousands`); el aviso «mostrando X de Y filas» no, y
  ahora usa `shown_rows_label`/`total_rows_label` en HTML, Word y `.qmd` (los enteros siguen para la
  lógica del Word).
- **Columnas numéricas**: `_table_view` publica `numeric`, calculado sobre las celdas ya con sus
  rótulos públicos; la plantilla emite `class="num"` en `th` y `td`, y el Word alinea a la derecha.
- **Controles negativos**: diez, todos rojos con el defecto y verdes tras restaurar byte a byte
  (`privado/evidencia/s22/cn_dinf.txt`): (a) seis decimales con punto, (b) sin dos cifras
  significativas, (c) todos los enteros agrupados, (e) sin cero final, (f) Decimal por float,
  (g) redondeo absoluto de las marcas, (h) `overflow-wrap: anywhere` en pantalla, (i) el PSI del
  cuerpo con `_num`, (j) el contexto de 28 dígitos, (k) el truncado sin agrupar. El (d), el
  celular, se mide en el navegador.

- **Los identificadores se cortan en sus guiones bajos.** Medido sobre el informe real del SBA
  (el YAML de Cami con el código nuevo: `08cf3076…`, las mismas cifras): sin partir en cualquier
  punto, `antiguedad_de_la_empresa__woe` o `cum_good_capture_rate` fijaban el ancho de su columna,
  y a 1.440 px se desplazaban 10 tablas, no las 4 de la simulación. La plantilla pone un `<wbr>`
  tras cada guion bajo de un encabezado o de una celda de texto: el guion bajo separa las palabras
  de un identificador y una cifra no tiene ninguno. Es la misma regla de D-INF-3 —una palabra se
  parte sólo entre palabras—; sólo en el HTML.
- **El artefacto, medido** (HTML y Word del SBA):

  | | Hoy (`f7c149c`) | Con D-INF |
  |---|---|---|
  | Celdas con punto decimal | 2.189 | **0** (los 489 «30.316» son miles) |
  | Celdas `true`/`false` | 214 | **0** (228 `sí`/`no`) |
  | Cifras partidas en más de un renglón | 874 (938 px) · 765 (2.560 px) | **0** en 375, 768, 938, 1.440, 1.920 y 2.560 px |
  | Ancho de la página en un teléfono de 375 px | 825 px | **375 px** |
  | Tablas que se desplazan dentro de su caja, 1.440 px | 10 | **3** |
  | Ídem, 1.920 y 2.560 px | 10 | **1** (la de 20 columnas) |
  | Word: celdas alineadas a la derecha | 0 | **3.382** |

### 12.1 Codex sobre el código: tres pasadas (tope)

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (a) **alto**: el cuerpo de estabilidad y las conclusiones escribían el PSI con `_num` junto a su banda. (b) **alto**: con el contexto de 28 dígitos, un `Decimal` de 29 cifras se redondeaba a `0,2500` y `Decimal("1E+24")` levantaba `InvalidOperation`. (c) **medio**: conteos sin agrupar —los adjuntos ya lo estaban; el aviso de truncado no— | (a) toda métrica de la prosa junto a una banda o un corte por `_cifra`; (b) `localcontext`, la tupla del Decimal y `copy_abs`; (c) `shown_rows_label`/`total_rows_label` en HTML, Word y `.qmd` |
| 2 | **medio**: el config efectivo del Anexo C pasaba por la regla de p-valores observados: un `entry_p_value` de 0.0005 se leía «< 0,001» | todo número del config se escribe exacto con `corte`, y `es_columna_de_pvalor` excluye los cortes por nombre (`entry_`, `exit_`, `max_`, `min_`, `threshold`, `alpha`, `cut`) |
| 3 | **alto**: las cards repiten cortes del config bajo `thresholds` y se redondeaban junto al config exacto: el mismo corte con dos valores | el corte se reconoce por **procedencia**: la ruta pasa por `effective_config`, `thresholds` o `traffic_light_cuts`, o el nombre es `threshold`, `alpha`, `entry_p_value`, `exit_p_value`, `*_threshold`, `*_alpha` o `*_cat_cutoff`. `ks_cutoff_score` —que contiene «cut»— es un resultado y sigue la regla de las cifras |

**Tope alcanzado.** La corrección de la pasada 3 no la revisó Codex. Queda declarado el límite: un
corte del config que una card repita bajo un nombre fuera de esa lista se escribe con la regla de
las cifras —cuatro decimales y el cero final—, que coincide con el exacto salvo que el corte tenga
más de cuatro decimales. Doce controles negativos, (a)–(c) y (e)–(m), en
`privado/evidencia/s22/cn_dinf.txt`.

## 13. Simplicidad (SDD-31) — obligatoria

- **Entrada mínima:** no cambia.
- **Qué NO se configura:** el formato de los números (es-CL, fijo, porque cuelga del idioma y el
  informe sólo se escribe en español), los decimales por tipo de valor y el ancho de la caja.
- **Presupuesto de perillas: CERO.**
- **Resumen por etapa:** no cambia.
- **Las cinco cifras:** idénticas.
