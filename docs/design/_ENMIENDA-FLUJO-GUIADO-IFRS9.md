# Enmienda SDD — Flujo guiado de IFRS 9 (segunda aplicación de SDD-31; hito H2)

> **Estado: PROPUESTA (S28, 2026-10-02).** Diseño sin código, pendiente de la revisión adversarial
> (tope de tres pasadas) y de la aprobación de Cami, punto por punto en §8. Aprobarla **no programa
> nada por sí sola**: la capa 0 y la A entran en la sesión siguiente, con tests nacidos rojos,
> controles negativos y revisión del código; B y C después, cada una con el OK de su release.
>
> **Base medida:** `main` = `3cc9654` (bayesrisk 2.3.0). Mediciones y scripts en el repo privado,
> `evidencia/s28/ifrs9-mediciones.md` (sobre la línea base de sólo lectura
> `evidencia/s27/ifrs9-linea-base.md`). **Enmienda a:**
> [`31-simplicidad-y-flujo-guiado.md`](31-simplicidad-y-flujo-guiado.md) (lo aplica), SDD-16
> (`provisioning_ifrs9`: una corrección de motor, §3.1), SDD-18 (`survival`: un artefacto aditivo,
> §3.8), SDD-05 (`data`: target y partición nulos en una corrida de cartera, §3.3, si Cami lo
> aprueba), [`_ENMIENDA-HL-Y-DECISIONES-EN-EL-YAML.md`](_ENMIENDA-HL-Y-DECISIONES-EN-EL-YAML.md)
> (dos acciones nuevas en `decisions`, §3.9), SDD-26 (página ejecutiva y supervivencia en el
> informe), SDD-23 y [`_SDD-UI-POR-TRABAJOS.md`](_SDD-UI-POR-TRABAJOS.md) (esenciales, «Avanzado» y
> las preguntas del trabajo IFRS 9), `docs_site/` (cuaderno y guía). **Molde:**
> [`_ENMIENDA-FLUJO-GUIADO-SCORECARD.md`](_ENMIENDA-FLUJO-GUIADO-SCORECARD.md).
>
> **No toca:** las fórmulas de staging, PD marginal, LGD, EAD ni descuento (con el mismo config, la
> ECL es bit a bit la de hoy salvo en el caso defectuoso de §3.1, que deja de terminar con una cifra
> falsa), el `config_hash` del preset F4 (`013e69dc…`) ni el de ningún YAML existente, la garantía
> SemVer 2.x del pipeline F1, CMF, el arnés H9R, D-JUR/D-GOB/D-EST/D-SUB/D-SC/D-VAL/D-HOR. **No
> autoriza** bump, tag, PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **Enmienda** | FLUJO-GUIADO-IFRS9 (D-ECL-0…D-ECL-15) |
| **Módulos** | Puerta guiada nueva `bayesrisk.Ecl` (`guided/`); `guided/summaries.py` (resúmenes de la familia IFRS 9); `provisioning_ifrs9` (corrección IFRS-8); `survival` (coeficientes como artefacto aparte); `data` (target y partición nulos, §8-3); `core/decisions.py` y `DecisionEntry` (dos acciones); `report` (página ejecutiva y curva); `ui/jobs.py` + `web/` (esenciales, preguntas del trabajo, Resultados); `docs_site/` |
| **Fase** | F4 |
| **Depende de** | SDD-31; FLUJO-GUIADO-SCORECARD (molde: `Scorecard`, `summaries`, `decisions`, Excel, página ejecutiva); D-OBL (decisiones institucionales); D-HOR (unidad temporal y horizonte); D-EST-5 (estabilidad del sobre frente al contenido); D-DEC (decisiones en el YAML) |
| **Lo consumen** | El cuaderno «Tu primera provisión IFRS 9», la guía IFRS 9 de `docs_site/`, el trabajo `provisiones_ifrs9` de la pantalla, la demo IFRS 9, H3 («PD + LGD») y H7 (forward y stress) |
| **Release** | Capa 0 + A en un minor (`Ecl` experimental); B + C en el siguiente (§3.15, §8-6) |

## Recomendación ejecutiva

Entregar `bayesrisk.Ecl`, que calcula la provisión IFRS 9 con **lo que el área de riesgo ya tiene
en su archivo de cartera** —fecha de corte, cartera, exposición, LGD, tasa efectiva, mora, marca de
incumplimiento— y **la historia de incumplimientos de esa misma cartera** para su curva de PD
(duración, evento, unidad y horizonte). Nada más se pregunta: lo que hoy obliga a declarar un target
y una partición de scorecard que la ECL no usa (medido: la cifra sale bit a bit igual sin ellos)
desaparece; los cinco defaults de fábrica que hoy no corren se fijan como constantes de la puerta
tomadas del preset F4, que sí corre; y el horizonte de 12 meses se **infiere** de la unidad, porque
dejarlo en su default duplica la ECL en silencio (medido: 6,86 M frente a 3,42 M). Cada etapa habla
en palabras de provisiones —«Cartera», «Curva de PD», «Provisión IFRS 9»—, no con el molde del
scorecard que hoy pinta «578 malos» y muestras Desarrollo/Holdout en una corrida que no las usa. La
decisión PIT/TTC sigue siendo de Cami (§3.6, §8-2); la recomendación es correr TTC **declarado** en
H2 y traer el ajuste prospectivo con H7.

## 0. Qué corrige de lo ya escrito

1. **ROADMAP H2** habla de `nikodym.Ecl`: tras el renombre (D-REN) es `bayesrisk.Ecl`.
2. **«Standalone de verdad» (preset F4, `ui/presets.py:804-808`) no lo es para el usuario:** la
   cadena no consume el scorecard, pero su sección `data` es la del F1 —esquema de 8 columnas de
   consumo, target `bad_flag == 1`, partición por cohorte con OOT 2024Q2—, y el trabajo
   `provisiones_ifrs9` pregunta «¿Qué define a un cliente malo?» y «¿Cómo separas la muestra para
   validar?» (`ui/jobs.py:645`, `:716-717`). Medido: sin las cinco columnas que sólo satisfacen
   ese esquema, F4 no corre (`data` falla por esquema); con target y partición cualesquiera, la ECL
   es la misma (§1.2).
3. **La enmienda IFRS9-HORIZONTE prometía cazar «doce años donde debía haber uno»** y no lo hace
   cuando la curva tiene menos períodos que el horizonte (§1.4, §3.1).
4. **Línea base de S17 y S27:** `provisioning_ifrs9` tiene **48** campos visibles, no 49 (el grep
   contaba los dos ocultos); F4 corre en **4,8–6,4 s**, no 7,6 s; la ruta «PD del scorecard → IFRS 9»
   **sí corre** por código hoy (§1.6).
5. **La pantalla y el resumen de una corrida IFRS 9 pintan el molde del scorecard**
   (`web/src/fixtures/demo/results-ifrs9.json:1003-1096`): «Datos y muestras», «578 malos», tres
   muestras, «la validación formal no está en el config» y cifras vacías; la supervivencia y la ECL
   no tienen resumen («Etapa sin resumen propio.», `guided/summaries.py:507-513`).

## 1. El estado, medido sobre `3cc9654`

### 1.1 Cifras

- **Formulario:** `data` 158, `survival` 24, `provisioning_ifrs9` 48 campos visibles (contador de
  `tests/unit/test_copy_del_formulario.py::_campos_visibles`); el trabajo `provisiones_ifrs9`
  pinta además `report` (33) y `governance` (14): **277**. Ninguna de las dos secciones de cálculo
  declara esenciales ni lleva `ui_essentials_declared`: se pintan enteras.
- **Preset F4:** `done` en 6,36 s (frío) / 4,79 s (caliente) sin informe, 5,37 s con informe HTML.
  Stage 1/2/3 = 5.235 / 477 / 288, EAD 114.325.315, ECL 3.423.116, curva sobre 6.000 operaciones con
  1.502 incumplimientos en 5 años. Su YAML completo tiene **268 líneas**.
- **Contra fábrica:** F4 cambia 7 de 24 hojas de `survival` y 4 de 48 de `provisioning_ifrs9`.

### 1.2 La entrada mínima ya basta para la cifra

Con sólo las 12 columnas que consume la cadena (`duration`, `event`, cuatro covariables, `as_of_date`,
`portfolio`, `ead`, `lgd`, `eir`, `is_default`), esquema vacío, target `event == 1` (o `is_default`)
y partición aleatoria, la corrida es **bit a bit igual a F4** en la curva, el staging, el detalle,
la curva de ECL y el resumen por cartera. La razón está en el código: `survival` con
`pd_source='none'` descarta la columna de partición antes de ajustar (`survival/step.py:168-173`) y
`provisioning_ifrs9` no la lee. Lo único que difiere es la etiqueta `partition` que la curva arrastra
por fila. **Target y partición son inertes para la ECL**, pero `DataConfig` los exige
(`data/config.py:987-1004`) y `RandomSplitConfig.dev_fraction` es `lt=1.0`: no hay forma de
declarar «sin muestras» con el contrato de hoy.

### 1.3 Los defaults de fábrica no corren

Con `survival` y `provisioning_ifrs9` de fábrica (sólo duración y evento declarados) la corrida cae
cinco veces seguidas, cada una al corregir la anterior: `pd_source='model_raw'` exige `model`;
sin horizonte, `DATO-INSTITUCIONAL-SUR-1` aborta; `scenarios.source='forward'` exige
`scenario_weight`; `ead.method='ccf'` exige `drawn`; `time_unit='period'` dispara
`DATO-INSTITUCIONAL-IFRS-7`. El preset F4 corre porque fija todo a mano (`requisitos_incumplidos`
de `ifrs9/config.py:981-1032` ya lo dice: «el árbol ya sabía que los defaults no corren»).

### 1.4 Un defecto del motor: la ECL a 12 meses que cubre toda la curva

Con `time_unit='year'`, horizonte 5 y el default `horizon_12m_periods=12`, la corrida termina
**`done` con ECL 6.863.157** —el doble de 3.423.116— y sólo `FALTA-DATO-IFRS-4`. Causa:
`_horizonte_no_dura_un_ano` (`ifrs9/engine.py:910-913`) devuelve `False` cuando el período 12 no
existe en la curva («los otros dos disyuntos ya lo cubren»), pero desde que el modo A se retiró sólo
queda uno, `H < T_min` (`:886-887`). Con una curva más corta que el horizonte, el «ECL a 12 meses»
suma la curva entera y `FALTA-DATO-IFRS-8` no dispara.

### 1.5 Lo que dicen hoy los resúmenes de una corrida F4

`build_stage_summaries` devuelve sólo `data` («6.000 filas · 578 malos (9,63 %) · 17 columnas»,
«Muestras: Desarrollo 4.024 · Holdout 1.030 · Fuera de tiempo (OOT) 946») y `report`;
`build_stage_summary("survival" | "provisioning_ifrs9")` devuelve el nombre crudo de la etapa y
«Etapa sin resumen propio.»; el resumen final dice «completada», «no corrió: la validación formal no
está en el config», sin cifras ni nada que revisar. Los 578 «malos» son `bad_flag`; la curva usa
1.502 eventos sobre el libro completo (`fit_scope = "poblacion_completa"`). El informe no tiene
página ejecutiva para IFRS 9 (`report/document.py:149-157`, `:382-388`) ni publica ninguna tabla de
la curva (`KEY_TABLES` sin `survival`, `:237`; sólo el volcado de la card en el anexo C.2).

### 1.6 «PD del scorecard» ya corre por código

F1 completo + `survival` con `pd_source` `model_raw` o `calibration` (PD como covariable) +
`provisioning_ifrs9` con `base_pd_source` `term_structure` o `calibration`, sobre el dataset IFRS 9
del paquete: `done` en 5,7–8,6 s, mismo staging, ECL 3.497.316 (+2,2 % frente a la curva propia),
curva ajustada sobre Desarrollo (4.024 de 6.000 filas). Ningún trabajo, preset ni puerta lo ofrece;
exige que **el mismo archivo** traiga las variables del scorecard, su target y las columnas de la
provisión.

### 1.7 La marca de incumplimiento importa

Sin `staging.is_default_col` el Stage 3 baja de 288 a 240 operaciones (las reestructuradas con mora
menor a 90 días vuelven a Stage 1/2) y la ECL baja 1,2 %.

## 2. Lo que ya está construido y no hay que inventar

- `guided/scorecard.py`: el molde completo —carga con huella, preámbulo `puerta_de_entrada` +
  inferencias, candado por carpeta, `run(until=)`/`resume()`, `_registrar_decision` sobre
  `config.decisions`, `summary()`, `export_excel()`, `export()`, `compare()`, `to_yaml()`,
  `_repr_html_`—. `Ecl` reutiliza la maquinaria común; lo que es del scorecard (inferir
  predictoras, frontera OOT, tramos) no se copia.
- `guided/summaries.py`: `StageSummary`, `TablaDeEtapa`, `FinalSummary`, `SummaryContext` y los
  consumidores ya cableados —pantalla (`ui/summaries.py:28-72` → `ResultsTab.tsx:432,1901`),
  informe (`report/builder.py:654-702`, capítulo `kind="summary"`), cuaderno (`_repr_html_`) y Excel
  (`guided/export.py`)—. Falta la familia IFRS 9, no la tubería.
- El preset F4 (`ui/presets.py:843-937`): las secciones `survival` y `provisioning_ifrs9` que corren,
  derivadas por `scripts/derive_ifrs9_preset.py`. Son la base de las constantes de la puerta (§3.5).
- `core/time_units.py::year_fraction`: año, semestre, trimestre, mes, semana y día, en inglés y en
  español; da el horizonte de 12 meses exacto para cada unidad (1, 2, 4, 12, 52, 365).
- `ifrs9/config.py::requisitos_incumplidos` y `survival/config.py::requisitos_incumplidos`: los
  mensajes en idioma de negocio de cada combinación que no corre.
- Los rótulos en español del informe (`report/prose.py:2526-2535`, `methodology.py:36`) y la ficha
  metodológica IFRS 9 (`methodology.py:72`).
- `provisioning_ifrs9.summary` (cartera × etapa con filas, EAD, ECL y cobertura), `.detail`
  (`pd_12m`, `pd_life`, `ecl_12m`, `ecl_lifetime`, `stage` por operación) y `survival.term_structure`
  (`pd_marginal`, `pd_cumulative` por operación y período): las tablas de decisión salen de ahí.
- `survival.estimator.params_`: los coeficientes del modelo de riesgo por período (sin errores
  estándar publicados; §3.8).

## 3. Las decisiones que se proponen

### 3.1 D-ECL-0 — Corrección del motor: el horizonte de 12 meses se verifica contra su duración

`_horizonte_no_dura_un_ano` deja de depender de que el período del horizonte exista en la curva:
con una unidad convertible, el horizonte de 12 meses dura `horizon_12m_periods × year_fraction(unit)`
años, y si eso se aleja de 1 más que la tolerancia vigente (`_HORIZONTE_ANIO_TOL`), dispara
`FALTA-DATO-IFRS-8`. Es la promesa de D-HOR-0 («doce años donde debía haber uno»), no un contrato
nuevo; el caso de una curva mensual de 12 períodos con horizonte 12 sigue sin disparar (12 × 1/12 =
1). **Efecto:** el caso de §1.4 deja de terminar con una cifra falsa y aborta con el aviso (es
gobernable: `fail_on_falta_dato=True` lo detiene). Ningún preset cambia: F4 declara 1. El
recorrido de tests que hoy corren con un horizonte mayor a la curva y unidad convertible se mide al
implementar y se declara.

### 3.2 D-ECL-1 — La puerta guiada `bayesrisk.Ecl` y su entrada mínima

```python
from bayesrisk import Ecl

ecl = Ecl(
    data="cartera_2025_06.parquet",   # una fila por operación a la fecha de corte; ruta o DataFrame
    id="operacion",                   # opcional, como en Scorecard
    as_of="fecha_corte",              # columna con la fecha de corte (un solo valor)
    portfolio="cartera",
    exposure="ead",                   # exposición al incumplimiento, ya calculada
    lgd="lgd",
    rate="tasa_efectiva",             # tasa efectiva ANUAL de cada operación
    days_past_due="dias_mora",
    default="marca_incumplimiento",   # opcional (§8-4)
    duration="anios_observados", event="incumplio", period="year", horizon=5,
    covariates=["dias_mora", "utilizacion", "carga_financiera"],   # opcional
)
ecl.run()                             # corre todo y cuenta cada etapa
ecl.summary()                         # ejecución, supuestos, cinco cifras y qué revisar
```

- **Lo que se pide es sólo lo institucional** (D-SIM-2, D-OBL): las columnas de negocio del archivo
  de cartera y la historia de incumplimientos que alimenta la curva. `duration`/`event` son la
  historia (tiempo observado y si incumplió); `period` es la **unidad** de esa duración —no se puede
  inferir de un entero, y declararla mal cambia la provisión (D-HOR)—; `horizon` es hasta dónde se
  proyecta la curva, que el motor no inventa (`DATO-INSTITUCIONAL-SUR-1`). Si falta `horizon`, la
  puerta se detiene **antes de correr** con el máximo observado y el valor que usaría («tus datos
  observan hasta 5 años: con `horizon=5` la curva llega hasta ahí»), como la frontera OOT del
  scorecard.
- **Lo que se infiere y se declara** (un evento `inferencia_*` al trail por cada uno):
  `inferencia_horizonte_12m` (`horizon_12m_periods = round(1 / year_fraction(period))`: año 1,
  semestre 2, trimestre 4, mes 12, semana 52, día 365; una unidad no reconocida detiene la puerta
  antes de correr con las aceptadas); `inferencia_esquema` (tipos de las columnas **declaradas**,
  obligatorias, para que una columna ausente falle en `data` con nombre y no a mitad del motor);
  `inferencia_identificador` (sin `id`, el índice del archivo); `inferencia_corrida_de_cartera`
  (sin target ni partición, §3.3); `inferencia_sin_marca` cuando no se pasa `default` (Stage 3 sólo
  por mora ≥ 90 días).
- **Un argumento por esencial, ninguno más** (D-SIM-4): la tabla de §3.7 es el contrato. `purpose=`,
  `owner=`, `review_every=`, `track=`, `document=`, `formats=`, `name=` y `run_dir=` se comportan
  como en `Scorecard` (mismos esenciales de `governance`, `report` y `tracking`; `name` por defecto
  `"ecl"`, `run_dir` `"bayesrisk-runs"`).
- **`data` como `DataFrame`** se persiste como snapshot parquet, igual que en `Scorecard`.
- **El paso de la puerta en el trail** es `ecl_guided` (el del scorecard es `scorecard_guided`); la
  procedencia se declara, los resultados son los del config (D-SIM-1).

### 3.3 D-ECL-2 — Una corrida de cartera no declara target ni partición (decisión de Cami, §8-3)

**Recomendación:** `DataConfig.target` y `DataConfig.partition` aceptan `null` **explícito** —la
clave sigue siendo obligatoria, de modo que olvidarla sigue siendo un error—, los dos a la vez o
ninguno. Con los dos en `null`, `DataStep` carga, valida el esquema, aplica la política de
especiales, calcula `data_hash` y publica `("data", "frame")`, `data_hash`, `special` y `data_card`,
pero no `labels` ni `splits`. Todo paso que los exige (`eda`, `binning`, `selection`, `model`) queda
fuera del DAG con el mensaje de `check_pipeline`, y `DataConfig` gana un requisito por contexto en
idioma de negocio («esta corrida modela un incumplimiento y no dijiste qué es un cliente malo»).
**Nada se siembra** (D-OBL-5): la corrida de cartera dice «no aplica», no inventa un criterio.

- Ningún `config_hash` existente se mueve: todo YAML vigente declara las dos claves con valor.
- `data` es estable (SemVer 2.x): relajar un campo obligatorio a anulable es aditivo; el tipo
  Python pasa a `TargetConfig | None` y se declara en el CHANGELOG.
- La alternativa (b) —que `Ecl` escriba `event == 1` como target y una partición aleatoria
  declarada inerte— no toca `data`, pero siembra una estrategia de partición (D-OBL-5), exige
  `min_bads_per_partition = 30` incumplimientos por muestra (una cartera chica con menos de ~150
  eventos caería por una partición que nadie usa) y deja al resumen hablando de muestras que no
  existen.

### 3.4 D-ECL-3 — La curva de PD: curva propia en H2; la PD del scorecard con H3 (decisión de Cami, §8-5)

«Curva propia» es la curva de supervivencia ajustada sobre la historia de incumplimientos de la
propia cartera (discrete-time hazard con las covariables declaradas): es lo que F4 ya demuestra y lo
que tiene todo banco que provisiona. «PD del scorecard» corre hoy por código (§1.6), pero exige que
**un solo archivo** traiga las variables del scorecard, su target y las columnas de la provisión, y
compone F1 completo con la cadena ECL: es exactamente el trabajo combinado de H3 («PD + LGD en una
corrida»). **Recomendación:** H2 entrega la curva propia; la PD del scorecard entra con H3, con la
medición de §1.6 como punto de partida. Una curva entregada por la institución como tabla (PD por
cartera y período) no tiene hoy ruta por las tres puertas —la puerta de artefactos exige la curva por
operación y declara la corrida no reconstruible desde el config— y queda como candidata con
evidencia (§3.14).

### 3.5 D-ECL-4 — Defaults: constantes de la puerta, nunca defaults de fábrica nuevos

Ningún default de fábrica cambia —`config_hash` es el del `model_dump` completo
(`core/config/hashing.py:108-136`), así que cambiar uno movería la identidad y la cifra de todo YAML
que lo omite—. La puerta parte de las secciones `survival` y `provisioning_ifrs9` del preset F4
(como `Scorecard` parte de F1) y escribe las columnas del usuario encima. Quedan como **constantes de
la puerta**, con su razón:

| Hoja | Fábrica | Puerta | Razón |
|---|---|---|---|
| `survival.input.pd_source` | `model_raw` | `none` | curva propia (§3.4); `model_raw` exige `model` |
| `survival.method` / `discrete_hazard.*` | `discrete_hazard`, logit, dummies por período | iguales; `pd_role="none"` | el estándar IFRS 9 de SDD-18 sobre períodos discretos |
| `survival.time_grid.time_unit` | `period` | `period=` | institucional; `period` dispara IFRS-7 |
| `survival.time_grid.horizon_periods` | `None` | `horizon=` | institucional; `None` dispara SUR-1 |
| `provisioning_ifrs9.pd.horizon_12m_periods` | 12 | inferido de la unidad | el default duplica la ECL con curvas anuales (§1.4) |
| `provisioning_ifrs9.pd.pit_mode` | `consume_pit` | `ttc_only` (§3.6) | `consume_pit` exige curvas PIT de `forward` |
| `provisioning_ifrs9.scenarios.source` | `forward` | `single` | `forward` exige pesos que sólo publica `forward` |
| `provisioning_ifrs9.ead.method` | `ccf` | `provided` | la EAD la entrega la institución; CCF exige `drawn` y límite |
| `provisioning_ifrs9.lgd.method` | `provided` | `provided` | la LGD modelada es H3 |
| `staging` (2,0 · 3,0 · 30 · 90) | ídem | ídem | presunciones de IFRS 9 5.5.11 y B5.5.37; se rebaten con motivo (§3.9) |
| `ecl.discount_convention` / `rounding` | anual por fracción de año / ninguno | ídem | la tasa se pide anual; el valor económico exacto |
| `fail_on_falta_dato` (las dos) | `True` | `True` | un aviso declarado detiene la corrida, como en el scorecard |

### 3.6 D-ECL-5 — PIT/TTC (decisión de Cami pendiente desde 2026-07-26; §8-2)

Hoy ninguna salida PIT es alcanzable sin datos nuevos: `consume_pit` exige una curva etiquetada
`pd_basis='pit'` que sólo produce `forward`; `apply_vasicek` exige `rho` por cartera y un factor
sistémico Z en la curva, que el dataset del paquete no trae (`ROADMAP.md` «Sacar el preset F4 de
`pit_mode="ttc_only"`»). IFRS 9 5.5.17 pide medir la ECL con información razonable y sustentable
sobre condiciones actuales y pronósticos (cita ya usada por el informe, `report/prose.py:2661`).

| Opción | Qué entrega H2 | Costo |
|---|---|---|
| **(a) TTC declarado en H2; el ajuste prospectivo llega con H7** | la puerta corre `ttc_only` y lo **dice siempre**: el resumen de la curva («PD a lo largo del ciclo, sin ajuste a las condiciones actuales ni escenarios»), «Qué revisar» del resumen final, la página ejecutiva y la guía | ninguno ahora; H7 decide la vía (forward o Vasicek) con datos macro reales |
| (b) Vasicek en H2 | `rho=` por cartera y un factor Z | Z no existe en la curva: cambio de motor para traerlo del archivo, del generador del dataset y recaptura de la demo; `rho` es un parámetro institucional más |
| (c) `forward` en H2 | escenarios macro ponderados | adelanta H7 entero, sin datos macro en el paquete |

**Recomendación: (a).** H2 resuelve la forma de uso; elegir la vía PIT es metodología con datos
macro que hoy no hay, y un PIT inventado sería peor que un TTC declarado. El preset F4 sigue en
`ttc_only` en cualquier caso.

### 3.7 D-ECL-6 — Esenciales por sección y mapeo exhaustivo a la firma

| Path esencial | Argumento | Tipo · default |
|---|---|---|
| `data.load.source` | `data` | ruta o `DataFrame` · obligatorio |
| `data.schema.unique_keys` / `index_col` | `id` | `str` · opcional (como `Scorecard`) |
| `provisioning_ifrs9.as_of_date_col` | `as_of` | `str` · obligatorio |
| `provisioning_ifrs9.portfolio_col` | `portfolio` | `str` · obligatorio |
| `provisioning_ifrs9.ead.ead_col` | `exposure` | `str` · obligatorio |
| `provisioning_ifrs9.lgd.lgd_col` | `lgd` | `str` · obligatorio |
| `provisioning_ifrs9.ecl.eir_col` | `rate` | `str` · obligatorio (anual) |
| `provisioning_ifrs9.staging.days_past_due_col` | `days_past_due` | `str` · obligatorio |
| `provisioning_ifrs9.staging.is_default_col` | `default` | `str \| None` · `None` (§8-4) |
| `survival.input.duration_col` / `event_col` | `duration` / `event` | `str` · obligatorios |
| `survival.time_grid.time_unit` | `period` | `str` · obligatorio |
| `survival.time_grid.horizon_periods` | `horizon` | `int` · obligatorio (la puerta sugiere) |
| `survival.input.covariate_cols` | `covariates` | `list[str]` · vacío |
| `governance.*`, `report.*`, `tracking` | `purpose`, `owner`, `review_every`, `document`, `formats`, `track` | como `Scorecard` |

Esenciales por sección: `survival` **5** (`duration_col`, `event_col`, `time_unit`,
`horizon_periods`, `covariate_cols`), `provisioning_ifrs9` **7** con la marca de incumplimiento o **6**
sin ella (§8-4); `data`, `governance` y `report` conservan los suyos. Las dos secciones ganan
`ui_essentials_declared`; el golden `test_esenciales_por_seccion.py` pasa de doce a catorce
secciones (`:213-228` fija hoy «las doce y ninguna otra»). Todo lo demás se pliega en «Avanzado».

**El tope de 6 y la marca de incumplimiento (§8-4).** Las siete columnas de `provisioning_ifrs9`
son datos institucionales de la entrada mínima (D-SIM-2), no perillas. La marca es la única de las
siete que admite ausencia y es la que más pesa en el staging después de la mora (§1.7). Dejarla en
«Avanzado» respeta el tope pero obliga a quien sí la tiene a salir de la puerta guiada para
declararla, y separa el cuaderno de la demo (Stage 3 de 288 a 240).

### 3.8 D-ECL-7 — Etapas y lo que dice cada resumen de la familia IFRS 9

La familia la decide el pipeline, no un argumento: una corrida con `provisioning_ifrs9` y sin
dominios del scorecard (`RESULT_DOMAINS`) habla con estas etapas, venga de `Ecl`, de un YAML o de la
pantalla (también la del preset F4, que conserva su target inerte):

| Etapa | Rótulo | Lo que dice | Tabla de decisión |
|---|---|---|---|
| `data` | Cartera | operaciones, fecha de corte, exposición total, carteras; dónde queda la evidencia; qué se infirió. Sin «malos» ni muestras | operaciones y exposición por cartera |
| `survival` | Curva de PD | operaciones e incumplimientos observados, períodos y unidad, covariables con su efecto en palabras («más mora, más riesgo»), PD a 12 meses y lifetime medias, **TTC declarado** (§3.6) | PD acumulada por período y cartera (promedio simple de las operaciones); coeficientes con signo, error estándar y p-valor |
| `provisioning_ifrs9` | Provisión IFRS 9 | operaciones y exposición por etapa, ECL total y cobertura, qué gatilló cada etapa (mora, marca), EAD constante declarada (IFRS-4) | ECL por cartera y etapa (filas, EAD, ECL, cobertura): `provisioning_ifrs9.summary` |
| `report` | Informe y ficha | dónde quedó cada archivo | — |

- **Un artefacto aditivo en `survival`:** `("survival", "coefficients")` con `term`, `coef`,
  `std_error`, `p_value` del ajuste discrete-hazard (el GLM ya los calcula; hoy sólo `params_` queda
  en el estimador). Es lo primero que pregunta un validador de la curva y sostiene la decisión
  humana `exclude` (§3.9). Clave propia, golden propio; ningún artefacto existente cambia.
- **Resumen final de la familia:** «Ejecución» (igual que el scorecard); **«Supuestos»** en lugar de
  «Validación técnica» —esta corrida no tiene veredicto técnico; en su lugar, lo que la cifra
  supone: TTC, EAD constante, escenario único, gatillos de staging activos—; **cinco cifras**: ECL
  total, cobertura (ECL / EAD), exposición en Stage 2 y 3 (%), ECL de Stage 2 y 3 (% del total) y PD a
  12 meses media ponderada por exposición (de `detail`); «Qué revisar»: las alertas de las etapas
  (incluye «sin PD de originación, el aumento significativo del riesgo se detecta sólo por mora y
  marca» y, sin covariables, «una sola curva para toda la cartera»); decisiones con motivo; archivos.
  El título del bloque deja de estar fijo en «Resumen del scorecard» (`summaries.py:325`, `:351`).
- **Una sola fuente** (D-SIM-5): los constructores nuevos viven en `guided/summaries.py` y los
  consumen la puerta, la pantalla (`ui/summaries.py`), el informe (página ejecutiva) y el Excel. Cada
  resumen usa sólo lo que publica su etapa o una anterior.

### 3.9 D-ECL-8 — Parar, decidir y seguir

```python
ecl.run(until="survival")            # mira la curva y los coeficientes
ecl.exclude("antiguedad", reason="efecto nulo y sin sentido de negocio")
ecl.rebut_backstops(stage2_days=60, reason="evidencia de cura en 31-60 días, informe de riesgo 2025-03")
ecl.resume()                         # corrida nueva y completa
```

- `run(until=)` y `resume()` con la semántica de D-SIM-6 (prefijo; corrida nueva completa).
- **Dos decisiones humanas**, con motivo obligatorio y registradas en `config.decisions` (D-DEC):
  `exclude(cols, reason=)` retira covariables de la curva (`survival.input.covariate_cols`);
  `rebut_backstops(stage2_days=, stage3_days=, reason=)` rebate las presunciones de 30 y 90 días
  (`staging.dpd_sicr_backstop` / `dpd_default_backstop`), que IFRS 9 admite sólo con información
  razonable y sustentable: por eso es decisión con motivo y no una perilla suelta.
  `DecisionEntry.action` (`core/config/schema.py:213`) gana `rebut_backstops`; `exclude` se
  reutiliza con su hoja propia en `value`, y el cotejo de `core/decisions.py` aprende a reconocer su
  efecto sobre la curva. La sección `decisions` sigue fuera del `config_hash`.
- **No son decisiones humanas en H2**, y por qué: los umbrales de SICR y las columnas opcionales de
  staging son config («Avanzado»); el override cualitativo por operación ya entra como columna del
  archivo (`stage_override_col`); el ajuste posterior al modelo (overlay) no existe en el motor y
  espera su evidencia (§3.14).

### 3.10 D-ECL-9 — Estabilidad: una API que puede ser estable sobre motores experimentales

`Ecl` vive en `guided` (estable desde S18) y sale **declarada experimental** en el copy público, el
CHANGELOG y su docstring hasta que cierre la capa B (adelanto declarado, D-SIM-1, como `Scorecard`
en la 1.17.0); el gate de estabilidad gana una excepción por símbolo que se retira al cerrar B.
Desde entonces la garantía cubre **la firma, los métodos y la forma de los resúmenes**, y las cifras
siguen la marca experimental de `survival` y `provisioning` (la misma lectura que D-EST-5: el sobre
es estable, el contenido sigue a quien lo calcula). Mover `survival` o `provisioning` a estables es
otra decisión (D-EST-4).

### 3.11 D-ECL-10 — Excel opcional y exportación (capa B)

`ecl.export_excel()` escribe `01 Cartera.xlsx`, `02 Curva de PD.xlsx`, `03 Provisión IFRS 9.xlsx` y
`04 Decisiones.xlsx`, con la misma mecánica, protección de celdas y regla de numeración que el
scorecard (§3.5 del molde: el número es la posición de la etapa y no se mueve en una corrida
parcial). `ecl.export("corrida.zip")` empaqueta el `run_dir`.

### 3.12 D-ECL-11 — Pantalla (capa B)

- `survival` y `provisioning_ifrs9` pintan sus esenciales abiertos y un «Avanzado» cerrado con la
  cifra de campos que difieren de fábrica (mecánica de D-FLU-8, sin cambios).
- El trabajo `provisiones_ifrs9` deja de preguntar «¿Qué define a un cliente malo?» y «¿Cómo separas
  la muestra para validar?»: siembra `data.target: null` y `data.partition: null` como override del
  trabajo (si §8-3 es (a)) y pregunta lo que sí decide la institución: duración, evento, unidad y
  horizonte de la curva (las dos primeras ya están, `ui/jobs.py:833-852`).
- Resultados pinta la familia IFRS 9 desde la misma fuente que `summary()`: el bloque «Resumen de la
  corrida» deja de mostrar el molde del scorecard, y la curva de PD por cartera gana su lugar junto
  al bloque IFRS 9 que ya existe (`ResultsTab.tsx:484-554`).

### 3.13 D-ECL-12 — Informe (capa C)

- La página ejecutiva «Resumen de la corrida» aparece también para la familia IFRS 9, con su
  resumen final (la condición any-of de `report/document.py:382-388` gana `provisioning_ifrs9`).
- El cuerpo publica la curva: `KEY_TABLES` gana la PD acumulada por período y cartera y la tabla de
  coeficientes; el anexo C.2 conserva la card.
- Mueve el golden del informe IFRS 9 y la demo publicada: se declaran antes de moverlos y la
  recaptura pide su OK (AGENTS).

### 3.14 D-ECL-13 — Caso real: EAD constante, CCF y los tres datasets

- **EAD constante (`FALTA-DATO-IFRS-4`)** se mantiene en H2 y se dice en el resumen de la provisión
  y en «Supuestos»: «la exposición se mantiene constante en el tiempo; si tu cartera amortiza, la ECL
  lifetime queda sobrestimada». El perfil de amortización es una capacidad nueva (CT-3) que entra
  sólo con la evidencia medida sobre un dataset real de cuotas (abajo).
- **CCF:** la puerta toma la EAD ya calculada; la ruta `drawn` + límite + CCF sigue disponible en
  «Avanzado» y en el config (qué NO se configura en la puerta, §3.16).
- **Criterio de tres datasets (C1):** H2 no se declara completo sin tres corridas de punta a punta
  por el writer, al menos una externa y real: (1) `ifrs9_retail_latam` (paquete); (2) y (3) dos
  carteras públicas con historia de pagos, saldo, tasa y mora, **candidatas a verificar al
  obtenerlas**: el dataset de préstamos de Lending Club (cuotas a 36/60 meses: saldo pendiente,
  tasa, estado de mora y recuperos tras castigo) y la muestra de Freddie Mac Single-Family
  Loan-Level (hipotecario: saldo vigente, mora mensual, tasa y pérdida al cierre). Su descarga exige
  una cuenta (Kaggle o registro de Freddie Mac): es un paso de Cami o con su autorización. Cada uno
  mide además el costo de la EAD constante y de la curva sin PD de originación, que son la
  evidencia de las candidatas de abajo.
- **Candidatas anotadas, no adoptadas** (D-SIM-3, cada una espera su evidencia): perfil de
  amortización de la EAD; curva por cartera estratificada; PD de originación inferida para SICR;
  curva entregada como tabla; ajuste posterior al modelo (overlay) con motivo; LGD por defecto por
  cartera.

### 3.15 D-ECL-14 — Capas

| Capa | Qué | Gate de cierre |
|---|---|---|
| **0** | D-ECL-0 (IFRS-8) y, si §8-3 es (a), `data` con target y partición nulos | test nacido rojo del caso de §1.4 (hoy `done` con 6,86 M); F1 y F4 con proyección canónica intacta y sus `config_hash`; requisito por contexto con su mensaje |
| **A** | `bayesrisk.Ecl` por código: entrada mínima e inferencias, `run`/`until`/`resume`, `exclude` y `rebut_backstops`, resúmenes por etapa de la familia IFRS 9 y su resumen final, `("survival","coefficients")`, notebook mínimo; experimental (D-ECL-9) | las cinco cifras ancladas; notebook en CI; `config_hash(ecl.config)` = el del YAML exportado; `run()` y `run(until) + resume()` con la misma proyección canónica; la ECL de `Ecl` sobre el dataset del paquete **igual a F4** (con la marca) salvo la etiqueta `partition` |
| **B** | Pantalla (esenciales, preguntas del trabajo, Resultados de la familia); Excel opcional y `export()`; `Ecl` pasa a estable | golden de esenciales (catorce secciones) y su espejo del front; copy gate; Excel celda a celda con el informe |
| **C** | Informe (página ejecutiva y curva); guía en `docs_site/`; tres datasets (C1) | goldens del informe declarados antes de moverlos; recaptura con su OK |

### 3.16 D-ECL-15 — Presupuesto de perillas: cero. Qué NO se configura

Cero hojas nuevas: cada argumento de `Ecl` escribe una hoja existente; `ui_essential` es metadato;
`target`/`partition` anulables no añaden hojas (el barrido del formulario recorre las ramas de cada
unión: se mide al implementar y se declara en `HOJAS_DEL_FORMULARIO` si cambia);
`("survival","coefficients")` es un artefacto, no una perilla; `rebut_backstops` es una acción de
`decisions`, fuera del hash. **No se configura en la puerta:** el método de la curva
(discrete-hazard logit con dummies por período), el rol de la PD del scorecard, la fuente de la
curva, el modo PIT (§3.6), los escenarios, el método de LGD y de EAD (CCF), la convención de
descuento, el redondeo, la regla de inferencia del horizonte de 12 meses, el promedio simple de la
curva por cartera en el resumen, las etapas, los rótulos, la numeración del Excel y qué tabla es «de
decisión». Todo lo que el motor sí admite sigue en «Avanzado» y en `ecl.config`.

## 4. Contratos de datos (I/O)

- **Entrada:** un archivo (csv/parquet/xlsx) o `DataFrame` con una fila por operación a la fecha de
  corte: las siete columnas de la provisión (la marca, opcional) y la historia de la curva
  (`duration` entero ≥ 1 en la unidad declarada, `event` 0/1). Fecha de corte única por corrida
  (`_as_of_date_from_frame`). La tasa es anual.
- **Salida:** `ecl.study`, `ecl.config` (`BayesRiskConfig` completo), `ecl.results[<etapa>]` (las
  tablas de decisión), `ecl.summary(<etapa>|None)`, y en disco el layout de `Scorecard`:
  `<run_dir>/<name>/run/`, `config.yaml`, `reports/`, `input/` y `excel/` si se pidió.
- **Invariantes:** `config_hash(ecl.config)` coincide con el del YAML exportado; la ECL de `Ecl`
  sobre el dataset del paquete, con la marca, es la de F4 (3.423.116); toda decisión humana aparece
  una vez en `config.decisions` y una vez en el trail de la corrida que la ejecuta.

## 5. Casos borde

Sin `horizon` (se detiene antes de correr con el máximo observado y el valor sugerido); unidad no
reconocida (`quincena`, `bimestre`, `period`: se detiene con las aceptadas); fecha de corte con más
de un valor (falla en el motor con su mensaje); una cartera con todas las operaciones censuradas
(`DATO-INSTITUCIONAL-SUR-2`, ya declarado); horizonte de 12 meses mayor que la curva con unidad
convertible (ahora `FALTA-DATO-IFRS-8`, §3.1); sin covariables (una sola curva, alerta en «Qué
revisar»); covariable no numérica (error del motor con su nombre); sin marca de incumplimiento
(Stage 3 sólo por mora, declarado); `rebut_backstops` con el umbral de Stage 3 menor que el de
Stage 2 (lo rechaza el validador de `staging`, `ifrs9/config.py:661-664`); `exclude` de una columna
que no es covariable (error legible); EIR mensual pasada como anual (no detectable: la ayuda lo dice
y el resumen muestra la tasa media por cartera para que salte a la vista).

## 6. Gates y controles negativos de ESTA enmienda

1. D-ECL-0: el caso de §1.4 nace rojo (hoy `done` con 6.863.157) y pasa a abortar con
   `FALTA-DATO-IFRS-8`; la curva mensual de 12 períodos con horizonte 12 sigue sin aviso. CN: revertir
   la corrección y ver el primero en rojo.
2. `data` nulo: corrida de cartera bit a bit igual a F4 en la provisión; un pipeline con `binning`
   y target nulo se detiene antes de correr con el mensaje de negocio; F1 y F4 con su proyección
   canónica y su `config_hash` intactos.
3. Golden de las cinco cifras de IFRS 9 (gemelo de `test_simplicidad_scorecard.py`) y golden de
   esenciales en catorce secciones; CN: un esencial de más pone rojo.
4. Notebook mínimo en CI (`docs_site/`); CN: una línea de más lo pone rojo.
5. `config_hash(ecl.config) == config_hash(load_config(ecl.to_yaml()))`.
6. Paridad computacional `run()` frente a `run(until="survival") + resume()` sin decisiones.
7. Los resúmenes de la familia IFRS 9 sin identificadores del motor (gate de códigos internos) y sin
   las palabras del scorecard («malos», «Desarrollo», «Holdout», «validación formal»); CN: devolver el
   resumen de datos del scorecard y ver el gate en rojo.
8. `("survival","coefficients")` con golden propio; los artefactos existentes de `survival` no se
   mueven.
9. Una decisión humana de cada tipo aparece en `config.decisions`, en el trail y en el resumen final
   con su motivo; CN: retirar la emisión.

## 7. Lo que esta enmienda NO hace

No cambia la ECL de ningún config correcto; no cambia ningún default de fábrica; no mueve el
`config_hash` del preset F4 ni de ningún YAML; no decide la vía PIT (§8-2); no trae la PD del
scorecard a H2 si Cami elige (a) en §8-5; no modela LGD ni EAD (H3); no toca forward, Markov ni
stress (H7); no reabre D-HOR más allá de cumplir su promesa (§3.1); no convierte el Excel en
obligatorio; no programa nada.

## 8. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 8-1 | La enmienda en su conjunto (D-ECL-0…15) | (a) **aprobar y programar la capa 0 + A en la sesión siguiente**; (b) aprobar con cambios; (c) no aprobar | **(a)** |
| 8-2 | PIT/TTC (§3.6) | (a) **TTC declarado en H2; PIT con H7**; (b) Vasicek en H2; (c) `forward` en H2 | **(a)**: sin datos macro, un PIT sería inventado; el TTC se declara en cada salida |
| 8-3 | Target y partición en una corrida de cartera (§3.3) | (a) **`data` acepta `null` explícito en los dos**; (b) `Ecl` siembra target = evento y una partición aleatoria declarada inerte | **(a)**: no siembra criterio (D-OBL-5), no cae por una partición que nadie usa, y el resumen deja de hablar de muestras |
| 8-4 | La marca de incumplimiento y el tope de 6 (§3.7) | (a) **siete esenciales en `provisioning_ifrs9`, excepción al tope sólo para esta sección**; (b) seis, y la marca en «Avanzado» | **(a)**: son siete datos de la entrada mínima, no perillas; sin la marca el Stage 3 baja de 288 a 240 y el cuaderno se separa de la demo |
| 8-5 | «PD del scorecard o curva propia» (§3.4) | (a) **curva propia en H2; la PD del scorecard con H3**; (b) `Ecl(..., pd=sc)` en la capa C de H2 | **(a)**: exige un archivo con las variables del scorecard y la cartera, y es el trabajo combinado de H3 |
| 8-6 | Releases | (a) **capa 0 + A en 2.4.0 (`Ecl` experimental); B + C en 2.5.0 con la recaptura**; (b) todo en una release | **(a)**: el molde del scorecard salió así; cada release con su OK |

## 13. Simplicidad (SDD-31)

- **Entrada mínima (§3.2):** el archivo de cartera con fecha de corte, cartera, exposición, LGD,
  tasa efectiva anual, mora (y la marca de incumplimiento, opcional) y la historia de la curva
  (duración, evento, unidad, horizonte). Se infieren y se declaran: el horizonte de 12 meses, el
  esquema de las columnas declaradas, el identificador, la corrida de cartera sin target ni
  partición y la ausencia de marca.
- **Qué NO se configura (§3.16):** método y fuente de la curva, rol de la PD, modo PIT, escenarios,
  métodos de LGD y EAD, descuento, redondeo, la regla del horizonte de 12 meses, el promedio de la
  curva en el resumen, etapas, rótulos, Excel y tablas de decisión. Constantes con su razón.
- **Campos esenciales (§3.7):** `survival` 5; `provisioning_ifrs9` 7 (u 6, §8-4); `data`,
  `governance` y `report` sin cambios; mapeo exhaustivo path → argumento de `Ecl`; el resto en
  «Avanzado» (capa B).
- **Presupuesto de perillas:** **cero** hojas nuevas (§3.16); la excepción que se pide es al tope de
  esenciales (§8-4), no al presupuesto.
- **Resumen por etapa (§3.8):** Cartera, Curva de PD, Provisión IFRS 9, Informe y ficha; resumen
  final con ejecución, supuestos, cinco cifras de provisión, qué revisar, decisiones y archivos.
  Decisiones humanas: `exclude` (covariables) y `rebut_backstops` (§3.9).
- **Notebook mínimo:** «Tu primera provisión IFRS 9» en `docs_site/`, ≤ 25 líneas (borrador de §3.2
  con `materialize`: ~20), ejecutado en CI.
- **Las cinco cifras (SDD-31 §5), línea base medida y objetivo:**

| Cifra | Hoy (`3cc9654`) | Objetivo |
|---|---|---|
| Líneas de usuario | sin notebook; ~8 líneas con el preset del paquete; con datos propios, un YAML de 268 líneas donde reescribir `data` y 12 rutas | ≤ 25 (~20) |
| Esenciales por sección | 0 en `survival` y `provisioning_ifrs9` (se pintan enteras) | 5 y 7 (u 6) |
| Perillas de las tres secciones de cálculo | 230 (158 + 24 + 48) | sin crecer |
| Segundos al primer resumen | no hay resumen de curva ni de ECL; primera cifra de ECL a los 4,8–6,4 s | ≤ 30 s (esperado ~5 s) |
| Conceptos antes del primer resultado | ≥ 8 (`ifrs9_preset`, `materialize`, `BayesRiskConfig`, `model_validate`, `run`, `run_dir`, `artifacts.get`, dominio/clave) | ≤ 5 (`Ecl`, `materialize`, `run`, `exclude`, `resume`) |

### Las diez preguntas de la línea base y dónde se responden

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | Entrada mínima frente a `data` | §3.3 y §8-3: `null` explícito, sin sembrar |
| 2 | PD del scorecard o curva propia | §3.4 y §8-5: curva propia en H2; la PD del scorecard con H3 |
| 3 | Defaults a constantes sin mover hashes | §3.5: constantes de la puerta desde F4; ningún default de fábrica cambia; D-ECL-0 corrige el motor |
| 4 | PIT/TTC | §3.6 y §8-2: TTC declarado en cada salida; decide Cami |
| 5 | Esenciales ≤ 6 | §3.7 y §8-4: 5 y 7 (u 6); golden a catorce secciones |
| 6 | Resúmenes de la familia, pantalla y página ejecutiva | §3.8, §3.12, §3.13 |
| 7 | Estabilidad | §3.10: experimental hasta B; después la firma estable y las cifras experimentales |
| 8 | Decisiones humanas, `until`/`resume`, Excel y `export()` | §3.9 y §3.11 |
| 9 | Caso real: IFRS-4, CCF y tres datasets | §3.14 |
| 10 | Cuaderno y supervivencia en pantalla | §13 (cuaderno), §3.12 (pantalla), §3.13 (informe) |
