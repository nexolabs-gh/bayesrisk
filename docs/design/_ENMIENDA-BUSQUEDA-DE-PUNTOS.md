# Enmienda — la búsqueda de puntos no confunde un redondeo de máquina con un tramo no visto

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda a [`09-scorecard.md`](09-scorecard.md) (la búsqueda de puntos del escalador y el evento `bin_no_visto`) |
| **Decisiones** | **D-BPT-1** (cómo casa un WoE con su fila de puntos), **D-BPT-2** (qué dice el trail) |
| **Módulos** | `bayesrisk.scorecard.scaler` |
| **Fase** | F1 (pipeline estable, serie 2.x) |
| **Estado** | **Propuesta** (S25, 2026-09-28). Revisión de Codex pendiente; sin aprobar, sin programar |
| **Depende de** | D-NOV-1 (la búsqueda es la que congela la referencia de una categoría no vista), D-FAL-1, D-CPY-3 |
| **Release** | Con redondeo a entero —el default y el de todos los presets— **no cambia ningún número**, medido; con `rounding_method="none"` los puntos de una fila observada pasan a ser exactamente los de su tramo (hoy difieren en el orden de 1e-14). El trail deja de registrar falsas alarmas: cambia el trail de toda corrida |
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

Dos lecturas:

1. **Ningún número cambia hoy** con redondeo a entero: la fórmula con el WoE a un ulp da el mismo
   entero que la tabla. La paridad corrida–bundle (el bundle puntúa por tramo) se sostiene.
2. **El trail miente**: dice que 43.774 operaciones observadas —todas— cayeron en un tramo «no
   visto» y se puntuaron «por fórmula». Ese evento llega al libro «Decisiones» del Excel y al anexo
   de decisiones del informe. Es exactamente el ruido que esconde la alarma verdadera —un WoE que
   de verdad no tiene fila—. Con `rounding_method="none"` además los puntos de la corrida y los del
   bundle difieren en ~1e-14.

## 1. D-BPT-1 — cómo casa un WoE con su fila de puntos (Cami decide, §5.1)

- **(a) Tolerancia de máquina — recomendada.** Un WoE casa con la fila de su variable cuyo WoE
  difiere en a lo sumo **1e-12** (absoluto; constante, no perilla); si más de una fila queda
  dentro, gana la **primera** en el orden de la tabla —la misma regla que hoy resuelve los WoE
  duplicados y la referencia de D-NOV-1—. La fila recibe sus puntos publicados, con su ajuste
  manual y su redondeo. Sólo un WoE sin ninguna fila a 1e-12 va por fórmula y se registra. 1e-12
  está cuatro órdenes por encima del ruido medido (2,2e-16) y nueve por debajo de la distancia entre
  dos tramos reales: el par de WoE distintos más cercano mide 0,0059 en el SBA (`empleos_apoyados`)
  y 0,0051 en el preset (`antiguedad_meses`).
- **(b) En la fuente.** `WoEBinner.transform` escribe el WoE **de la tabla** por tramo en vez del
  que recalcula OptBinning. Limpia todo aguas abajo, pero mueve un ulp el WoE de todas las filas de
  toda corrida —y con él la PD y las métricas en el último decimal—: la proyección canónica del
  preset y la demo dejan de ser bit a bit; exige declararlo y probablemente recapturar.
- **(c) No hacer nada**: documentar que `bin_no_visto` cuenta también diferencias de un ulp.

Por qué (a): corrige el trail sin mover ningún número por defecto, deja una sola regla de
búsqueda para corrida, bundle y referencia de no vistas, y la alarma vuelve a significar algo.

## 2. D-BPT-2 — qué dice el trail

`bin_no_visto` se registra sólo para los WoE sin fila a 1e-12, con el mismo payload de hoy. En el
SBA y en el preset desaparece (se espera 0 eventos; se mide). Ningún evento nuevo: casar dentro de
la tolerancia no es una decisión, es la definición de «su tramo».

**Qué no cambia**: la tabla de puntos, el bundle (ya puntúa por tramo), la referencia de D-NOV-1
(ya lleva el WoE exacto de la tabla), la fórmula para un WoE de verdad sin fila, el redondeo y los
ajustes manuales.

## 3. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 5.1 | La búsqueda | (a) tolerancia 1e-12; (b) WoE de la tabla en la transformación; (c) nada | **(a)** |

## 6. Estrategia de tests (borrador)

- una fila con el WoE de su tramo más un ulp recibe los puntos del tramo y **no** registra
  `bin_no_visto` (nace rojo);
- un WoE a más de 1e-12 de toda fila sigue yendo por fórmula y se registra;
- dos filas dentro de la tolerancia: gana la primera, también con un override en la segunda;
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
- **Cinco cifras**: sin cambio (medido: 0 puntos distintos con redondeo a entero).

## 8. Revisión adversarial de este documento

Tope declarado: tres pasadas. Criterio de parada: la pasada 3 no tumba una premisa. Un hallazgo
contractual no se programa: se eleva.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
