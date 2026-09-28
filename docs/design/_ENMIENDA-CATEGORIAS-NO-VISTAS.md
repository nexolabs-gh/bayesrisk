# Enmienda — una categoría que no existía en Desarrollo: una sola regla para la corrida y el bundle

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda a [`06-binning.md`](06-binning.md) (§3 y §8: categorías no vistas), a [`09-scorecard.md`](09-scorecard.md) (el bundle y `bin_no_visto`) y a [`_ENMIENDA-PUNTUAR-POBLACION-TTD.md`](_ENMIENDA-PUNTUAR-POBLACION-TTD.md) §7 (cierra el defecto que dejó elevado) |
| **Decisiones** | **D-NOV-1** (la regla), **D-NOV-2** (`binning.cat_unknown`), **D-NOV-3** (el aviso de una predictora que cambia de dominio), **D-NOV-4** (qué dicen las superficies) |
| **Módulos** | `bayesrisk.binning` (`transformer`, `step`, `config`), `bayesrisk.scorecard` (`bundle`, `scaler`), `bayesrisk.guided` (`summaries`) |
| **Fase** | F1 (pipeline estable, serie 2.x) |
| **Estado** | **APROBADA por Cami el 2026-09-28** (S24, interactivo, con la recomendación de los tres puntos de §5): regla del **peor tramo** (5.1 a), `cat_unknown` **sólo vacío** con rechazo al validar y retiro en 3.0 (5.2 a), **alerta de cambio de dominio desde el 10 %** sin excluir sola (5.3 a). Tres pasadas de Codex (tope, §8). **Implementada el 2026-09-28 (S25)**; lo que el código precisó, en §9 |
| **Depende de** | D-TTD-5 (el conteo por muestra ya existe), D-FAL-1 (el precedente de la regla conservadora), D-RAR (categorías raras), SDD-31 |
| **Release** | **Cambia números** de corridas que hoy terminan —las que tienen categorías no vistas en Holdout, OOT o fuera del ajuste— y el resultado del bundle en esas filas ⇒ en 2.x exige la decisión explícita de Cami; minor con cambio declarado en el CHANGELOG |
| **Autor / Fecha** | Claude Code (writer) / 2026-09-28 |

---

## 0. Por qué existe: medido

Medido el 2026-09-28 sobre la muestra SBA 7(a) de la prueba de Cami (49.999 préstamos, partición
por fecha con OOT desde 2008-01-01, 5.725 operaciones OOT), con bayesrisk 2.1.0 y un contrafactual
que reemplaza sólo el WoE de las filas con categoría no vista por el de su peor tramo regular
(el predictor lineal se recalcula con los coeficientes ajustados; nada se reajusta):

| Caso | Filas con categoría no vista | AUC OOT hoy → (a) | KS OOT hoy → (a) |
|---|---|---|---|
| **El YAML de Cami** (excluye `anio_fiscal`) | `programa` 58 OOT + 8 fuera del ajuste; `estado_del_proyecto` 1 Holdout | 0,7865 → 0,7861 | 0,4849 → 0,4840 |
| **La misma corrida con `anio_fiscal`** | `anio_fiscal` **2.620 OOT (45,8 %)**; `estado_del_proyecto` 1 Holdout | 0,7969 → 0,7891 | 0,5006 → 0,4960 |

Dos lecturas:

1. **Una categoría nueva de verdad** (un programa que no existía, un estado nuevo) es poca cosa y
   la regla conservadora apenas mueve las cifras (−0,0004 de AUC): es el caso para el que existe.
2. **Una predictora derivada de la fecha** es otra cosa. Las 2.620 operaciones del año fiscal 2009
   tuvieron una tasa de malos **real de 14,7 %** —frente a 27,7 % del resto de OOT—; hoy reciben el
   promedio (23,8 %) y con la regla conservadora recibirían la de su peor tramo («2007, 2008»,
   36,1 %). Ninguna regla para la categoría acierta, porque la variable mide el tiempo, no al
   deudor. Lo correcto es **excluirla**, y eso es lo que D-NOV-3 tiene que decir a tiempo.

Hoy conviven **tres comportamientos distintos** para la misma fila:

1. **La corrida** le da WoE ≈ 0 (`2,2e-16`, el riesgo promedio de la cartera): OptBinning lo decide
   con `cat_unknown=None` (`optbinning/binning/transformations.py:291-295`).
2. **El escalador** busca los puntos por `(variable, WoE)` exacto: en el SBA ese WoE ≈ 0 calza con el
   WoE 0 de los tramos vacíos `Special`/`Missing` y la fila recibe sus puntos; si no calzara, los
   calcula por fórmula (`bin_no_visto`). Medido: las 58 operaciones OOT con un `programa` nuevo
   reciben **65 puntos**, los de las filas vacías `Special`/`Missing` (WoE 0); con la regla (a)
   recibirían 58, los de «Community Express», su peor tramo.
3. **El bundle** no la puntúa: `scoring_status="not_scorable"` con
   `categoria_no_observada_en_fit` (`scorecard/bundle.py:1287-1292`).

La corrida y el bundle **discrepan** en esas filas (D-TTD §7 lo fijó en un test), y la pantalla
sólo dice «reciben WoE 0, el riesgo promedio» (D-TTD-5). Además:

- **`binning.cat_unknown` sólo funciona vacío.** Un número muere en `transform_bins`
  (`ValueError: cat_unknown must be string if metric='bins'`, validado antes de mirar los datos,
  aunque no haya ninguna categoría nueva); un texto muere antes, en la transformación a WoE. La
  perilla está en el formulario y en el config, y ningún valor distinto del default llega al final.
- **Nada avisa de una predictora que cambia de dominio.** En el SBA, `anio_fiscal` entra como
  predictora con partición por fecha: el año fiscal 2009 no existe en Desarrollo por
  construcción. Sólo se excluyen las columnas `date_col`/`cohort_col`/`partition_col` exactas.

## 1. D-NOV-1 — la regla (Cami decide, §5.1)

Una sola regla, que aplican **igual** la corrida (todas las muestras: Holdout, OOT, fuera del
ajuste) y el bundle:

- **(a) Conservadora — recomendada.** La categoría no vista recibe el WoE de su **tramo de
  referencia**: el tramo **regular** de la variable con **mayor tasa de malos observada** en
  Desarrollo (el de menor WoE; empate → la primera fila regular en el orden de la tabla). Es
  exactamente el criterio de D-FAL-1, ya aprobado para un bin de faltantes sin clase. Se decide en
  «Tramos y WoE», al transformar, porque ahí se fija el WoE de Holdout, OOT y fuera del ajuste que
  consumen después el modelo, la PD, los puntos, la calibración y las métricas (pasada 2 de Codex:
  decidirlo más tarde obligaría a rehacer todo eso). En la vista por tramos, la fila se rotula con
  el tramo de referencia, así que las tablas por tramo cuentan lo mismo que el WoE. El bundle la
  puntúa igual (§1.2) y lo marca con un aviso por fila, no con un rechazo.

  **Límite declarado, el mismo de D-FAL-1**: la regla es conservadora en el **riesgo observado**.
  Con el signo esperado del coeficiente, eso es también el puntaje más bajo de la variable; si el
  modelo invierte el signo —que `sign_policy` ya marca para toda la variable—, el puntaje se
  invierte con toda la variable (pasada 1 de Codex). No se elige por puntos porque los puntos no
  existen cuando se fija el WoE.
- **(b) Riesgo promedio.** WoE 0 en la corrida —lo de hoy— y el bundle pasa a puntuar con los
  puntos que la corrida da a ese WoE: la fila que la búsqueda del escalador resuelve —en el SBA, la
  vacía `Special`/`Missing`, con su ajuste manual y su redondeo si los tiene— o la fórmula si no hay
  coincidencia, **congelada al ajustar** igual que en §1.1 (pasada 3 de Codex: calcular por fórmula
  en el bundle volvería a separarlo de la corrida).
- **(c) No puntuable en ambos.** La corrida deja esas filas fuera de las métricas de su muestra,
  declaradas, como hace hoy el bundle.

Por qué (a): el objetivo del proyecto es «menos créditos que no debieron darse». Una categoría que
el modelo nunca vio es, por definición, riesgo sin evidencia; darle el promedio es optimista, y un
banco chico que puntúa un producto nuevo con el promedio lo aprueba a ciegas. (a) es además la
regla que ya rige los faltantes sin clase, así que el modelador aprende una sola. Su costo, medido
en §0: con categorías nuevas de verdad, −0,0004 de AUC OOT; con una predictora derivada de la
fecha, −0,008 —y ahí la respuesta correcta no es ninguna regla sino excluir la variable, que es lo
que D-NOV-3 avisa—.

### 1.1 Los puntos: los mismos en la corrida y en el bundle

La fila no vista lleva el WoE **exacto** de su tramo de referencia (el número de la tabla, no uno
recalculado), así que el escalador le da los puntos que hoy da a ese WoE: los de la **primera** fila
de la tabla de puntos con ese WoE (`scaler.py`, búsqueda por `(variable, WoE)`), con su ajuste
manual y su redondeo. Eso no cambia para ninguna fila observada. Para que el bundle dé lo mismo:

- al ajustar, el escalador **resuelve y congela** por variable categórica del modelo la fila que su
  propia búsqueda devuelve para el WoE de referencia —`bin_index`, WoE, puntos crudos y puntos
  publicados—; si dos filas comparten ese WoE y un override toca la segunda, la congelada es la
  primera, la misma que usa la corrida (pasada 2 de Codex), y el trail lo registra como hoy registra
  los WoE duplicados;
- un ajuste manual se hace sobre un tramo real; no hay fila «no vista» que ajustar;
- `bin_no_visto` (la fórmula para un WoE sin coincidencia exacta) **no cambia**: sigue cubriendo las
  diferencias de precisión de hoy, y no lo alcanza una fila no vista, que trae un WoE de la tabla;
- la tabla de puntos del informe y el Excel ganan, por variable categórica del modelo, una línea
  «Categorías no vistas → como «<tramo>»».

### 1.2 El bundle: los ya guardados no cambian

Hoy el esquema del bundle es la versión 1 y su manifiesto sólo admite
`treatment_policy.unseen="not_scorable"` (`scorecard/bundle.py:883-890` y el validador de
`:1712-1723`). Cambiar `apply` para todos alteraría bundles ya entregados (pasada 1 de Codex). Se
versiona:

- los bundles nuevos se escriben con **esquema 2**: `treatment_policy.unseen="reference_bin"` y un
  bloque `unseen_reference` por variable categórica del modelo (`bin_index`, WoE, puntos crudos,
  puntos publicados), validado al cargar contra la tabla de puntos congelada del mismo bundle;
- el lector acepta **1 y 2** y despacha por la política declarada: un bundle de esquema 1 sigue
  rechazando la fila con `categoria_no_observada_en_fit`, exactamente como hoy;
- una librería anterior a esta enmienda no lee un bundle de esquema 2 y lo dice («esquema no
  soportado»), que es lo que ya hace con cualquier esquema desconocido; va declarado en el
  CHANGELOG;
- el lineage de `apply` declara el esquema **del bundle cargado**, no la constante del código
  (hoy `bundle.py:526` escribe `_BUNDLE_SCHEMA`): aplicar un bundle de esquema 1 dice esquema 1
  (pasada 2 de Codex).

**Qué no cambia:** Desarrollo (por construcción no tiene categorías no vistas); el ajuste; la tabla
de binning; las variables numéricas (un valor fuera del rango de Desarrollo cae en el primer o el
último tramo, como hoy).

## 2. D-NOV-2 — `binning.cat_unknown`

Hoy sólo funciona vacío. Con una regla declarada, la perilla no tiene caso: el default ya no es
«un número que el modelador tenga que elegir». Se propone:

- el campo **sigue existiendo** (el config F1 es API estable en 2.x) y su único valor válido es el
  vacío, que significa «la regla del motor (D-NOV-1)»;
- cualquier otro valor se rechaza **al validar el config**, con un mensaje que dice por qué —hoy
  muere igual, pero en «Tramos y WoE» y con un error de OptBinning—; no rompe ninguna corrida que
  hoy termine;
- se retira en la próxima mayor (3.0), con la poda de D-SIM.

Presupuesto de perillas: **−1** en la práctica (una perilla que nunca funcionó deja de ofrecerse en
la pantalla).

## 3. D-NOV-3 — el aviso de una predictora que cambia de dominio

La alerta de D-TTD-5 **sigue** para toda variable con al menos una fila no vista, en cualquier
muestra (pasada 1 de Codex: el umbral no la reemplaza). Además, cuando en Holdout, OOT o fuera del
ajuste una variable categórica trae categorías no vistas en una fracción de filas **de esa
muestra** mayor o igual a una **constante de 10 %** (medido: `programa` 1,0 % de OOT —una categoría
nueva de verdad: sólo la alerta de D-TTD-5—; `anio_fiscal` 45,8 % —las dos—; las demos no tienen
categorías no vistas), el resumen de «Tramos y WoE» suma una **segunda alerta, de cambio de
dominio**, y el de la selección la repite si la variable quedó seleccionada:

> «anio_fiscal: el 45,8 % de las operaciones fuera de tiempo trae un valor que no existía en
> Desarrollo. Si la variable se deriva de la fecha, no sirve para predecir fuera de tiempo:
> considera excluirla (`exclude`).»

No se excluye nada solo: excluir es una decisión humana con motivo (D-FLU). No se adivina por el
nombre de la columna.

## 4. D-NOV-4 — qué dicen las superficies

| Superficie | Qué dice |
|---|---|
| Trail | `categoria_no_vista` con `accion="asignar_woe_peor_tramo"` y el tramo de referencia en `umbral` (hoy `asignar_woe_neutral`) |
| Artefacto `("binning","unseen_categories")` | Gana la columna aditiva `tramo_asignado` |
| Resumen «Tramos y WoE» | La alerta de D-TTD-5 dice el tratamiento nuevo: «reciben el riesgo de su peor tramo («2005»)» |
| Bundle (esquema 2) | Puntúa la fila con los puntos de su referencia; `scoring_status="scored"` con aviso `categoria_no_vista_como_referencia`; el manifiesto declara la regla y la referencia por variable. Esquema 1: sin cambios |
| Informe | Anexo con la card; el cuerpo no gana sección |

## 5. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 5.1 | La regla | (a) conservadora; (b) riesgo promedio; (c) no puntuable | **(a)** |
| 5.2 | `cat_unknown` | (a) sólo vacío, rechazo al validar, retiro en 3.0; (b) repararla para aceptar un WoE declarado en corrida y bundle | **(a)** |
| 5.3 | El aviso de dominio | (a) alerta con umbral constante; (b) además excluir automáticamente | **(a)** |

## 6. Estrategia de tests (borrador)

- corrida y bundle dan los mismos puntos a una fila con categoría no vista, en OOT y fuera del
  ajuste (nace rojo: hoy el bundle la rechaza), también **con un override** sobre el tramo de
  referencia, con **empate** de puntos y con redondeo;
- el WoE asignado es el del tramo de mayor tasa de malos, con empate, y la vista por tramos rotula
  la fila con ese tramo; con un coeficiente de **signo invertido** (flag) el límite declarado se
  cumple tal cual (la fila sigue a su tramo);
- dos filas con el mismo WoE y un override en la segunda: corrida y bundle dan los puntos de la
  primera; el lineage de `apply` con un bundle de esquema 1 dice esquema 1;
- un bundle de **esquema 1** guardado antes de la enmienda carga y sigue rechazando la fila; uno de
  esquema 2 con una referencia que no casa con su tabla de puntos no carga;
- la alerta de D-TTD-5 aparece con una sola fila no vista; la de cambio de dominio, sólo desde el
  10 % de la muestra;
- `cat_unknown` numérico o texto se rechaza al validar, con mensaje;
- el aviso de dominio aparece sobre el umbral y no bajo él;
- el test de paridad de D-TTD §7 (`test_paridad_con_el_bundle_y_el_desacuerdo_conocido_en_categorias_no_vistas`)
  se invierte: el desacuerdo desaparece;
- controles negativos de cada uno.

## 13. Simplicidad (SDD-31)

- **Entrada mínima**: ninguna.
- **Qué NO se configura**: la regla, el umbral del aviso.
- **Perillas**: −1 (se retira de la pantalla `cat_unknown`, que nunca funcionó con otro valor).
- **Resúmenes**: «Tramos y WoE» y «Selección» ganan la alerta de dominio.
- **Cinco cifras** (YAML de Cami): AUC OOT 0,7865 → 0,7861, KS 0,4849 → 0,4840 con (a); Gini, caída y PSI se miden al implementar.

## 8. Revisión adversarial de este documento

Tope declarado: tres pasadas. Criterio de parada: la pasada 3 no tumba una premisa. Un hallazgo
contractual no se programa: se eleva.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (high) cambiar `apply` alteraría bundles ya guardados; (high) el menor WoE no siempre es conservador con un signo invertido; (high) sin regla para overrides la corrida y el bundle divergen; (medium) el umbral suprimiría la alerta ya aprobada de D-TTD-5 | Esquema 2 con lector de 1 y 2 (§1.2); referencia por **puntos publicados** (§1); referencia congelada con herencia de override y redondeo (§1.1); la alerta de D-TTD-5 sigue y el umbral suma una segunda (§3); tests nuevos (§6) |
| 2 | (high) la referencia por puntos se decidía después de que el modelo ya calculó la PD de Holdout/OOT; (high) el WoE no identifica la fila de puntos si hay WoE duplicados con override; (medium) el lineage de un bundle de esquema 1 declararía esquema 2 | La referencia vuelve al criterio de D-FAL-1 (menor WoE, fijado al transformar) con el límite del signo declarado como allí (§1); el escalador congela la fila que su propia búsqueda resuelve, y `bin_no_visto` no cambia (§1.1); el lineage toma el esquema del bundle cargado (§1.2); tests (§6) |
| 3 (tope) | (medium) la alternativa (b) calculaba los puntos del bundle por fórmula y podía divergir de la corrida | (b) congela la misma fila que resuelve el escalador (§1). La opción recomendada (a) pasó la pasada sin hallazgos. Revisión cerrada en el tope |

## 9. Lo que el código precisó (S25, 2026-09-28)

Implementada según §1–§4 con la opción (a) de cada punto. Precisiones del código, ninguna
contractual:

1. **Una sola regla para el tramo de referencia.** `binning.transformer._peor_tramo_regular` —fila
   regular con observaciones, sin `Special`/`Missing` ni totales, menor WoE, empate → primera— la
   usan D-FAL-1 (sin cambio de comportamiento) y D-NOV-1. Se fija al ajustar en
   `WoEBinner.unseen_reference_` (`UnseenReference`: variable, etiqueta del motor, WoE de la
   tabla), por variable categórica.
2. **Qué fila es «no vista»** es la misma máscara que ya contaba D-TTD-5 (`_mascara_no_vista`): ni
   vista en el ajuste, ni especial declarado, ni vacía. `transform` le pone el WoE exacto de la
   referencia y `transform_bins`, su etiqueta del motor —la del `bin_frame`, que así cuenta lo mismo
   que el WoE en la selección y la estabilidad—. Un binner ajustado antes de D-NOV transforma como
   antes.
3. **Una sola búsqueda de puntos.** `scorecard.scaler.filas_de_referencia_no_vista` es la regla de
   `PointsScaler.transform` —primera fila por `(feature, woe)`— y la usan el bundle (congela),
   el resumen (línea de la tabla de puntos, que es la del Excel y la pantalla) y el informe.
4. **Bundle esquema 2.** `unseen_reference` es una clave de primer nivel del manifiesto —sólo en
   esquema 2— con `bin_index`, `woe`, `raw_points` y `points` por variable categórica del modelo.
   Al cargar se exige una por categórica, ni más ni menos, y que casen exactos con la regla
   categórica `feature:bin_index` del mismo bundle. Construir un bundle desde un `Study` cuyo
   binning se ajustó antes de D-NOV falla con un mensaje que pide volver a correr: congelar una
   referencia que la corrida no usó volvería a separar corrida y bundle.
5. **La línea del informe es sólo vista**: la tabla `scorecard.scorecard` de `results.json` y del
   CSV no cambia; el campo aditivo `ReportInputBundle.unseen_reference_bins` da el `bin_index`.
6. **Denominadores del aviso de dominio**: Holdout y OOT, sus filas en `data.frame`; fuera del
   ajuste, las filas fuera del ajuste que la TTD incluye —las mismas poblaciones en que se cuentan
   las no vistas—. La selección repite el aviso para las variables con `included` en su tabla.
7. **`cat_unknown`** queda con `ui_widget="hidden"` y la estrategia de Hypothesis sólo genera el
   vacío.

**Medido** (YAML SBA de Cami en un temporal, `config_hash` `08cf3076…` sin cambio): AUC OOT
0,786496 → **0,78612**, KS 0,484854 → **0,483961**, Gini 0,572992 → 0,57224; Holdout AUC 0,864395
→ 0,86438 (una fila de `estado_del_proyecto`); peor PSI 0,1612 → 0,1624. Las 58 filas OOT con
«Rural Loan Initiative» reciben **58** puntos («Community Express») en la corrida y en el bundle
—diferencia de puntaje 0—; antes, 65 y rechazo. Preset F1: `config_hash` `1063d6cf…` intacto y
proyección canónica idéntica salvo el esquema (vacío) de `("binning", "unseen_categories")`, que gana
la columna `tramo_asignado`; su modelo no tiene categóricas, así que su informe no gana la línea.
