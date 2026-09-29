# Enmienda — Hosmer-Lemeshow dice su magnitud, y las decisiones humanas con motivo viajan en el YAML

| Campo | Valor |
|---|---|
| **Tipo** | Enmienda a [`22-validation.md`](22-validation.md) (Hosmer-Lemeshow: lo que publica y cómo pesa en el estado técnico) y a [`31-simplicidad-y-flujo-guiado.md`](31-simplicidad-y-flujo-guiado.md) / [`_ENMIENDA-FLUJO-GUIADO-SCORECARD.md`](_ENMIENDA-FLUJO-GUIADO-SCORECARD.md) §3.3 (dónde viven las decisiones humanas con motivo) |
| **Decisiones** | **D-HLG-1…3** (Hosmer-Lemeshow con muestras grandes), **D-DEC-1…4** (decisiones con motivo en el YAML) |
| **Módulos** | `bayesrisk.validation` (kernel, evaluador, resultados), `bayesrisk.guided`, `bayesrisk.core.config` (schema y hash), `bayesrisk.core.study`, `bayesrisk.ui` (resúmenes y formulario), `bayesrisk.report` |
| **Fase** | F1 (FASE B del scorecard; serie 2.x). Nace de los hallazgos 5 y 7 de la prueba real de Cami, elevados en [`_ENMIENDA-COPY-PRUEBA-REAL-SBA.md`](_ENMIENDA-COPY-PRUEBA-REAL-SBA.md) §8.1 y §8.2 |
| **Estado** | **Propuesta** (S26, 2026-09-29). Sin programar |
| **Depende de** | D-VAL-13…18 (puerta por grupo de HL, «No evaluable»), D-CPY-6 (brecha media agregada), D-FLU-1…12 y D-GOB-17 (decisiones con autor y motivo), D-EXC-1, D-HASH-* (qué entra al `config_hash`) |
| **Release** | Junto con D-BPT-1…2 en la **2.3.0** (ritmo de Cami del 2026-09-29: cambios chicos juntos). Ningún `config_hash` se mueve. D-HLG: con la opción recomendada, **ningún veredicto cambia**; se suma una tabla y una frase. D-DEC: una sección INFRA nueva en el config, aditiva; el trail de una corrida desde un YAML con decisiones gana esos eventos. Un YAML con `decisions` no lo lee una librería anterior (`extra="forbid"`): declarado |
| **Autor / Fecha** | Claude Code (writer) / 2026-09-29 |

---

## 0. Por qué existe: medido

### 0.1 Hosmer-Lemeshow con muestras grandes (hallazgo 7)

El kernel (`validation/calibration_tests.py:73-138`) ordena por PD calibrada, parte en 10 grupos de
igual tamaño, suma Σ(O−E)²/[E(1−p̄)] y compara con χ² de 8 gl; cualquier rechazo deja el estado
técnico en «Falla» (`results.derive_overall_status`). Los conteos por grupo se calculan y **se
descartan**: nadie ve dónde está la brecha. Medido el 2026-09-29 rehaciendo los grupos del kernel
sobre corridas guardadas (`privado/guiones/medir_hl_por_grupo.py`; el estadístico coincide con el
publicado):

| Corrida · muestra | n | HL · p-valor | PD media vs. tasa | Brecha abs. media ponderada | Brecha máx. por grupo | Grupo que más pesa |
|---|---|---|---|---|---|---|
| SBA · Desarrollo | 30.316 | 59,1 · 7e-10 → **Falla** | 23,80 % vs. 23,80 % | **1,12 pp** | 3,42 pp | g3: 2,94 % obs. vs. 4,62 % pred. (O/E 0,64) |
| SBA · Holdout | 7.733 | 31,9 · 1e-4 → **Falla** | 23,69 % vs. 24,14 % | 1,78 pp | 3,73 pp | g2: 1,16 % vs. 3,27 % (O/E 0,36) |
| SBA · OOT | 5.725 | 224,1 · 5e-44 → **Falla** | 26,11 % vs. 21,76 % | **6,04 pp** | 18,07 pp | g10: 62,4 % vs. 80,5 % |
| Preset F1 · OOT | 1.008 | 19,5 · 0,013 → **Falla** | 23,34 % vs. 23,71 % | 4,22 pp | 9,71 pp | g7: 16,8 % vs. 26,5 % |
| Preset F1 · Desarrollo | 3.961 | 6,0 · 0,65 → Pasa | 23,33 % vs. 23,33 % | 1,23 pp | 2,59 pp | — |

Dos lecturas, y la segunda corrige la premisa del hallazgo:

1. **El p-valor no dice la magnitud.** El mismo «Falla» cubre 1,1 pp de brecha media (Desarrollo
   del SBA) y 6,0 pp con la PD media corrida 4,4 pp (OOT del SBA, deriva real). El usuario sólo ve
   «p-valor < 0,001».
2. **No es sólo «el test es demasiado potente».** En Desarrollo del SBA el rechazo lo empujan los
   deciles de PD baja: 2,9 % observado contra 4,6 % predicho (O/E 0,64), una brecha **relativa**
   grande y **absoluta** chica. Un criterio de materialidad en puntos porcentuales la declararía
   inmaterial; uno relativo, no. Elegir entre los dos es metodología, no copy.

### 0.2 Las decisiones con motivo no viajan en el YAML (hallazgo 5)

Medido el 2026-09-29 (`privado/guiones/medir_decisiones_yaml.py`, cartera sintética,
`sc.exclude("ruido", reason=…)`):

| | Corrida guiada | `to_yaml()` | `bayesrisk.run(loads_config(yaml))` (lo que hace la pantalla) |
|---|---|---|---|
| Decisiones humanas en el trail | **1** (`exclude`, con su motivo) | el motivo **no está**; la exclusión sí | **0**; `Study.preamble` vacío |
| `config_hash` | `h` | — | `h` (idéntico) |

El motivo vive sólo en la memoria del objeto `Scorecard` y en el trail de sus corridas. Quien
recibe el YAML —otra persona, la pantalla, un validador— corre el mismo modelo sin saber que una
variable se excluyó a mano ni por qué; la pantalla dice «Ninguna decisión humana registrada». Y
aunque llegara un preámbulo, `ui/summaries.serialize_summaries` no pasa `decision_lines`
(`final.decisions` sale siempre vacío).

## 1. D-HLG — Hosmer-Lemeshow dice su magnitud (Cami decide, §3)

### 1.1 Lo que dicen las fuentes (cotejo del 2026-09-29, detalle en `privado/evidencia/s26/`)

- **Informar la magnitud junto al p-valor**: respaldado. Kramer & Zimmerman (2007, Crit Care Med
  35:2052; PubMed 17568333): con una desviación de 0,4 % el HL rechaza en el 10 % de las
  simulaciones con n = 5.000 y en el 100 % con n = 50.000; recomiendan mirar observado y predicho
  por decil. Van Calster et al. (2016, J Clin Epidemiol 74:167, §9; 2019, BMC Med 17:230): el
  p-valor no informa ni el tipo ni la magnitud del descalibre. BCBS WP14 (2005, pp. 3, 29, 33, 35):
  el HL supone independencia y se complementa con otros análisis. Guía BCE de modelos internos
  (junio 2026, §330(a)(ii), p. 157): análisis gráfico de la tasa de default frente a la PD por grado.
- **Ajustar el número de grupos con n** (Paul, Pennell & Lemeshow 2013, Stat Med 32:67): la regla
  sólo cubre 1.000 < n ≤ 25.000 (verificado en dos fuentes secundarias; el texto original está tras
  pago) y depende de la tasa de eventos. El SBA (30.316) queda fuera: **se descarta**.
- **Degradar un rechazo inmaterial a «Revisar»**: la **forma** tiene respaldo —EBA/GL/2017/16
  §216-217 (p. 55): los umbrales y las acciones por severidad los predefine la institución; guía
  BCE §52(c) y §55: romper un umbral lleva a investigar y a actuar «si es necesario»; manual EBA de
  validación IRB (EBA/REP/2023/29) §24(c): hallazgos por materialidad—. Pero **ninguna fuente fija
  un corte numérico** de brecha (ni en pp ni como O/E); las instrucciones de validación del BCE
  (2019, §2.5.3.1) usan Jeffreys por grado y no mencionan HL. Un corte sería un default propio de
  la librería, sin anclaje regulatorio, como el semáforo de D-VAL-5.
- **Nattino, Pennell & Lemeshow (2020, Biometrics 76:549)** estandarizan el parámetro de no
  centralidad del HL: una medida de ajuste que no depende de n, con intervalo. Es el camino con más
  fundamento, pero el texto está tras pago y no se verificó si propone una tolerancia: queda como
  trabajo futuro, no como opción.

### 1.2 Opciones

- **(a) Tabla por grupo y la brecha en la frase; el veredicto no cambia — recomendada.**
  - **D-HLG-1**: el kernel devuelve, además de lo que publica hoy, sus grupos: `n`, malos
    observados, esperados (Σ PD), tasa observada, PD media, brecha (tasa − PD, en pp), razón O/E y
    contribución al estadístico. Se publican en una clave aditiva `("validation",
    "hosmer_lemeshow_groups")` —muestra × grupo—, con los mismos grupos que usó el test (no los de
    la curva de confiabilidad, que usa `qcut` y puede diferir).
  - **D-HLG-2**: la línea de HL que falla —resumen de validación, página ejecutiva e informe— suma,
    después del p-valor y de la PD media agregada de D-CPY-6, **el grupo de mayor diferencia
    absoluta** entre tasa observada y PD media (en puntos porcentuales; a igual diferencia, el de
    menor número) con sus dos tasas: «Hosmer-Lemeshow en Desarrollo (p-valor < 0,001; PD media
    agregada 23,8 % frente a 23,8 % observada; la mayor diferencia, en el grupo 8 de 10: 45,6 %
    observado frente a 42,1 % predicho)». No es el grupo de mayor contribución al estadístico —en el
    SBA, el grupo 3, con 1,7 pp y O/E 0,64 (pasada 1 de Codex)—: la frase dice magnitud absoluta y
    la tabla por grupo trae también la razón O/E y la contribución, para que la brecha relativa no se
    esconda. El informe gana la tabla por grupo en el capítulo de validación (una por muestra, 10
    filas) y la pantalla, un desplegable con la misma tabla bajo «Calibración por muestra». Sin causa
    atribuida (D-CPY-6).
  - **D-HLG-3**: corrige una premisa escrita: D-VAL-4 dice «HL bilateral»; el kernel usa, como
    corresponde a un χ² de bondad de ajuste, la cola superior (`chi2.sf`). Se corrige el texto de
    SDD-22, no el código.
  - Por qué: cierra el hallazgo con lo que las fuentes sostienen, no inventa un umbral, no cambia
    ningún veredicto ni número y muestra justo lo que la medición destapó —que la brecha puede ser
    relativa—. El validador ve dónde está la diferencia y firma.
- **(b) (a) más un corte de materialidad**: un HL que rechaza con brecha máxima por grupo bajo un
  corte pasa de «Falla» a «Revisar» (el estado técnico baja de `fail` a `warn`). Exige elegir el
  criterio —absoluto (pp) o relativo (O/E)— y el valor, sin fuente que lo fije: sería un default de
  la librería declarado como tal y, por EBA/GL/2017/16 §217, configurable por la institución (una
  perilla nueva, `validation.calibration.hl_materiality`). Con un corte absoluto de 5 pp, Desarrollo
  y Holdout del SBA pasan a «Revisar» y OOT sigue «Falla»; con uno relativo (O/E fuera de 0,8–1,25),
  los tres siguen «Falla». Cambia veredictos de corridas existentes.
- **(c) Nada**: el hallazgo 7 queda abierto.

## 2. D-DEC — las decisiones con motivo viajan en el YAML

- **D-DEC-1 · Dónde.** Una sección INFRA nueva de primer nivel, `decisions`, en `BayesRiskConfig`:
  una lista **en orden** de registros `{action, columns, reason, author, value}` —`action` ∈
  `exclude`, `keep`, `merge_bins`, `set_bins`; `columns` al menos una; `reason` no vacío; `author` =
  `"usuario"` por defecto; `value`, la **huella exacta del efecto**: las hojas que la decisión dejó
  escritas, tal como hoy van en el `valor` del evento (`binning.exclude_columns`,
  `selection.force_include`/`model.force_include`, o la hoja de `binning.variable_overrides` de la
  variable con sus cortes)—. Entra a `INFRA_SECTIONS`: **fuera del `config_hash`**, porque el efecto
  ya está escrito en las hojas computacionales, que sí entran. `to_yaml()` la vuelca y `loads_config`
  la lee; el round-trip `load(dump(c)) == c` se conserva. **Vacía, no se vuelca** —ni `decisions:
  []` ni `null`— en `Scorecard.to_yaml()`, `dump_config` y `/api/config/to-yaml` (pasada 1 de
  Codex): el YAML de un config sin decisiones queda byte a byte como el de la 2.2.0 y lo sigue
  cargando una librería anterior; uno **con** decisiones no (`extra="forbid"`), declarado. Se
  descarta ponerla en `governance`: esa sección exige `purpose` y obligaría a inventar uno.
- **D-DEC-2 · Una sola fuente, con su historia.** La puerta guiada **agrega** cada decisión a
  `config.decisions` —en vez de a una lista propia— y deja de llevarlas en su preámbulo. El registro
  es **de solo agregar**, como la lista de hoy (pasada 1 de Codex): `exclude(x)` y luego `keep(x)`,
  aun antes de la primera corrida, dejan los dos registros con sus motivos. `Study.run` emite,
  después del preámbulo que reciba (puerta e inferencias), un evento `decision_del_usuario` por
  registro, en el orden del config, con **el mismo payload de hoy** (`regla`, `umbral` vacío, `valor`
  = el `value` guardado, `accion`, `autor`, `motivo`, `variables`), y lo persiste en
  `run_context.preamble`. Así la corrida guiada, `bayesrisk.run(loads_config(yaml))` y la pantalla
  dan el **mismo trail** y la misma ficha, Excel, página ejecutiva e informe.
- **D-DEC-3 · Un registro cuyo efecto ya no está en el config (Cami decide, §3).** Antes de emitir,
  cada registro se coteja con el config, **variable por variable**, contra su huella: se mira sólo
  el **último** registro de cada variable en su familia (`exclude`/`keep`; `merge_bins`/`set_bins`);
  los anteriores son historia y se emiten tal cual. Tres estados: **aplicada** (la hoja del config
  coincide exactamente con la huella: la variable en `binning.exclude_columns`; en `force_include`
  y fuera de las excluidas; los cortes de `variable_overrides` **idénticos** a los guardados);
  **en suspenso** (cortes fijados de una variable que después se excluyó: D-EXC-1 ya los declara;
  se emite como hoy); **sin efecto** (la hoja no está o cambió: un YAML editado a mano —cortes
  `[10, 20]` reescritos a `[15, 25]`— o el formulario de la pantalla). Para el tercero:
  - **(a) Se declara y no se atribuye — recomendada.** No se emite como decisión humana; el motor
    registra `decision_sin_efecto` (con la acción, las variables, el motivo y qué hoja no coincide)
    y el resumen final lo dice como alerta: «La decisión «set_bins monto — motivo» ya no está
    aplicada: sus cortes cambiaron en el config». Es el precedente de `point_override_sin_casar`
    (D-CPY-3): lo que no se aplicó se declara, no se atribuye ni detiene la corrida.
  - **(b) Se rechaza al validar el config**, con un mensaje que nombra el registro. Más estricto,
    pero la pantalla no muestra `decisions` en el formulario (D-DEC-4): quien edite ahí una hoja que
    contradice una decisión quedaría sin forma de corregirlo.
  - **(c) Se emite igual**: atribuiría a una persona algo que el config no hace. Descartada.
- **D-DEC-4 · La pantalla.** `serialize_summaries` pasa las líneas de decisión desde
  `study.preamble`, como ya hace el informe (`decision_lines_from_preamble`): el resumen final deja
  de decir «Ninguna decisión humana registrada» cuando el YAML las trae. El formulario **no** muestra
  `decisions` (no es una perilla: es el registro de algo que se decidió en otra puerta) y la
  conserva en el round-trip `from-yaml`/`to-yaml` aunque se editen otras secciones.

**Qué no cambia (D-DEC)**: el `config_hash` de todo config (medido antes y después con los goldens
de hash); el YAML de un config sin decisiones; `DecisionRecord` y la ficha (D-GOB-17); el Excel
«11 Decisiones» (lee el trail); la regla `decision_del_usuario` y su payload, `valor` incluido; las
inferencias y la entrada de la puerta, que siguen en su preámbulo; que la puerta declare en cada
corrida todas las decisiones acumuladas.

## 3. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 3.1 | Hosmer-Lemeshow con muestras grandes | (a) tabla por grupo y la mayor brecha en la frase, veredicto intacto; (b) (a) más un corte de materialidad configurable que degrada a «Revisar»; (c) nada | **(a)** |
| 3.2 | Un registro de decisión sin efecto en el config | (a) se declara y no se atribuye; (b) se rechaza al validar; (c) se emite igual | **(a)** |
| 3.3 | El resto de D-DEC (sección INFRA `decisions` en orden y con huella, omitida si vacía; una sola fuente; pantalla) | aprobar como está / pedir cambios | **aprobar** |

## 6. Estrategia de tests (borrador)

- D-HLG: el kernel devuelve los grupos y su suma reproduce el estadístico (golden a mano, 10 grupos);
  la clave `hosmer_lemeshow_groups` trae muestra × grupo con los mismos grupos que el test (no
  `qcut`); la frase dice el grupo de mayor diferencia absoluta con sus dos tasas en es-CL, en
  resumen, página ejecutiva, HTML y Word, con un caso donde ese grupo y el de mayor contribución
  difieren (el SBA: 8 y 3); la tabla aparece en el informe y en la pantalla (vitest); ningún
  veredicto ni `n_failed` cambia en el preset (proyección canónica: sólo la clave nueva); control
  negativo: elegir el grupo de mayor contribución en vez del de mayor diferencia.
- D-DEC: `to_yaml()` trae `decisions` con el motivo (nace rojo); `bayesrisk.run(loads_config(yaml))`
  emite las mismas decisiones humanas que la corrida guiada, en el mismo orden (nace rojo: hoy 0);
  el `config_hash` de un config con y sin `decisions` es el mismo, y los goldens de hash no se
  mueven; el YAML de un config sin decisiones no trae la clave y es idéntico al de la 2.2.0 (también
  por `/api/config/to-yaml`); `exclude` y luego `keep` sobre la misma variable antes de correr dejan
  los dos registros y los dos eventos (como hoy); con cortes reescritos a mano, `set_bins` no se
  atribuye; `set_bins` y después `exclude` deja los cortes en suspenso, no «sin efecto»; un
  registro sin efecto no se atribuye, se declara y sale como alerta (o se rechaza, según 3.2); la
  pantalla muestra las decisiones del YAML en el resumen final y el formulario las conserva al
  editar otra sección; la sección no se pinta —los censos de campos visibles, perillas y
  esenciales no cambian—, pero el fixture del schema y el ledger de `option_surface` sí la ven
  (se regeneran y se clasifica como oculta, con su razón).
- Controles negativos: uno por regla, en paralelo (RUNBOOK §6).

## 13. Simplicidad (SDD-31)

- **Entrada mínima**: ninguna nueva. Las decisiones se siguen tomando con `exclude`, `keep`,
  `merge_bins` y `set_bins` y su `reason=`.
- **Qué NO se configura**: el número de grupos de HL (sigue `hl_n_groups`, sin cambio); con (a),
  ningún corte de materialidad; la sección `decisions` no es una perilla y no aparece en el
  formulario.
- **Perillas**: 0 con (a) + D-DEC; 1 con (b) (`hl_materiality`).
- **Resúmenes**: validación gana la mayor brecha en su línea de HL; el resumen final muestra las
  decisiones que trae el YAML y alerta de las que ya no están aplicadas.
- **Cinco cifras**: sin cambio (ninguna línea de usuario, campo visible, perilla con (a), segundo ni
  concepto nuevo).

## 8. Revisión adversarial de este documento

Tope declarado: tres pasadas. Criterio de parada: la pasada 3 no tumba una premisa. Un hallazgo
contractual no se programa: se eleva.

| Pasada | Hallazgo | Qué cambió |
|---|---|---|
| 1 | (high) el registro «sólo vigente» perdía `exclude` si se revertía con `keep` antes de correr; (high) sin huella del efecto, un motivo se atribuía a cortes editados a mano, y un `set_bins` en suspenso pasaba por aplicado; (medium) «la mayor diferencia» nombraba el grupo de mayor contribución (g3, 1,7 pp) y no el de mayor brecha (g8, 3,4 pp); (medium) `decisions: []` rompía la carga del YAML en una librería anterior | Registro de solo agregar con `value` (la huella) y payload intacto (D-DEC-1/2); cotejo por variable del último registro, con aplicada / en suspenso / sin efecto (D-DEC-3); la frase dice la mayor diferencia absoluta y la tabla trae O/E y contribución (D-HLG-2); la sección vacía no se vuelca (D-DEC-1); tests (§6) |
