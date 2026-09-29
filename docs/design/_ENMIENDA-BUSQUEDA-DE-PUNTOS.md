# Enmienda — la búsqueda de puntos no confunde un redondeo de máquina con un tramo no visto, y los ajustes manuales llegan a la corrida

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda a [`09-scorecard.md`](09-scorecard.md) (la búsqueda de puntos del escalador y el evento `bin_no_visto`) |
| **Decisiones** | **D-BPT-1** (cómo casa un WoE con su fila de puntos), **D-BPT-2** (qué dice el trail) |
| **Módulos** | `bayesrisk.scorecard.scaler` |
| **Fase** | F1 (pipeline estable, serie 2.x) |
| **Estado** | **APROBADA por Cami el 2026-09-29** (S25, interactivo, con la recomendación de §5.1): opción **(a)**, la fila más cercana a 1e-12 con rechazo al ajustar de un ajuste manual sobre tramos indistinguibles por WoE. Tres pasadas de Codex (tope, §8), las tres con hallazgos reales incorporados. **Implementada el 2026-09-29 (S26)**; lo que el código precisó y lo medido, en §9 |
| **Depende de** | D-NOV-1 (la búsqueda es la que congela la referencia de una categoría no vista), D-FAL-1, D-CPY-3 |
| **Release** | **Cambia números** —y rechaza un caso de config que hoy corre— donde hay ajustes manuales de puntos (`point_overrides`): hoy no llegan a la corrida en los tramos cuyo WoE difiere un ulp de la tabla (medido: 23.565 de 23.565 filas en un tramo del SBA) y pasan a llegar, como ya llegan al bundle y a la tabla publicada. Sin ajustes manuales y con redondeo a entero —los presets y la demo— no cambia ningún número (medido). Con `rounding_method="none"` los puntos de una fila observada pasan a ser exactamente los de su tramo (hoy ~1e-14). El trail deja de registrar falsas alarmas: cambia el trail de toda corrida ⇒ minor con cambio declarado y OK de Cami |
| **Autor / Fecha** | Claude Code (writer) / 2026-09-28 |

---

## 0. Por qué existe: medido

El escalador puntúa cada fila buscando su WoE **exacto** en la tabla de puntos
(`scaler._points_for_values`, clave `(variable, WoE)`); si no lo encuentra, calcula los puntos por
fórmula y registra `bin_no_visto` («calcular_por_formula»). El WoE de la fila lo calcula OptBinning
al transformar y el de la tabla, al construir la tabla: son el mismo número salvo el último bit.

Medido el 2026-09-28 con bayesrisk 2.2.0:

| Corrida | Celdas (fila × variable final) | Por fórmula | \|ΔWoE\| máx. | Puntos distintos a los de su tramo | Corrida vs. bundle |
|---|---|---|---|---|---|
| SBA de Cami (YAML, 43.774 filas modelables, 8 variables) | 350.192 | **285.623 (81,6 %)** | 2,2e-16 | **0** | 0 filas distintas |
| Preset F1 | — | 5 variables con evento, miles de filas cada una | — | 0 | — |
| SBA con un ajuste manual de 7 puntos en «SBA Express» (pasada 1 de Codex) | 23.565 filas del tramo | 23.565 | — | **23.565** (la corrida da 64, la tabla y el bundle 7) | **23.565 filas, 57 puntos** |

Tres lecturas:

1. **Ningún número cambia hoy** con redondeo a entero: la fórmula con el WoE a un ulp da el mismo
   entero que la tabla. La paridad corrida–bundle (el bundle puntúa por tramo) se sostiene.
2. **El trail miente**: dice que 43.774 operaciones observadas —todas— cayeron en un tramo «no
   visto» y se puntuaron «por fórmula». Ese evento llega al libro «Decisiones» del Excel y al anexo
   de decisiones del informe. Es exactamente el ruido que esconde la alarma verdadera —un WoE que
   de verdad no tiene fila—. Con `rounding_method="none"` además los puntos de la corrida y los del
   bundle difieren en ~1e-14.
3. **Un ajuste manual de puntos no llega a la corrida** (pasada 1 de Codex, medido): la fórmula no
   conoce el override. En el SBA sólo 3.582 de 43.774 filas casan exacto; en «SBA Express» ninguna.
   La tabla de puntos, el informe y el bundle dicen 7; el puntaje de la corrida, sus métricas y su
   calibración usan 64. Lo mismo alcanza al bin asignado de D-FAL-1 que hereda un override y a las
   filas observadas del tramo de referencia de D-NOV-1 (las no vistas sí casan: llevan el WoE de la
   tabla). Es un defecto de corrección, no de ruido.

## 1. D-BPT-1 — cómo casa un WoE con su fila de puntos (Cami decide, §5.1)

- **(a) Tolerancia de máquina — recomendada.** Un WoE casa con la fila de su variable **más
  cercana** cuyo WoE difiere en a lo sumo **1e-12** (absoluto; constante, no perilla): una
  coincidencia exacta siempre gana (distancia 0), y sólo ante la misma distancia gana la **primera**
  en el orden de la tabla —la regla que hoy resuelve los WoE duplicados y la referencia de
  D-NOV-1— (pasada 1 de Codex: «la primera dentro de la tolerancia» podía desplazar una exacta). La
  fila recibe sus puntos publicados, con su ajuste manual y su redondeo. Sólo un WoE sin ninguna
  fila a 1e-12 va por fórmula y se registra. **Un ajuste manual sobre cualquier tramo de un grupo
  que la búsqueda no puede distinguir** —dos o más tramos de la misma variable con WoE a 1e-12 o
  menos entre sí, **sea cual sea su posición**— **se rechaza al ajustar**, con un mensaje que nombra
  los tramos del grupo (pasadas 2 y 3 de Codex): sobre el segundo, hoy el ajuste llega a la tabla y
  al bundle pero nunca a la corrida; sobre el primero, la corrida se lo daría también a las filas del
  segundo y el bundle no. El bin asignado de D-FAL-1 no cuenta para el grupo: comparte el WoE de su
  referencia **por construcción**, hereda su ajuste y rechaza uno propio, y corrida y bundle ya le
  dan lo mismo. Los tramos auxiliares vacíos (WoE 0 sin filas) sí cuentan: un regular con WoE
  exactamente 0 y un `Missing` vacío también forman grupo —conservador, declarado—. 1e-12
  está cuatro órdenes por encima del ruido medido (2,2e-16) y nueve por debajo de la distancia entre
  dos tramos reales: el par de WoE distintos más cercano mide 0,0059 en el SBA (`empleos_apoyados`)
  y 0,0051 en el preset (`antiguedad_meses`).
- **(b) En la fuente.** `WoEBinner.transform` escribe el WoE **de la tabla** por tramo en vez del
  que recalcula OptBinning. Limpia todo aguas abajo, pero mueve un ulp el WoE de todas las filas de
  toda corrida —y con él la PD y las métricas en el último decimal—: la proyección canónica del
  preset y la demo dejan de ser bit a bit; exige declararlo y probablemente recapturar.
- **(c) Por identidad de tramo.** La corrida puntúa cada fila observada por el **índice** de su
  tramo —como el bundle—, no por su WoE: sin tolerancia ni ambigüedad, y un ajuste sobre un tramo
  duplicado sí llegaría. Exige publicar el índice de tramo de cada población que se puntúa
  (Holdout, OOT, fuera del ajuste) y pasarlo al escalador: una clave nueva por población y un
  cambio de firma en `PointsScaler.transform`. Es la opción más limpia y la más cara.
- **(d) No hacer nada**: documentar que `bin_no_visto` cuenta también diferencias de un ulp y que un
  ajuste manual no llega a la corrida.

Por qué (a): hace que el ajuste manual que la institución declara llegue al puntaje de la corrida
—hoy sólo llega a la tabla y al bundle— y rechaza a tiempo el único caso que la búsqueda por WoE no
puede resolver, corrige el trail, no toca el modelo (la PD no usa puntos), deja una sola regla de
búsqueda para corrida, bundle y referencia de no vistas, y la alarma vuelve a significar algo. (b)
también corrige los ajustes, pero mueve un ulp todos los WoE de toda corrida y no resuelve los
duplicados; (c) resuelve todo pero cambia la firma del escalador y suma una clave por población:
queda como camino si aparece un caso real de tramos duplicados que la institución necesite ajustar.

**Límite declarado (pasada 2 de Codex).** Sin ajustes manuales, un puntaje crudo a ~1e-14 de un
borde de redondeo puede quedar hoy de un lado por la fórmula y pasar al otro con la fila de la
tabla. No se observó en el SBA ni en el preset (0 celdas), pero es posible: el cambio va hacia el
entero de la tabla publicada y del bundle, y se declara en el CHANGELOG.

## 2. D-BPT-2 — qué dice el trail

`bin_no_visto` se registra sólo para los WoE sin fila a 1e-12, con el mismo payload de hoy. En el
SBA y en el preset desaparece (se espera 0 eventos; se mide). Ningún evento nuevo: casar dentro de
la tolerancia no es una decisión, es la definición de «su tramo».

**Qué no cambia**: la tabla de puntos, el bundle (ya puntúa por tramo), la referencia de D-NOV-1
(ya lleva el WoE exacto de la tabla), la fórmula para un WoE de verdad sin fila, el redondeo y los
ajustes manuales válidos. Un ajuste sobre un tramo indistinguible por WoE, que hoy corre y no llega a
la corrida, pasa a rechazarse al ajustar.

## 3. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 5.1 | La búsqueda | (a) la más cercana a 1e-12 y rechazo del ajuste ambiguo; (b) WoE de la tabla en la transformación; (c) por identidad de tramo; (d) nada | **(a)** |

## 6. Estrategia de tests (borrador)

- una fila con el WoE de su tramo más un ulp recibe los puntos del tramo y **no** registra
  `bin_no_visto` (nace rojo);
- con un ajuste manual en un tramo cuyas filas difieren un ulp, redondeo a entero: la corrida da
  los puntos del ajuste y coincide con el bundle (nace rojo: hoy 57 puntos de diferencia en el
  SBA); también en el bin asignado de D-FAL-1 que lo hereda y en el tramo de referencia de D-NOV-1;
- un WoE a más de 1e-12 de toda fila sigue yendo por fórmula y se registra;
- dos filas dentro de la tolerancia sin ajuste: gana la más cercana —la exacta aunque sea la
  segunda—, a igual distancia la primera; un ajuste manual sobre la segunda **o sobre la primera**
  se rechaza al ajustar con un mensaje que nombra los tramos del grupo (hoy corre y corrida y
  bundle divergen), y un ajuste sobre la referencia de un bin asignado de D-FAL-1 sigue permitido y
  heredado, con corrida, tabla y bundle iguales;
- un puntaje crudo a un ulp de un borde de redondeo, con cada método: la corrida da el entero de la
  tabla y coincide con el bundle;
- con `rounding_method="none"`, corrida y bundle dan puntos idénticos en las filas observadas del
  SBA (nace rojo: hoy difieren en ~1e-14);
- el SBA y el preset: 0 eventos `bin_no_visto`; `config_hash` y proyección canónica del preset sin
  cambios salvo el trail;
- controles negativos de cada uno.

## 13. Simplicidad (SDD-31)

- **Entrada mínima**: ninguna.
- **Qué NO se configura**: la tolerancia (constante con su razón en el código).
- **Perillas**: 0.
- **Resúmenes**: ninguno cambia; el libro «Decisiones» y el anexo pierden el ruido.
- **Cinco cifras**: sin cambio sin ajustes manuales (medido: 0 puntos distintos con redondeo a
  entero); con ajustes manuales cambian —hacia lo declarado—, y se miden al implementar.

## 8. Revisión adversarial de este documento

Tope declarado: tres pasadas. Criterio de parada: la pasada 3 no tumba una premisa. Un hallazgo
contractual no se programa: se eleva.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (high) «la primera dentro de 1e-12» podía desplazar una coincidencia exacta posterior; (high) la ruta por fórmula ignora los ajustes manuales: la regla cambia puntajes enteros donde hay overrides y la cabecera decía «ningún número» | La más cercana gana, la exacta siempre (§1); medido el defecto de los overrides —23.565 filas, 57 puntos— y declarado como cambio de números y como motivo principal (§0, Release, §1); tests nuevos (§6) |
| 2 | (high) con dos tramos del mismo WoE y un ajuste en el segundo, la búsqueda por WoE nunca lo alcanza y el bundle sí; (medium) sin ajustes, un ulp puede cambiar un entero junto a un borde de redondeo | El ajuste ambiguo se rechaza al ajustar (§1 a) y se añade (c) por identidad de tramo como alternativa; el borde de redondeo queda como límite declarado y en la Release; tests (§6) |
| 3 (tope) | (high) el rechazo sólo miraba «una fila anterior»: un ajuste sobre el **primero** de dos tramos indistinguibles también llegaba, en la corrida, a las filas del segundo, y el bundle no | Se rechaza el ajuste sobre cualquier miembro del grupo, sea cual sea su posición; el bin asignado de D-FAL-1 queda fuera del grupo por construcción (§1 a); test con el ajuste en el primero (§6). La premisa —casar a 1e-12 y que el ajuste llegue a la corrida— no cayó. Revisión cerrada en el tope, sin cuarta pasada |

## 9. Implementación (S26, 2026-09-29)

**Lo que el código precisó.**

1. **Una sola búsqueda.** `scaler._fila_mas_cercana` recorre las filas de la variable en el orden
   de la tabla y se queda con la de menor distancia a 1e-12 o menos (comparación estricta: a igual
   distancia no reemplaza a la primera). La usan `PointsScaler.transform` y
   `filas_de_referencia_no_vista` —la referencia de D-NOV-1 que congelan el bundle, el resumen y el
   informe—; con el WoE exacto de la tabla da la primera fila con ese WoE, lo mismo que antes. El
   atributo privado `_point_lookup_` desaparece: `transform` lee `scorecard_`, así que un escalador
   ajustado con la 2.2.0 y guardado sigue transformando. Cada WoE distinto se resuelve una vez por
   variable (memo), no una vez por fila.
2. **El grupo se arma encadenado.** `_rechazar_ajuste_indistinguible` ordena los tramos de la
   variable por WoE y une los vecinos a 1e-12 o menos (enlace simple): si a–b y b–c están a 1e-12
   pero a–c no, los tres forman grupo. Conservador; con el ruido medido (2,2e-16) y los pares reales
   (≥ 0,005) no hay caso intermedio. Corre **antes** de construir las filas de la variable, así que
   un ajuste rechazado no alcanza a dejar su `point_override` en el trail.
3. **El bin asignado de D-FAL-1 queda fuera del grupo con la misma prueba que ya lo hacía heredar**
   (`_reference_row`: etiqueta en `assigned_bins` y una fila anterior con su WoE **exacto**). Un bin
   asignado sin esa fila cuenta como regular.
4. **El mensaje nombra los tramos con su rótulo legible** —el de las tablas del resumen y del
   informe («Faltantes», «Valores especiales», «≥ 50.450 y < 102.230,5»)— en el orden de la tabla,
   y el tramo ajustado; sugiere unir los tramos o quitar el ajuste.
5. **`woe_duplicado` no cambia**: sigue registrando sólo los WoE **exactamente** repetidos (su
   payload y su acción siguen siendo ciertos: a igual distancia gana la primera). Ningún evento
   nuevo (§2).

**Medido** (`privado/evidencia/s26/`, con PYTHONHASHSEED=0 y el código congelado en una copia):

| Corrida | Antes (2.2.0, `1c8d436`) | Después |
|---|---|---|
| Preset F1: `config_hash` | `1063d6cf…` | `1063d6cf…`; proyección canónica **0 diferencias** |
| Preset F1: eventos `bin_no_visto` | 5 (5.697, 5.260, 3.937, 5.623 y 5.641 filas) | **0** |
| SBA de Cami: eventos `bin_no_visto` | 16 (8 variables × modelables y fuera del ajuste) | **0** |
| SBA: puntos distintos a los de su tramo · corrida vs. bundle | 0 · 0 filas | 0 · 0 filas (el puntaje no cambia) |
| SBA con ajuste de 7 en «SBA Express» | 0 de 23.565 filas con 7; bundle ≠ corrida en 23.565 (máx. 57) | **23.565 de 23.565** con 7; bundle = corrida (0) |
| SBA con `rounding_method="none"` | 56.647 celdas ≠ tabla; 8.126 filas bundle ≠ corrida (máx. 2,3e-13) | **0 · 0** |

El WoE de la transformación sigue difiriendo un ulp del de la tabla en las mismas celdas (285.623 en
el SBA): la enmienda no toca el WoE (opción (b) descartada), sólo cómo se casa.

**Tests** (`tests/unit/test_busqueda_de_puntos.py`, 17): un ulp y 1e-13 casan sin evento; el ajuste
llega a un ulp, también al bin asignado de D-FAL-1 que lo hereda; la exacta gana aunque sea la
segunda y el punto medio da la primera; a 0,9e-12 casa y a 1,1e-12 va por fórmula con su evento; un
puntaje a 3e-13 de un borde de redondeo da el entero de la tabla con los tres métodos; el rechazo
sobre el primero o el segundo de un grupo no contiguo, y el grupo de un regular con WoE 0 y los
auxiliares vacíos; de punta a punta con OptBinning real, 0 eventos y corrida = tabla = bundle con
ajuste y sin redondeo. Tres tests cambian de contrato: el ajuste sobre el segundo de dos tramos del
mismo WoE (en `test_scorecard_scaler.py` y `test_categorias_no_vistas.py`) pasa de «manda la
primera» a rechazo, y el de D-FAL-1 que ajustaba el **primero** de dos tramos regulares del mismo
WoE (`test_binning_faltantes_sin_clase.py`, el caso de la pasada 3) pasa a rechazo con el grupo
sin el `Missing` asignado y conserva la herencia sobre una tabla sin gemelo. **17 nacen rojos
sobre `1c8d436`** (la variante sin redondeo de punta a punta
nace verde con la cartera sintética: allí la fórmula a un ulp daba el mismo float; el caso que
nacía rojo es el SBA, medido arriba, y en unidad el WoE a 1e-13).

**Controles negativos** (uno por regla, en paralelo, cada uno en su copia de `src/`): tolerancia 0
→ 13 rojos; «la primera dentro de la tolerancia» en vez de la más cercana → rojo el de la exacta
segunda; sin rechazo → 5 rojos (los tres de grupo y los dos de contrato cambiado); el bin asignado
contando para el grupo → rojo el de D-FAL-1; `bin_no_visto` por cada fila → 6 rojos.
