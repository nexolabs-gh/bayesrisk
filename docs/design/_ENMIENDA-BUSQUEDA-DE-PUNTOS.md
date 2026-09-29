# Enmienda — la búsqueda de puntos no confunde un redondeo de máquina con un tramo no visto, y los ajustes manuales llegan a la corrida

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda a [`09-scorecard.md`](09-scorecard.md) (la búsqueda de puntos del escalador y el evento `bin_no_visto`) |
| **Decisiones** | **D-BPT-1** (cómo casa un WoE con su fila de puntos), **D-BPT-2** (qué dice el trail) |
| **Módulos** | `bayesrisk.scorecard.scaler` |
| **Fase** | F1 (pipeline estable, serie 2.x) |
| **Estado** | **Propuesta** (S25, 2026-09-28). Revisión de Codex pendiente; sin aprobar, sin programar |
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
  fila a 1e-12 va por fórmula y se registra. **Un ajuste manual sobre un tramo que la búsqueda no
  puede distinguir** —su WoE está a 1e-12 o menos del de una fila anterior de la misma variable—
  **se rechaza al ajustar**, con un mensaje que nombra los dos tramos (pasada 2 de Codex): hoy ese
  ajuste llega a la tabla y al bundle, que puntúa por tramo, pero nunca a la corrida. El bin
  asignado de D-FAL-1 no cambia: ya comparte el WoE de su referencia, hereda su ajuste y rechaza uno
  propio. 1e-12
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
  segunda—, a igual distancia la primera; un ajuste manual sobre la segunda se rechaza al ajustar
  con un mensaje que nombra los dos tramos (hoy corre y la corrida lo ignora);
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
