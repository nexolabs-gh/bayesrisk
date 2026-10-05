# Referencia de la API

Superficie pública de bayesrisk, organizada por dominio. Cada símbolo se genera
automáticamente desde sus *docstrings* con [mkdocstrings]; las firmas y campos son los del código
publicado (`2.5.0`).

!!! note "Estabilidad (SemVer 2.x)"
    El pipeline de validación de scorecard (F1) —el trío `run` → `Study` → `BayesRiskConfig` y los
    dominios `data`, `eda`, `binning`, `selection`, `model`, `scorecard`, `calibration`,
    `performance` y `stability`— es **API estable**: no rompe hasta una versión 3.0. También lo son el
    informe (`report`), el trail de auditoría (`audit`), porque ya son superficie de integración,
    y la puerta guiada (`guided`, `bayesrisk.Scorecard`), desde que cerraron sus tres puertas.
    Las superficies que aún crecen (modelado ML, provisiones, survival, forward-looking, stress,
    validación, gobernanza y tracking) están marcadas como **experimentales** en su *docstring*,
    fuera de la garantía SemVer 2.x.

    Esa lista no se escribe a mano en tres sitios: la fija `bayesrisk.testing.stability` y la
    verifican los gates del repositorio contra el *docstring* de cada paquete y contra esta página.

!!! note "Núcleo liviano e import perezoso"
    `import bayesrisk` no arrastra el stack ML. `bayesrisk.run` se re-exporta de forma perezosa (PEP
    562) desde `bayesrisk.api`, y los backends pesados de cada dominio (pandas, sklearn, statsmodels,
    optbinning, XGBoost, …) se cargan solo al ejecutar el paso correspondiente, tras sus *extras*
    opcionales.

## Puerta guiada

`bayesrisk.Scorecard` construye, corre y cuenta un scorecard de comportamiento con la entrada
mínima; es un cliente de `run` que arma el `BayesRiskConfig`, lo ejecuta y lee sus artefactos.
Estable bajo SemVer 2.x desde que cerraron sus tres puertas (código, config completo y
pantalla): su firma, sus resúmenes y sus decisiones (`exclude`, `keep`, `merge_bins`,
`set_bins`) sólo crecen de forma aditiva.

::: bayesrisk.guided.scorecard.Scorecard

`bayesrisk.Ecl` calcula la provisión IFRS 9 de una cartera con la misma mecánica: el archivo de
cartera y la historia de incumplimientos que alimenta la curva de PD, resúmenes por etapa en
palabras de provisiones y dos decisiones con motivo (`exclude` sobre las covariables de la curva y
`rebut_backstops` sobre las presunciones de mora). Su firma, sus métodos y la forma de sus
resúmenes son estables bajo SemVer 2.x desde que la pantalla ofrece lo mismo; sus cifras siguen la
marca experimental de `survival` y `provisioning`, los motores que las calculan.

::: bayesrisk.guided.ecl.Ecl

::: bayesrisk.guided.summaries.StageSummary

::: bayesrisk.guided.summaries.FinalSummary

## Ejecución y estado de la corrida

Punto de entrada único (`run`) y las estructuras *stateful* que produce: el `Study` contenedor, su
`ArtifactStore` *namespaced*, el `RunContext` (estado + lineage) y el `LineageBundle` reproducible.
`check_pipeline` responde si un config **se puede** ejecutar, sin ejecutarlo.

::: bayesrisk.run
    options:
      heading_level: 3

::: bayesrisk.check_pipeline
    options:
      heading_level: 3

::: bayesrisk.api.PipelineCheck
    options:
      heading_level: 3

::: bayesrisk.api.assemble_run
    options:
      heading_level: 3

<a id="study"></a>

::: bayesrisk.core.study.Study
    options:
      heading_level: 3

::: bayesrisk.core.artifacts.ArtifactStore
    options:
      heading_level: 3

::: bayesrisk.core.lineage.RunContext
    options:
      heading_level: 3

::: bayesrisk.core.lineage.LineageBundle
    options:
      heading_level: 3

::: bayesrisk.core.steps.Step
    options:
      heading_level: 3

## Configuración declarativa

`BayesRiskConfig` es la raíz del experimento (Pydantic v2): agrupa las secciones de reproducibilidad,
orquestación y todos los dominios. Se acompaña de utilidades de identidad (`config_hash`),
carga/volcado YAML y migración de esquema.

::: bayesrisk.core.config.schema.BayesRiskConfig
    options:
      heading_level: 3

::: bayesrisk.core.config.schema.RunConfig
    options:
      heading_level: 3

::: bayesrisk.core.config.schema.ReproConfig
    options:
      heading_level: 3

::: bayesrisk.core.config.schema.DecisionEntry
    options:
      heading_level: 3

::: bayesrisk.core.config.hashing.config_hash
    options:
      heading_level: 3

::: bayesrisk.core.config.loader.load_config
    options:
      heading_level: 3

::: bayesrisk.core.config.loader.loads_config
    options:
      heading_level: 3

::: bayesrisk.core.config.loader.dump_config
    options:
      heading_level: 3

::: bayesrisk.core.config.migration.migrate
    options:
      heading_level: 3

::: bayesrisk.core.config.migration.migration
    options:
      heading_level: 3

## Datos

Carga, validación de esquema, definición del *target*, particionado y hashing lógico del dataset
(`data_hash`) que alimenta el lineage.

::: bayesrisk.data.config.DataConfig
    options:
      heading_level: 3

::: bayesrisk.data.loading.DataLoader
    options:
      heading_level: 3

::: bayesrisk.data.schema.SchemaValidator
    options:
      heading_level: 3

::: bayesrisk.data.target.TargetDefinition
    options:
      heading_level: 3

::: bayesrisk.data.partition.Partitioner
    options:
      heading_level: 3

::: bayesrisk.data.step.DataStep
    options:
      heading_level: 3

## Análisis exploratorio (EDA)

Perfiles por variable, calidad de datos, tasa de incumplimiento en el tiempo y su estabilidad
temporal, antes de modelar. Cómo se lee cada pieza —y qué hace el motor cuando el archivo no trae
fecha— está en la guía [Análisis exploratorio](guias/analisis-exploratorio.md).

### Eje, indicador, causas y marcas

En los resultados —JSON, tablas, model card— cada uno viaja como su **identificador**; en la
pantalla, en el informe y en las guías se lee como su **palabra**. Son el mismo dato, y cada
correspondencia tiene una sola fuente en `bayesrisk.eda`.

| Identificador | Palabra | Qué es | Fuente |
|---|---|---|---|
| `period` | por fecha de observación | Eje **efectivo** de la tasa (`axis` de la card) | `bayesrisk.eda.default_rate.AXIS_LABELS` |
| `cohort` | por cohorte | Ídem; puede ser el efectivo aunque el config diga `period` (`axis_inferred`) | ídem |
| `cv` | variación relativa | Indicador de estabilidad temporal | `bayesrisk.eda.stability.STABILITY_INDICATOR_LABELS` |
| `max_relative_drift` | peor desvío | Ídem | ídem |
| `trend_slope` | tendencia | Ídem | ídem |
| `eje_cohorte` | eje de cohorte, sin orden cronológico | Causa de no evaluar la señal (`stability_not_evaluable_reason`) | `bayesrisk.eda.stability.NOT_EVALUABLE_REASON_LABELS` |
| `pocos_periodos_evaluables` | menos de dos períodos con observaciones suficientes | Ídem | ídem |
| `tasa_media_cero` | sin incumplimientos en los períodos evaluables | Ídem; sólo con un indicador relativo | ídem |
| `sin_eje_temporal` | el archivo no trae un eje temporal que ordenar | Ídem; la tasa no se pudo agrupar, así que no hay serie que mirar | ídem |
| `tasa_no_calculable` | la tasa por período no se pudo calcular | Ídem; el cálculo de la tasa falló, así que no hay serie que mirar | ídem |
| `no_calculable` | no se pudo calcular | Ídem; la señal falló por sí sola y la tasa se conserva entera | ídem |
| `sin_eje_temporal` | el archivo no trae columna de fecha ni cohorte declarada | Causa de no evaluar **la tasa** (`default_rate_not_evaluable_reason`): sin columna de fecha y sin cohorte declarada no hay eje, la tabla por período sale vacía y la corrida sigue | `bayesrisk.eda.default_rate.DEFAULT_RATE_NOT_EVALUABLE_REASON_LABELS` |
| `no_calculable` | no se pudo calcular | Ídem, cuando el **cálculo** falló: la tabla sale vacía, la tasa global se conserva si hubo población y la causa del motor viaja en `failed_analyses` | ídem |
| `near_constant` | casi constante | Marca de calidad por columna | `bayesrisk.eda.quality.QUALITY_FLAG_LABELS` |
| `near_unique` | casi única | Ídem | ídem |
| `high_cardinality` | alta cardinalidad | Ídem | ídem |

La regla que gobierna la causa es una sola: hay causa **si y sólo si** el indicador configurado no
es finito; entonces `stability_value` viaja como `null` y `stability_flagged` es `false`. Cuando
el archivo no trae columna de fecha y la partición es por cohorte, el eje se **infiere** a esa
cohorte y la decisión `eje_eda_inferido` queda en el trail de la corrida.

`EdaStep` **nunca detiene la corrida**: la tasa por período, la señal temporal, los perfiles y la
calidad fallan por separado, cada uno publica su versión vacía y el paso publica siempre sus seis
artefactos. La card trae `failed_analyses` —sub-análisis (`default_rate`, `stability`,
`univariate`, `quality`, `figures`) → causa del motor—, vacío en toda corrida sana; cada falla deja una
decisión `analisis_exploratorio_parcial` en el trail, y en el canal de métricas lo que no se
calculó se **omite** en vez de publicarse como cero. Una excepción que no sea `EdaError` también
degrada, pero su causa lleva el tipo: «error inesperado del motor (`<Tipo>`): …». Las piezas
—`DefaultRateAnalyzer`, `UnivariateProfiler`, `DataQualityProfiler`— usadas por código siguen
levantando su `EdaError` de siempre. Lo que se dice de cada uno y la frase que lo redacta viven
en `bayesrisk.eda.card` (`FAILED_ANALYSIS_LABELS`, `failed_analysis_sentence`).

::: bayesrisk.eda.config.EdaConfig
    options:
      heading_level: 3

::: bayesrisk.eda.univariate.UnivariateProfiler
    options:
      heading_level: 3

::: bayesrisk.eda.quality.DataQualityProfiler
    options:
      heading_level: 3

::: bayesrisk.eda.default_rate.DefaultRateAnalyzer
    options:
      heading_level: 3

::: bayesrisk.eda.stability.TemporalStabilityAnalyzer
    options:
      heading_level: 3

::: bayesrisk.eda.step.EdaStep
    options:
      heading_level: 3

## Binning y WoE

Discretización supervisada con *Weight of Evidence* (WoE), monotonía controlada e IV (motor
OptBinning tras el *extra* `scoring`).

::: bayesrisk.binning.config.BinningConfig
    options:
      heading_level: 3

::: bayesrisk.binning.transformer.WoEBinner
    options:
      heading_level: 3

::: bayesrisk.binning.results.BinningResult
    options:
      heading_level: 3

::: bayesrisk.binning.step.BinningStep
    options:
      heading_level: 3

## Selección de variables

Filtrado pre-modelo por IV, correlación, VIF y estabilidad.

### Motivos y bandas de IV

Cada variable candidata sale con un motivo (`decisions[].reason`) y con la banda diagnóstica de su
IV (`decisions[].iv_band`). Igual que con las bandas de estabilidad, el identificador es el dato y
la palabra es lo que se lee en pantalla y en el informe; las fuentes únicas son
`bayesrisk.selection.results.REASON_LABELS` y `bayesrisk.binning.results.IV_BAND_LABELS`.

| Motivo | Palabra |
|---|---|
| `included` | inclusión |
| `business_include` | inclusión forzada de negocio |
| `business_exclude` | exclusión de negocio |
| `low_iv` | IV insuficiente |
| `high_iv` | IV excesivo (posible fuga) |
| `low_auc` | AUC insuficiente |
| `low_ks` | KS insuficiente |
| `low_gini` | Gini insuficiente |
| `high_correlation` | correlación excesiva |
| `high_vif` | VIF excesivo |
| `cluster_representative_lost` | no ser representante de su clúster |
| `constant_or_nonfinite` | ser constante o no finita |
| `missing_binning_artifact` | faltar su artefacto de binning |
| `forced_conflict` | conflicto entre reglas forzadas |
| `high_stability` | inestabilidad temporal |

| Banda de IV | Palabra |
|---|---|
| `none` | sin poder |
| `weak` | débil |
| `medium` | medio |
| `strong` | fuerte |
| `suspicious` | sospechoso |

::: bayesrisk.selection.config.SelectionConfig
    options:
      heading_level: 3

::: bayesrisk.selection.selector.FeatureSelector
    options:
      heading_level: 3

::: bayesrisk.selection.results.SelectionResult
    options:
      heading_level: 3

::: bayesrisk.selection.step.SelectionStep
    options:
      heading_level: 3

## Modelo (regresión logística PD)

Regresión logística sobre variables WoE con *stepwise*, política de signos e inferencia
(statsmodels).

::: bayesrisk.model.config.ModelConfig
    options:
      heading_level: 3

::: bayesrisk.model.estimator.LogisticPDModel
    options:
      heading_level: 3

::: bayesrisk.model.results.ModelResult
    options:
      heading_level: 3

::: bayesrisk.model.step.ModelStep
    options:
      heading_level: 3

## Scorecard

Traducción de coeficientes a puntajes enteros (escala PDO / *target odds*), con *overrides* y
redondeo controlado.

::: bayesrisk.scorecard.config.ScorecardConfig
    options:
      heading_level: 3

::: bayesrisk.scorecard.scaler.PointsScaler
    options:
      heading_level: 3

::: bayesrisk.scorecard.transformer.Scorecard
    options:
      heading_level: 3

::: bayesrisk.scorecard.results.ScorecardResult
    options:
      heading_level: 3

::: bayesrisk.scorecard.step.ScorecardStep
    options:
      heading_level: 3

## Calibración

Ajuste de la PD cruda a un ancla de negocio (*through-the-cycle*), con tope de *offset* auditable.

::: bayesrisk.calibration.config.CalibrationConfig
    options:
      heading_level: 3

::: bayesrisk.calibration.calibrator.PDCalibrator
    options:
      heading_level: 3

::: bayesrisk.calibration.results.CalibrationResult
    options:
      heading_level: 3

::: bayesrisk.calibration.step.CalibrationStep
    options:
      heading_level: 3

## Desempeño

Métricas de discriminación (AUC/KS/Gini) y desempeño por decil, por partición.

::: bayesrisk.performance.config.PerformanceConfig
    options:
      heading_level: 3

::: bayesrisk.performance.evaluator.PerformanceEvaluator
    options:
      heading_level: 3

::: bayesrisk.performance.results.PerformanceResult
    options:
      heading_level: 3

::: bayesrisk.performance.step.PerformanceStep
    options:
      heading_level: 3

## Estabilidad

PSI/CSI y estabilidad temporal del puntaje y de las características.

### Bandas de estabilidad

Cada comparación se clasifica en una banda, y la banda fija de forma única la acción auditada. En
los resultados —JSON, `psi_table`, `stability_metrics`, model card— la banda viaja como su
**identificador**; en la pantalla, en el informe y en las guías se lee como su **palabra**. Son el
mismo dato: la fuente única de la correspondencia es `bayesrisk.stability.results.BAND_LABELS`.

| Identificador | Palabra | Acción auditada |
|---|---|---|
| `stable` | Estable | `none` |
| `review` | Revisar | `vigilar` |
| `redevelop` | Redesarrollar | `redesarrollar` |
| `not_evaluable` | No evaluable | `none` |

El resumen de cada comparación publica juntos el peor PSI entre score y PD, la identidad de la
magnitud ganadora (`score_psi` → «score», `pd_psi` → «PD calibrada», en
`bayesrisk.stability.results.PSI_METRIC_LABELS`) y la banda **de esa misma magnitud**.

::: bayesrisk.stability.config.StabilityConfig
    options:
      heading_level: 3

::: bayesrisk.stability.evaluator.StabilityEvaluator
    options:
      heading_level: 3

::: bayesrisk.stability.results.StabilityResult
    options:
      heading_level: 3

::: bayesrisk.stability.step.StabilityStep
    options:
      heading_level: 3

## Validación

Backtesting y pruebas regulatorias de discriminación, calibración y estabilidad (familias de tests).
Cómo se lee el resultado —y qué hace un validador con él— está en la guía
[Validación formal](guias/validacion-formal.md).

### Estado técnico y veredictos

En los resultados —JSON, tablas tidy, model card— cada estado viaja como su **identificador**; en la
pantalla y en el informe se lee como su **palabra**. Son el mismo dato, y su correspondencia tiene
una sola fuente: `bayesrisk.validation.results`.

| Identificador | Palabra | Dónde aparece |
|---|---|---|
| `pass` | Pasa | Estado técnico agregado de la corrida |
| `warn` | Revisar | Ídem |
| `fail` | Falla | Ídem |
| `not_evaluable` | No evaluable | Ídem: ninguna prueba dejó un veredicto de pasa o falla y la estabilidad no dejó una decisión. La falta de potencia es una causa posible, no la única: también sale con sólo el puntaje de Brier, con sólo discriminación o con las pruebas de pasa o falla apagadas |
| `pass` | Pasa | Veredicto de una fila de calibración o de backtesting |
| `fail` | Falla | Ídem |
| `not_evaluable` | Sin veredicto | Ídem: sin potencia estadística, o una fila que no es una prueba de pasa/falla (el puntaje de Brier) |
| `partition_below_min` / `group_below_min` / `degenerate_group` / `non_finite_statistic` | la muestra quedó bajo el mínimo de operaciones / un grupo de PD quedó bajo el mínimo de operaciones / un grupo de PD quedó sin variabilidad / el estadístico no fue finito con PD extremas | Por qué un Hosmer-Lemeshow quedó sin veredicto (`not_evaluable_reason`); la card las enumera en `metric_sections.validation.not_evaluable_partitions` |
| `green` / `amber` / `red` | Verde / Ámbar / Rojo | Semáforo de un grado de rating |
| `stability_artifact` / `recomputed` | Reusado de la etapa de estabilidad / Recalculado en esta etapa | De dónde salió cada fila de la tabla de estabilidad (`source`); la card lo repite en `metric_sections.validation.stability_source` y, si se recalculó, dice con qué receta en `stability_recompute` (`declared`, la sección de estabilidad; `minimal`, sin eje temporal ni bins) |

El **estado técnico es evidencia del motor**, no el veredicto sobre el modelo: aprobar, aprobar con
observaciones o rechazar es una decisión de quien valida, y el informe lo declara explícitamente.

### Familias y sus tablas

| Identificador | Palabra | Tabla que publica |
|---|---|---|
| `discrimination` | Discriminación | Una fila por partición: población, AUC, Gini, KS, origen y estado |
| `calibration` | Calibración | Hosmer-Lemeshow y puntaje de Brier por partición, y el contraste por grado |
| `stability` | Estabilidad | El PSI de cada magnitud y comparación, con su banda |
| `backtesting` | Backtesting | Un contraste realizado-vs-estimado por parámetro y segmento |

Los grupos de cada Hosmer-Lemeshow con veredicto se publican aparte, en
`("validation", "hosmer_lemeshow_groups")`: una fila por muestra y grupo, con los mismos grupos de
la prueba —operaciones, malos observados y esperados, tasa observada, PD media, la diferencia en
puntos porcentuales (`gap_pp`), la razón O/E (`oe_ratio`) y su aporte al estadístico
(`contribution`), que sumado por muestra lo reproduce—. Sin Hosmer-Lemeshow, la tabla sale vacía.

Los grados sin potencia estadística **no** entran en la tabla de calibración ni en el conteo de
pruebas: viajan aparte, en `card.metric_sections.validation.not_evaluable_grades`, con sus conteos
y el mínimo técnico que los dejó fuera. Un Hosmer-Lemeshow sin veredicto **sí** está en la tabla
—con `statistic` nulo y su causa— pero tampoco cuenta: `n_tests` y `n_failed` cuentan sólo las
decisiones evaluables de las cuatro familias.

::: bayesrisk.validation.config.ValidationConfig
    options:
      heading_level: 3

::: bayesrisk.validation.evaluator.ValidationEvaluator
    options:
      heading_level: 3

::: bayesrisk.validation.results.ValidationResult
    options:
      heading_level: 3

::: bayesrisk.validation.step.ValidationStep
    options:
      heading_level: 3

## Backends ML

Modelos GBDT (XGBoost, LightGBM, CatBoost), *random forest* y SVM como *extras* selectivos, con
monotonía y comparación *challenger* frente al scorecard.

::: bayesrisk.ml.config.MLConfig
    options:
      heading_level: 3

::: bayesrisk.ml.results.MLResult
    options:
      heading_level: 3

::: bayesrisk.ml.step.MLStep
    options:
      heading_level: 3

## Tuning de hiperparámetros

Optimización del espacio de búsqueda (Optuna) con muestreadores/*pruners* deterministas.

::: bayesrisk.tuning.config.TuningConfig
    options:
      heading_level: 3

::: bayesrisk.tuning.results.TuningResult
    options:
      heading_level: 3

::: bayesrisk.tuning.step.TuningStep
    options:
      heading_level: 3

## Explicabilidad

Explicaciones globales/locales (SHAP opcional) y *reason codes* para scorecard y modelos ML.

::: bayesrisk.explain.config.ExplainConfig
    options:
      heading_level: 3

::: bayesrisk.explain.results.ExplainResult
    options:
      heading_level: 3

::: bayesrisk.explain.step.ExplainStep
    options:
      heading_level: 3

## Survival

Modelos de tiempo-a-evento: Kaplan-Meier, hazard discreto y Cox/AFT (algunos tras *extra*).

::: bayesrisk.survival.config.SurvivalConfig
    options:
      heading_level: 3

::: bayesrisk.survival.step.SurvivalStep
    options:
      heading_level: 3

## Cadenas de Markov

Estimación de matrices de transición y estructura temporal de PD por estados.

::: bayesrisk.markov.config.MarkovConfig
    options:
      heading_level: 3

::: bayesrisk.markov.step.MarkovStep
    options:
      heading_level: 3

## Forward-looking

Proyección macroeconómica, modelos satélite y escenarios ponderados para PD *point-in-time*.

::: bayesrisk.forward.config.ForwardConfig
    options:
      heading_level: 3

::: bayesrisk.forward.results.ForwardResult
    options:
      heading_level: 3

::: bayesrisk.forward.step.ForwardStep
    options:
      heading_level: 3

## Stress testing

Escenarios de *shock*, barridos de sensibilidad y *reverse stress* sobre las métricas de provisión.

::: bayesrisk.stress.config.StressConfig
    options:
      heading_level: 3

::: bayesrisk.stress.results.StressResult
    options:
      heading_level: 3

::: bayesrisk.stress.step.StressStep
    options:
      heading_level: 3

## Provisiones

Dos marcos de provisión —**IFRS 9/ECL** y **método interno** (exposición por la tasa de pérdida del
grupo, descompuesta en PD · LGD o provista directamente; jurisdiccionalmente neutro)— más una capa fina de orquestación que compara dos
metodologías y aplica la regla declarada. El motor **CMF (Chile)** documentado más abajo es el
**caso de referencia** de cómo se aterriza una norma local sobre esa base; su alcance y su fecha de
verificación están en [Aterrizar una norma local](norma-local.md).

!!! warning "Sobre la regla del máximo"
    La regla del máximo del **Capítulo B-1** (Circular N° 2.346 / 06.03.2024) es entre el **método
    estándar de la CMF y el método interno del banco**, y se aplica *"para cada institución en Chile
    que consolida con el banco"*. **No** es un máximo entre la provisión CMF y el ECL de IFRS 9: el
    Compendio (Cap. A-2, num. 5) **excluye** el modelo de deterioro de NIIF 9 sobre las colocaciones
    y los créditos contingentes, porque esos criterios los define la propia CMF en B-1 a B-3.
    El comparativo CMF↔IFRS 9 que expone esta capa es un **comparativo entre marcos contables**
    (útil, por ejemplo, para reportar a una matriz extranjera), no una exigencia de la CMF.

::: bayesrisk.provisioning.config.ProvisioningConfig
    options:
      heading_level: 3

::: bayesrisk.provisioning.orchestrator.ProvisioningOrchestrator
    options:
      heading_level: 3

::: bayesrisk.provisioning.results.ProvisionOrchestrationResult
    options:
      heading_level: 3

::: bayesrisk.provisioning.step.ProvisioningStep
    options:
      heading_level: 3

### Motor CMF

::: bayesrisk.provisioning.cmf.config.CmfProvisioningConfig
    options:
      heading_level: 4

::: bayesrisk.provisioning.cmf.engine.CmfProvisioningEngine
    options:
      heading_level: 4

::: bayesrisk.provisioning.cmf.results.CmfProvisionResult
    options:
      heading_level: 4

### Motor IFRS 9 / ECL

::: bayesrisk.provisioning.ifrs9.config.IfrsProvisioningConfig
    options:
      heading_level: 4

::: bayesrisk.provisioning.ifrs9.engine.IfrsProvisioningEngine
    options:
      heading_level: 4

::: bayesrisk.provisioning.ifrs9.results.IfrsProvisionResult
    options:
      heading_level: 4

## Gobernanza

*Model card* (SR 11-7), inventario de modelos y registro de escenarios/overlays. Es la superficie de
trazabilidad que `run` ensambla y (opcionalmente) publica al inventario.

::: bayesrisk.governance.config.GovernanceConfig
    options:
      heading_level: 3

::: bayesrisk.governance.model_card.ModelCard
    options:
      heading_level: 3

::: bayesrisk.governance.model_card.ModelCardBuilder
    options:
      heading_level: 3

::: bayesrisk.governance.inventory.ModelInventory
    options:
      heading_level: 3

::: bayesrisk.governance.inventory.NullInventory
    options:
      heading_level: 3

::: bayesrisk.governance.inventory.InventoryEntry
    options:
      heading_level: 3

::: bayesrisk.governance.inventory.publish_inventory
    options:
      heading_level: 3

::: bayesrisk.governance.scenarios.ScenarioLog
    options:
      heading_level: 3

## Auditoría, lineage y reproducibilidad

*Audit sink* JSONL, captura del entorno y hashing determinista de datos/archivos, más la relectura
del *trail* para reconstruir la corrida.

::: bayesrisk.audit.config.AuditConfig
    options:
      heading_level: 3

::: bayesrisk.audit.sink.JsonlAuditSink
    options:
      heading_level: 3

::: bayesrisk.audit.environment.EnvironmentSnapshot
    options:
      heading_level: 3

::: bayesrisk.audit.environment.capture_environment
    options:
      heading_level: 3

::: bayesrisk.audit.hashing.hash_dataframe
    options:
      heading_level: 3

::: bayesrisk.audit.hashing.hash_file
    options:
      heading_level: 3

::: bayesrisk.audit.replay.read_trail
    options:
      heading_level: 3

::: bayesrisk.audit.replay.iter_trail
    options:
      heading_level: 3

## Tracking (MLflow)

Registro opcional de corridas y modelos en un backend externo (MLflow), tras el *extra*
correspondiente.

::: bayesrisk.tracking.config.TrackingConfig
    options:
      heading_level: 3

::: bayesrisk.tracking.recorder.TrackingRecorder
    options:
      heading_level: 3

::: bayesrisk.tracking.sink.TrackingSink
    options:
      heading_level: 3

::: bayesrisk.tracking.inventory.MLflowInventory
    options:
      heading_level: 3

## Reportería

Reporte auditable del scorecard: ensamblado del bundle, render HTML/PDF y narración opcional
(regla o IA).

::: bayesrisk.report.config.ReportConfig
    options:
      heading_level: 3

::: bayesrisk.report.builder.ReportBuilder
    options:
      heading_level: 3

::: bayesrisk.report.renderer.HtmlReportRenderer
    options:
      heading_level: 3

::: bayesrisk.report.renderer.PdfReportRenderer
    options:
      heading_level: 3

::: bayesrisk.report.results.ReportResult
    options:
      heading_level: 3

::: bayesrisk.report.step.ReportStep
    options:
      heading_level: 3

## Datasets y presets (helpers)

Utilidades para el quickstart y la UI: materialización determinista de datasets sintéticos,
ingesta de *uploads* y el config F1 curado (`standard_preset`).

::: bayesrisk.ui.datasets.materialize
    options:
      heading_level: 3

::: bayesrisk.ui.datasets.list_datasets
    options:
      heading_level: 3

::: bayesrisk.ui.datasets.ingest_upload
    options:
      heading_level: 3

::: bayesrisk.ui.presets.standard_preset
    options:
      heading_level: 3

## Extras opcionales

Introspección de *extras* instalados e imports perezosos con error accionable cuando falta una
dependencia opcional.

::: bayesrisk.utils.optional.has_extra
    options:
      heading_level: 3

::: bayesrisk.utils.optional.require_extra
    options:
      heading_level: 3

[mkdocstrings]: https://mkdocstrings.github.io/
