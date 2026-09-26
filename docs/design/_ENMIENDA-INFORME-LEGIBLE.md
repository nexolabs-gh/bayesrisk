# Enmienda corta del informe — cifras que se leen y un ancho que usa la pantalla

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda de **presentación** del informe generado (HTML, PDF, Word y `.qmd`). No toca el motor, el config, `results`, los exports de datos ni ninguna identidad |
| **Decisiones** | **D-INF-1…4** y dos **elevaciones** que no entran (§6) |
| **Módulos** | `nikodym.report` (`renderer`, `charts`, `docx`, `prose`, `templates/`) |
| **Fase** | F1 |
| **Estado** | **Propuesta** (S22, 2026-09-26). Cami eligió «enmienda corta y código ahora» con aprobación antes de programar |
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
| Pantalla de 2.560 px | la caja del documento se queda en **1.360 px** y la columna de contenido en **756 px**; 10 de las 45 tablas no caben y se desplazan dentro de su caja (la más ancha pide 1.700 px) |
| Celular de 375 px | la página mide **825 px** de ancho: se desplaza entera hacia el lado |

**La causa del celular no son las tablas** —esas se desplazan dentro de su propia caja, como
promete el CSS—, sino las dos listas del resumen de la corrida (`dl.summary-files` y
`dl.summary-states`): su rejilla `minmax(150px, 260px) 1fr` deja la columna del valor en 59 px y
una ruta de archivo, que no tiene dónde partirse, la empuja hasta 388 px.

**La regla de 2026-07-20 tenía una razón que ya no se sostiene.** El punto decimal se conservó para
que las tablas se pudieran copiar a una herramienta de análisis. Hoy esas cifras crudas tienen tres
caminos mejores que copiar HTML: `results.json` de la corrida, los libros por etapa de
`export_excel()` y las tablas de la puerta guiada (`TablaDeEtapa`, números intactos). Y el informe es
copy público: una persona lo lee, y lo lee junto a una prosa que ya dice `23,80 %` y `30.316`.

---

## 1. D-INF-1 — Todo número que el informe imprime va en es-CL, y ninguno cruza un corte

Una sola función de formato, compartida por las tablas, las listas de clave y valor, los bloques del
anexo de parámetros, el linaje y los gráficos. Sus decimales base son los de los resúmenes por
etapa (D-FLU), no una regla nueva:

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
representación exacta (la más corta que reproduce el float, `repr`, como `prose._cut`).

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
(`0,125` frente a un p-valor `0,1251`, que se escribiría `0,125`) sigue pudiendo coincidir: por eso la prosa conserva que *el color de cada grado se decidió sobre el valor exacto*,
y el veredicto de cada fila sigue escrito en su propia columna.

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

- **Un eje de coeficientes de `3e-09` se rotularía `0,00`** en todas sus marcas. Las marcas del eje
  pasan a escribirse con los decimales base del eje y, si la marca no es exacta con ellos, con los
  que necesite (tras limpiar el ruido de coma flotante del localizador con un redondeo a 12
  decimales), con la misma notación científica bajo una millonésima.
- **`Brier=0.0004` se leería `0,000`, y un corte configurado `0,125` se leería `0,12`.** Brier y
  ECE pasan por la función de §1 (`0,00040`); los umbrales de las leyendas se escriben **exactos**,
  como `prose._cut` escribe los cortes en la prosa (`0,125`, `0,10`, `0,25`).

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

## 3. D-INF-3 — En una pantalla grande, el informe usa el ancho

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
  `0,00`; `Brier=0.0004` se escribe `0,00040`.
- **Ancho**, medido en el navegador interno sobre el informe del SBA en 375, 768, 1.440, 1.920 y
  2.560 px: ancho desplazable = viewport, tablas que se desplazan dentro de su caja antes y
  después. Se guarda como evidencia; el CSS no tiene prueba unitaria que valga como oráculo.
- **Controles negativos**: (a) devolver `.6f` en `_format_float` pone rojo el censo de puntos
  decimales; (b) quitar la regla de dos cifras significativas pone rojo el caso `0.000015`;
  (c) agrupar todos los enteros pone rojo el año de `tramo`; (d) quitar el `dl` a una columna deja
  el celular en 825 px, medido; (e) quitar la regla del cero final pone rojo el PSI `0.24996`.
- **PDF**: el del SBA antes y después, con su número de páginas y las tablas apaisadas revisadas
  una a una en el render.
- Suite completa sin `-W ignore`, `mypy`, `ruff`, y el HTML, el PDF y el Word del SBA abiertos.

## 8. La revisión adversarial de este documento

Tope declarado: **dos pasadas**, porque es una enmienda de presentación acotada.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (a) **alto**: redondear puede contradecir el semáforo —un PSI `0.24996` se leería `0,2500` frente a su corte `0,25`— y un corte institucional `0.05004` del anexo se leería `0,0500`. (b) **alto**: cambiar sólo el separador de los gráficos deja un eje de `3e-09` rotulado `0,00`, `Brier=0.0004` como `0,000` (usa `.3f`, no `.2f` como decía el texto) y un corte `0,125` en la leyenda como `0,12`. (c) **medio**: `width: 100%` es una regla general que `@media print` no redeclara; poner `width: auto` fuera de pantalla alcanzaría al PDF | (a) §1.1: la regla del cero final, con su garantía y su límite escritos. (b) §1.3: marcas del eje con los decimales que necesiten, Brier/ECE por la función de §1 y umbrales de leyenda exactos. (c) §3: `width: auto` sólo en `@media screen`, y el PDF se compara página a página. Los tres, con casos en §7 |

## 13. Simplicidad (SDD-31) — obligatoria

- **Entrada mínima:** no cambia.
- **Qué NO se configura:** el formato de los números (es-CL, fijo, porque cuelga del idioma y el
  informe sólo se escribe en español), los decimales por tipo de valor y el ancho de la caja.
- **Presupuesto de perillas: CERO.**
- **Resumen por etapa:** no cambia.
- **Las cinco cifras:** idénticas.
