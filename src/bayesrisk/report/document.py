"""Esquema del documento del informe: **fuente única** de estructura, orden y títulos.

Antes de este módulo, el orden canónico de secciones vivía duplicado en tres sitios
(``builder``, ``renderer`` y ``ai``) y una card del pipeline equivalía a una sección de primer
nivel: el reporte era un volcado del pipeline, no un informe. Aquí se declara el **documento**
—portada, índice, resumen ejecutivo, capítulos 1-6 y anexos A/B/C— y los ocho dominios del
pipeline pasan a ser **subsecciones**: los resultados que un validador lee en el cuerpo, y el
detalle completo (tablas agregadas y payloads) en los anexos.

El principio es que la evidencia **no se pierde**: se ordena. El payload crudo y las tablas
agregadas que el cuerpo no muestra se degradan a anexo. Lo único que sale del documento son las
tablas **por observación** (:data:`PER_OBSERVATION_TABLES`), que no son evidencia sino dataset: se
entregan completas como archivos adjuntos y el anexo dice dónde están.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final, Literal, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict

SectionKind: TypeAlias = Literal["prose", "data", "toc", "appendix", "summary"]
"""Tipo de bloque de una sección. ``summary`` es la página ejecutiva (capa C de
FLUJO-GUIADO-SCORECARD): el resumen final de la corrida, estructurado, que cada renderer pinta
con su propia parcial antes del resumen ejecutivo."""


class _Identified(Protocol):
    """Sección identificable por ``id``.

    Se tipa por protocolo, y no con ``ReportSection``, porque los DTOs importan **de** este módulo:
    depender de ellos crearía un ciclo. El orden lo define el ``id``, nada más.
    """

    @property
    def id(self) -> str:
        """Identificador lógico de la sección (``results.model``, ``appendix_tables``…)."""


_SectionT = TypeVar("_SectionT", bound=_Identified)

__all__ = [
    "APPENDIX_LINEAGE_ID",
    "APPENDIX_PARAMETERS_ID",
    "APPENDIX_PARAMETER_DOMAINS",
    "APPENDIX_TABLES_ID",
    "ATTACHMENT_ONLY_TABLES",
    "CANONICAL_SECTION_ORDER",
    "CHAPTER_SPECS",
    "COMPARISON_CONCENTRATION_TABLE",
    "COMPARISON_MODELS_TABLE",
    "COMPARISON_PROVISIONS_TABLE",
    "COMPARISON_PROVISION_TABLE",
    "COMPARISON_RUNS_TABLE",
    "COMPARISON_SAMPLES_TABLE",
    "COMPARISON_SECTIONS",
    "COMPARISON_TESTS_TABLE",
    "COMPARISON_VARIABLES_TABLE",
    "CONTEXT_DOMAINS",
    "DOMAIN_TITLES",
    "EDA_DEFAULT_RATE_TABLE",
    "EXECUTIVE_SUMMARY_ID",
    "HL_GROUP_TABLE_PREFIX",
    "IFRS9_DOMAINS",
    "IFRS9_EXTRA_SECTIONS",
    "KEY_TABLES",
    "MASTER_SCALE_CUTOFFS_TABLE",
    "MASTER_SCALE_SCALE_TABLE",
    "METHODOLOGY_STEPS",
    "MONITORING_GRADES_TABLE",
    "MONITORING_SECTIONS",
    "MONITORING_SERIES_TABLE",
    "MONITORING_VARIABLES_TABLE",
    "PER_OBSERVATION_TABLES",
    "PIPELINE_DOMAINS",
    "RESULT_DOMAINS",
    "STABILITY_PSI_BY_PERIOD_TABLE",
    "SURVIVAL_PD_BY_PERIOD_TABLE",
    "VALIDATION_FAMILIES",
    "ChapterSpec",
    "domain_section_id",
    "domain_title",
    "internal_grouping_label",
    "max_visible_rows",
    "ordered_sections",
    "section_sort_key",
    "table_title",
]

# Los ocho dominios del pipeline scorecard F1, en el orden en que se ejecutan.
PIPELINE_DOMAINS: Final[tuple[str, ...]] = (
    "eda",
    "binning",
    "selection",
    "model",
    "scorecard",
    "calibration",
    "performance",
    "stability",
)

DOMAIN_TITLES: Final[dict[str, str]] = {
    "lgd_training": "Entrenamiento LGD con historia separada",
    "data": "Población, particiones y exclusiones",
    "eda": "Población y calidad de datos",
    "binning": "Binning WoE y poder predictivo",
    "selection": "Selección de variables",
    "model": "Modelo PD",
    "scorecard": "Scorecard",
    "calibration": "Calibración",
    "performance": "Desempeño y discriminación",
    "stability": "Estabilidad",
    "validation": "Validación formal",
    "master_scale": "Escala maestra y puntos de corte",
    # SDD-33 capa B: el capítulo de una corrida de monitoreo y sus parámetros en el anexo C.
    "monitoring": "Monitoreo del modelo en uso",
    # SDD-34 capa B: el capítulo de una corrida de comparación y su parámetro en el anexo C.
    "comparison": "Comparación de modelos",
    "survival": "Supervivencia y curva PD lifetime",
    "markov": "Matrices de transición",
    "forward": "Escenarios forward-looking",
    # El título nombra el país: el informe circula fuera de Chile y «la CMF» no es un referente
    # universal. Sin el rótulo, un lector de otra jurisdicción recibe un documento formalmente
    # impecable del que no puede deducir qué norma se aplicó.
    #
    # ⚠️ El de `provisioning` es el título NEUTRO, y el rótulo del país lo pone `domain_title()`
    # cuando la comparación configurada es de verdad la del B-1 (D-MAX-2). Hasta el 2026-08-04 este
    # literal decía «la regla del máximo (Chile)» **siempre**, incluso comparando contra IFRS 9 —una
    # comparación que ninguna norma chilena pide—, con el matiz enterrado en el cuerpo del capítulo.
    "provisioning": "La provisión a reportar — comparación entre dos métodos",
    "provisioning_cmf": "Método estándar de la CMF de Chile (Cap. B-1)",
    "provisioning_internal": "Método interno del banco",
    "provisioning_ifrs9": "Pérdida crediticia esperada (ECL) por etapas",
}

#: Título del capítulo de orquestación cuando la comparación **sí** es la que exige el Cap. B-1.
_TITULO_PROVISIONING_B1: Final = "La provisión a constituir — la regla del máximo (Chile)"

#: Nombres cortos con que la card publica cada fuente (``SOURCE_NAMES`` de ``provisioning/config``).
_FUENTES_DEL_B1: Final[frozenset[str]] = frozenset({"cmf", "internal"})


def domain_title(domain: str, card: Mapping[str, Any] | None = None) -> str:
    """Título del capítulo de un dominio, rotulando el país sólo cuando corresponde (D-MAX-2).

    🔴 **Un título es lo primero que se lee, y hasta el 2026-08-04 éste afirmaba «(Chile)» sobre
    cualquier comparación**, incluida `max(CMF, IFRS 9)` — que no es la regla del B-1 y que el
    propio motor etiqueta en su lineage como *«comparativo entre marcos contables SIN norma
    chilena que lo exija»*. El lector veía el titular con la bandera y la cifra; el matiz vivía
    enterrado en el cuerpo del capítulo.

    El criterio es **el mismo que la prosa ya calcula** (`prose.py:1512-1513`) y el mismo que el
    orquestador usa para su etiqueta regulatoria (`orchestrator.py:767-768`): las dos fuentes son
    el método estándar y el interno, **y** la comparación es a nivel de institución. Se reutiliza
    en vez de reimplementarse: un criterio *parecido* rotularía «Chile» donde el lineage dice que
    no.

    Sin card no se rotula: afirmar el país sin el dato es exactamente lo que esta función arregla.
    """
    if domain != "provisioning" or card is None:
        return DOMAIN_TITLES[domain]
    fuentes = {str(card.get("source_a") or ""), str(card.get("source_b") or "")}
    nivel = str(card.get("comparison_level") or "")
    if fuentes == _FUENTES_DEL_B1 and nivel == "total":
        return _TITULO_PROVISIONING_B1
    return DOMAIN_TITLES[domain]


# Dominios que alimentan el capítulo de Contexto (población) y los de Resultados (el cuerpo).
CONTEXT_DOMAINS: Final[tuple[str, ...]] = ("data", "eda")
RESULT_DOMAINS: Final[tuple[str, ...]] = (
    "binning",
    "selection",
    "model",
    "scorecard",
    "calibration",
    "performance",
    "stability",
    # La escala maestra (SDD-32, capa B): la última etapa del scorecard, con su card. Sin la etapa
    # no hay card y la subsección no se emite: el informe de una corrida sin escala no cambia.
    "master_scale",
)
# Subsecciones del capítulo CONDICIONAL de provisiones (SDD-28 D5). El orquestador primero (es el
# titular: la provisión a constituir y el sobrecosto del estándar), luego el desglose de cada
# método; las que no publicaron card se omiten solas.
# ⚠️ Esta tupla es TAMBIÉN el gate del capítulo desde D-CAP-1: se emite si corrió **cualquiera** de
# los tres (``requires_any_domain``), no si corrió el orquestador. Decir lo segundo dejaba sin
# capítulo a toda corrida de un solo motor, porque el orquestador exige dos fuentes distintas.
PROVISION_DOMAINS: Final[tuple[str, ...]] = (
    "provisioning",
    "provisioning_cmf",
    "provisioning_internal",
)
# Subsecciones del capítulo CONDICIONAL de IFRS 9 (SDD-16). La card del step ``provisioning_ifrs9``
# trae staging, EAD y ECL reportada; antes, la curva de PD de la etapa de supervivencia, si corrió
# (FLUJO-GUIADO-IFRS9 D-ECL-12): es lo primero que lee un validador de la provisión, y hasta la
# capa C sólo vivía en el anexo C.2 como card. Cada una se emite sólo si su dominio corrió.
IFRS9_DOMAINS: Final[tuple[str, ...]] = ("survival", "provisioning_ifrs9")
# Y dos subsecciones que no son un dominio con card sino lo que la provisión hizo con los
# escenarios de la institución y con la PD del modelo (IFRS9-FIRMABLE capa C, D-FIR-11): sólo se
# emiten cuando la corrida los trae, con las líneas y tablas de los resúmenes de etapa
# (`guided.summaries.ifrs9_report_extras`). La de escenarios va entre la curva y la provisión —el
# orden del pipeline—; la de la PD, tras la provisión.
IFRS9_EXTRA_SECTIONS: Final[dict[str, str]] = {
    "forward": "Escenarios y ajuste por ciclo",
    "pd_model": "La PD de tu modelo y el aumento significativo del riesgo",
}
_IFRS9_CHILDREN: Final[tuple[str, ...]] = ("survival", "forward", "provisioning_ifrs9", "pd_model")

# Familias publicadas por el ``ValidationResult`` atómico (SDD-22), en el orden metodológico del
# capítulo condicional. Solo se emiten las declaradas en ``card.families_run``.
VALIDATION_FAMILIES: Final[tuple[tuple[str, str], ...]] = (
    ("discrimination", "Discriminación"),
    ("calibration", "Calibración"),
    ("stability", "Estabilidad"),
    ("backtesting", "Backtesting realizado vs. estimado"),
)

# El Anexo C no redefine el pipeline scorecard: añade los dominios F3/F4 que realmente corrieron.
# Mantener esta tupla separada evita que provisiones/survival/IFRS 9 se vuelvan requisitos
# implícitos de F1.
APPENDIX_PARAMETER_DOMAINS: Final[tuple[str, ...]] = (
    "lgd_training",
    "data",
    *PIPELINE_DOMAINS,
    "survival",
    "markov",
    "forward",
    *PROVISION_DOMAINS,
    "provisioning_ifrs9",
    "validation",
    # Los cortes y el puntaje de aprobación que declaró la institución (SDD-32, capa B).
    "master_scale",
    # La tarjeta, la columna de periodo y la de desenlace del monitoreo (SDD-33, capa B).
    "monitoring",
    # Las corridas comparadas, en orden (SDD-34, capa B).
    "comparison",
)

APPENDIX_LINEAGE_ID: Final = "appendix_lineage"
APPENDIX_TABLES_ID: Final = "appendix_tables"
APPENDIX_PARAMETERS_ID: Final = "appendix_parameters"
EXECUTIVE_SUMMARY_ID: Final = "executive_summary"
"""La página ejecutiva: el resumen final de la corrida (D-FLU-4), tras la portada."""

# Etapas que describe el capítulo de Metodología, en el orden en que ocurrieron. ``data`` aporta
# config y una card de población opcional; su tratamiento debe quedar escrito aun sin esa card.
METHODOLOGY_STEPS: Final[tuple[tuple[str, str], ...]] = (
    ("lgd_training", "Ajuste y evaluación de LGD"),
    ("data", "Tratamiento de datos y particiones"),
    ("binning", "Binning WoE"),
    ("selection", "Selección de variables"),
    ("model", "Estimación del modelo PD"),
    ("scorecard", "Escalado del scorecard"),
    ("calibration", "Calibración de la PD"),
    ("provisioning_ifrs9", "Ficha metodológica IFRS 9 / ECL"),
    # SDD-33 capa B: la referencia, los cuatro indicadores, sus umbrales fijos y la tabla de
    # decisión de una corrida de monitoreo.
    ("monitoring", "Cómo se monitorea el modelo"),
    # SDD-34 capa B: la muestra de evaluación, la comparabilidad, la prueba, el PSI común, el
    # índice y la frontera de una corrida de comparación.
    ("comparison", "Cómo se comparan los modelos"),
)

#: La PD acumulada por período y cartera de la curva de supervivencia. No es un artefacto del motor:
#: la arma el builder con la misma función que la etapa «Curva de PD» del resumen
#: (:func:`bayesrisk.guided.summaries.pd_curve_by_portfolio`), una sola fuente (D-SIM-5).
SURVIVAL_PD_BY_PERIOD_TABLE: Final = "survival.pd_by_period"

#: Las dos tablas del cuerpo de «Escala maestra y puntos de corte» (SDD-32, capa B): los tramos con
#: su PD y su lectura por muestra, y la tabla de puntos de corte. No son artefactos del motor: las
#: arma el builder con la MISMA función que el resumen de la etapa
#: (:func:`bayesrisk.guided.summaries.master_scale_report_extras`), ya escritas como las lee una
#: persona; los artefactos completos (``master_scale.grades``, ``grade_table``, ``cutoff_table``)
#: van al anexo de tablas.
MASTER_SCALE_SCALE_TABLE: Final = "master_scale.scale"
MASTER_SCALE_CUTOFFS_TABLE: Final = "master_scale.cutoffs"

#: La serie de PSI por período de la estabilidad (SDD-33 D-MNT-9): la calculaba la etapa y no se
#: publicaba. La arma el builder desde el resumen «Estabilidad» (una sola fuente, D-SIM-5).
STABILITY_PSI_BY_PERIOD_TABLE: Final = "stability.psi_by_period"

#: Las tres tablas del cuerpo del capítulo «Monitoreo del modelo en uso» (SDD-33, capa B): la serie
#: por periodo con su veredicto, cada tramo por periodo y el CSI de cada variable. No son artefactos
#: del motor: las arma el builder con la MISMA función que el resumen de la etapa
#: (:func:`bayesrisk.guided.summaries.monitoring_report_extras`); los artefactos completos
#: (``monitoring.periods``, ``grades_by_period``, ``variables_by_period``) van al anexo de tablas.
MONITORING_SERIES_TABLE: Final = "monitoring.series"
MONITORING_GRADES_TABLE: Final = "monitoring.by_grade"
MONITORING_VARIABLES_TABLE: Final = "monitoring.by_variable"

#: Las subsecciones del capítulo del monitoreo: id → (título, tablas del cuerpo). El cuerpo de la
#: primera son las líneas y las alertas del resumen; las otras dos, su tabla.
MONITORING_SECTIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "verdict": ("Veredicto y serie por periodo", (MONITORING_SERIES_TABLE,)),
    "grades": ("Cada tramo por periodo", (MONITORING_GRADES_TABLE,)),
    "variables": ("Cada variable por periodo", (MONITORING_VARIABLES_TABLE,)),
}

#: Las tablas del cuerpo del capítulo «Comparación de modelos» (SDD-34, capa B). No son artefactos
#: del motor: las arma el builder con la MISMA función que el resumen de la etapa
#: (:func:`bayesrisk.guided.summaries.comparison_report_extras`); la tabla de modelos se reparte por
#: columnas entre discriminación y concentración. Los artefactos completos (``comparison.runs``,
#: ``models``, ``tests``, ``samples``, ``variables``, ``provision``) van al anexo de tablas.
COMPARISON_RUNS_TABLE: Final = "comparison.runs_compared"
COMPARISON_MODELS_TABLE: Final = "comparison.discrimination_table"
COMPARISON_TESTS_TABLE: Final = "comparison.paired_tests"
COMPARISON_SAMPLES_TABLE: Final = "comparison.samples_table"
COMPARISON_CONCENTRATION_TABLE: Final = "comparison.concentration_table"
COMPARISON_VARIABLES_TABLE: Final = "comparison.variables_table"
COMPARISON_PROVISIONS_TABLE: Final = "comparison.provisions"
COMPARISON_PROVISION_TABLE: Final = "comparison.provision_by_stage"

#: Las subsecciones del capítulo de la comparación: id → (título, tablas del cuerpo). La primera y
#: la última llevan su texto —la lectura con qué revisar, y la elección— aunque no tengan tabla;
#: las demás se emiten sólo si su tabla se publicó (una comparación de IFRS 9 no tiene gráficos ni
#: variables; una de scorecards no tiene provisión). Los dos gráficos van en «discrimination» y
#: «concentration».
COMPARISON_SECTIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "reading": ("Las corridas y su comparabilidad", (COMPARISON_RUNS_TABLE,)),
    "discrimination": (
        "Discriminación y estabilidad",
        (COMPARISON_MODELS_TABLE, COMPARISON_TESTS_TABLE, COMPARISON_SAMPLES_TABLE),
    ),
    "concentration": ("Concentración de los tramos", (COMPARISON_CONCENTRATION_TABLE,)),
    "variables": ("Las variables de cada modelo", (COMPARISON_VARIABLES_TABLE,)),
    "provision": (
        "Provisión por etapa",
        (COMPARISON_PROVISIONS_TABLE, COMPARISON_PROVISION_TABLE),
    ),
    "choice": ("La elección", ()),
}

# Tablas que el CUERPO del informe muestra por dominio: las que un validador necesita leer para
# formarse un juicio. El Anexo de tablas publica el RESTO de las tablas agregadas de la corrida —lo
# que el cuerpo no mostró, no lo que ya mostró—: el cuerpo cura, el anexo completa. Repetir una
# tabla íntegra en dos sitios no añade trazabilidad, añade páginas.
KEY_TABLES: Final[dict[str, tuple[str, ...]]] = {
    "lgd_training": (
        "lgd_training.coefficients",
        "lgd_training.evaluation_readable",
        "lgd_training.population_readable",
    ),
    "data": ("data.states", "data.partitions", "data.exclusions"),
    # 🔴 Las claves llevan el nombre de la TABLA dentro del artefacto: los artefactos de `eda`
    # son DTOs que envuelven su frame (`DefaultRateResult.by_period`, `QualityResult.by_column`)
    # y el builder los aplana con ese sufijo. Hasta la capa 3 del scorecard completo esta lista
    # decía `eda.default_rate`/`eda.quality`, que no casaban con ninguna tabla del bundle, así que
    # la subsección «Población y calidad de datos» salía SIN tablas en el cuerpo y las dos iban
    # al anexo con su clave cruda por título. Medido sobre el informe de una corrida real.
    "eda": ("eda.default_rate.by_period", "eda.quality.by_column"),
    "binning": ("binning.summary",),
    "selection": ("selection.selection_table", "selection.vif_table"),
    "model": ("model.coefficients", "model.fit_statistics"),
    "scorecard": ("scorecard.scorecard",),
    "calibration": ("calibration.parameters",),
    "performance": ("performance.discriminant_metrics", "performance.performance_table"),
    "stability": (
        "stability.stability_metrics",
        "stability.psi_table",
        STABILITY_PSI_BY_PERIOD_TABLE,
    ),
    "provisioning": ("provisioning.comparison",),
    "provisioning_cmf": ("provisioning_cmf.summary",),
    "provisioning_internal": ("provisioning_internal.groups",),
    # La curva de PD de una provisión (D-ECL-12): la PD acumulada por período y cartera —la misma
    # tabla que la etapa «Curva de PD» del resumen— y los coeficientes del ajuste.
    "survival": (SURVIVAL_PD_BY_PERIOD_TABLE, "survival.coefficients"),
    "provisioning_ifrs9": ("provisioning_ifrs9.summary",),
    # «Escenarios y ajuste por ciclo» (IFRS9-FIRMABLE capa C): los escenarios con sus pesos, la
    # sensibilidad, la ECL por escenario y el desplazamiento por tramo —la curva consumida—.
    "forward": (
        "forward.scenarios",
        "forward.sensitivity",
        "provisioning_ifrs9.ecl_by_scenario",
        "provisioning_ifrs9.shift_by_period",
    ),
    "master_scale": (MASTER_SCALE_SCALE_TABLE, MASTER_SCALE_CUTOFFS_TABLE),
    # El capítulo del monitoreo (SDD-33, capa B): cada subsección muestra su tabla.
    **{f"monitoring.{hijo}": tablas for hijo, (_titulo, tablas) in MONITORING_SECTIONS.items()},
    # El capítulo de la comparación (SDD-34, capa B): cada subsección muestra sus tablas.
    **{f"comparison.{hijo}": tablas for hijo, (_titulo, tablas) in COMPARISON_SECTIONS.items()},
}

#: La tabla de la tasa por período o cohorte, que además del máximo configurable de filas por
#: tabla lleva el tope contractual de :data:`bayesrisk.eda.default_rate.MAX_PUBLISHED_PERIODS`.
EDA_DEFAULT_RATE_TABLE: Final = "eda.default_rate.by_period"


def max_visible_rows(table_key: str, max_table_rows: int) -> int:
    """Cuántas filas de ``table_key`` muestra el documento: el configurable, o menos.

    ``report.sections.max_table_rows`` acota lo que se muestra de cualquier tabla y no tiene
    máximo; la tasa por período o cohorte tiene además un tope CONTRACTUAL —1.000, el mismo que la
    respuesta de la interfaz (cierre 1 de D-SC)—, porque una cohorte casi única trae una fila por
    operación y un máximo configurado alto volvía a materializar la tabla entera en el HTML, el
    QMD y el Word (pasada 7 de la revisión adversarial). El total y el aviso «mostrando N de M»
    siguen contando la tabla entera; la tabla completa queda como artefacto de la corrida.
    """
    if table_key == EDA_DEFAULT_RATE_TABLE:
        from bayesrisk.eda.default_rate import MAX_PUBLISHED_PERIODS  # perezoso: dominio

        return min(max_table_rows, MAX_PUBLISHED_PERIODS)
    return max_table_rows


# Tablas **por observación**: una fila por crédito/cliente. Son frames del dataset, no resúmenes, y
# NO pertenecen al documento: truncadas no sirven como dato (están incompletas) ni como informe
# (nadie lee 200 filas de puntajes). Salen del cuerpo y de los anexos, y se emiten completas como
# exports de datos (:mod:`bayesrisk.report.exports`), referenciadas desde el Anexo de tablas.
#
# El criterio es la **naturaleza** de la tabla, no su tamaño: una tabla agregada con muchas filas
# (p. ej. el PSI por tramo de score, o el binning de una variable con muchos bins) se queda en el
# documento porque es lo que un validador revisa. Por eso la lista es explícita y no un umbral de
# filas: un umbral expulsaría del informe justo la evidencia que lo sostiene.
PER_OBSERVATION_TABLES: Final[frozenset[str]] = frozenset(
    {
        "lgd_training.predictions",
        "provisioning_internal.detail",
        "provisioning_internal.pd_input",
        "binning.woe_frame",
        "calibration.calibrated_pd_frame",
        "calibration.out_of_model_calibrated_pd_frame",
        "model.raw_pd_frame",
        "scorecard.score",
        "scorecard.out_of_model_score",
        "selection.selected_woe_frame",
    }
)

# La tabla global de coeficientes es un transporte canónico, no una tabla por operación.
# Se entrega íntegra como adjunto; su vista decodificada sí pertenece al cuerpo del informe.
ATTACHMENT_ONLY_TABLES: Final = PER_OBSERVATION_TABLES | {"lgd_training.model_table"}

# Títulos legibles por artefacto tabular: el informe habla de "Coeficientes del modelo PD", no de
# `model.coefficients`. Las claves dinámicas (una tabla por variable) se resuelven en `table_title`.
_TABLE_TITLES: Final[dict[str, str]] = {
    "binning.bin_edges": "Bordes numéricos originales de los tramos",
    "binning.cut_dictionary": "Diccionario exacto de reglas por tramo",
    "eda.stability": "Evidencia original de estabilidad del análisis exploratorio",
    "stability.temporal_records": "Estabilidad temporal completa, incluidos los percentiles",
    "validation.hosmer_lemeshow_groups": "Grupos HL convencionales: valores originales",
    "binning.event_rate_by_partition": "Tasa de malos por tramo y muestra: soporte íntegro",
    "binning.unseen_categories": "Categorías no vistas por variable y muestra",
    "selection.iv_by_partition": "IV por variable y muestra: soporte íntegro",
    "stability.out_of_model_psi": "PSI de la población fuera del ajuste",
    "lgd_training.model_table": "Modelo LGD reutilizable (tabla de transporte)",
    "lgd_training.coefficients": "Coeficientes del modelo LGD",
    "lgd_training.predictions": "LGD observada y predicha por operación elegible",
    "lgd_training.evaluation": "Diagnósticos completos de entrenamiento y evaluación",
    "lgd_training.population": "Conteos completos de población y exclusiones",
    "lgd_training.evaluation_readable": "Evaluación descriptiva y media de referencia",
    "lgd_training.population_readable": "Población y exclusiones de la historia",
    "provisioning_internal.detail": (
        "Detalle de provisión interna por operación (prorrateo del grupo)"
    ),
    "provisioning_internal.pd_input": "PD consumida para toda la cartera",
    "provisioning_internal.pd_coverage": "Cobertura de PD de la cartera",
    "data.states": "Estados de la población",
    "data.partitions": "Particiones de modelamiento",
    "data.exclusions": "Exclusiones aplicadas",
    "eda.default_rate.by_period": "Tasa de incumplimiento observada por período o cohorte",
    "eda.quality.by_column": "Calidad de datos por columna",
    "binning.summary": "Resumen de binning — IV por variable",
    "binning.woe_frame": "Dataset transformado a WoE",
    "selection.selection_table": "Criterios de selección por variable",
    "selection.correlation_matrix": "Matriz de correlación entre variables",
    "selection.vif_table": "Factor de inflación de varianza (VIF)",
    "selection.stability_table": "Estabilidad de las variables candidatas",
    "selection.selected_woe_frame": "Dataset WoE de las variables seleccionadas",
    "model.coefficients": "Coeficientes del modelo PD",
    "model.stepwise_trace": "Traza del procedimiento stepwise",
    "model.fit_statistics": "Estadísticos de ajuste del modelo",
    "model.raw_pd_frame": "PD sin calibrar por observación",
    "scorecard.scorecard": "Scorecard — puntajes por atributo",
    "scorecard.score": "Puntaje por observación",
    "scorecard.out_of_model_score": "Puntaje de las operaciones fuera del ajuste (TTD)",
    "calibration.parameters": "Parámetros de la calibración",
    "calibration.calibrated_pd_frame": "PD calibrada por observación",
    "calibration.out_of_model_calibrated_pd_frame": (
        "PD calibrada de las operaciones fuera del ajuste (TTD)"
    ),
    "performance.performance_table": "Desempeño por tramo de riesgo",
    "performance.discriminant_metrics": "Métricas de discriminación por partición",
    "stability.psi_table": "PSI por tramo de score",
    "stability.stability_metrics": "Métricas de estabilidad (PSI/CSI)",
    "validation.discrimination": "Validación formal — discriminación",
    "validation.calibration": "Validación formal — calibración",
    "validation.stability": "Validación formal — estabilidad",
    "validation.backtesting": "Validación formal — backtesting",
    "provisioning.comparison": "Comparación estándar vs. interno y regla del máximo",
    "provisioning_cmf.summary": "Provisión estándar por categoría CMF",
    "provisioning_internal.groups": "Provisión interna por grupo homogéneo",
    "provisioning_ifrs9.summary": "Pérdida crediticia esperada (ECL) por etapa",
    SURVIVAL_PD_BY_PERIOD_TABLE: (
        "PD acumulada por período y cartera (promedio de las operaciones)"
    ),
    "survival.coefficients": "Coeficientes de la curva de PD (supervivencia)",
    # IFRS9-FIRMABLE capa C: las tablas de «Escenarios y ajuste por ciclo», las del resumen.
    "forward.scenarios": "Escenarios de la institución, con sus pesos",
    "forward.sensitivity": "La sensibilidad estimada",
    "provisioning_ifrs9.ecl_by_scenario": (
        "ECL por escenario frente a la curva a lo largo del ciclo"
    ),
    "provisioning_ifrs9.shift_by_period": "Desplazamiento por tramo",
    # SDD-32 capa B: las dos tablas del cuerpo (desde el resumen) y los artefactos completos.
    MASTER_SCALE_SCALE_TABLE: "Escala maestra — los tramos y su PD",
    MASTER_SCALE_CUTOFFS_TABLE: "Tabla de puntos de corte",
    "master_scale.grades": "Tramos de la escala maestra",
    "master_scale.grade_table": "Tramos de la escala por muestra",
    "master_scale.cutoff_table": "Puntos de corte por muestra",
    STABILITY_PSI_BY_PERIOD_TABLE: "PSI del puntaje por período contra Desarrollo",
    # SDD-33 capa B: las tres tablas del cuerpo (desde el resumen) y los artefactos completos.
    MONITORING_SERIES_TABLE: "Monitoreo — la serie por periodo y su veredicto",
    MONITORING_GRADES_TABLE: "Monitoreo — cada tramo por periodo",
    MONITORING_VARIABLES_TABLE: "Monitoreo — el CSI de cada variable por periodo",
    "monitoring.periods": "Indicadores del monitoreo por periodo",
    "monitoring.grades_by_period": "Tramos de la escala por periodo",
    "monitoring.variables_by_period": "CSI de cada variable por periodo",
    # SDD-34 capa B: las tablas del cuerpo (desde el resumen) y los artefactos completos.
    COMPARISON_RUNS_TABLE: "Comparación — las corridas y su comparabilidad",
    COMPARISON_MODELS_TABLE: "Comparación — discriminación, estabilidad y frontera",
    COMPARISON_TESTS_TABLE: "Comparación — pruebas de DeLong pareadas",
    COMPARISON_SAMPLES_TABLE: "Comparación — cada modelo en cada muestra",
    COMPARISON_CONCENTRATION_TABLE: "Comparación — concentración de los tramos y frontera",
    COMPARISON_VARIABLES_TABLE: "Comparación — signo e IV de cada variable por modelo",
    COMPARISON_PROVISIONS_TABLE: "Comparación — cada provisión",
    COMPARISON_PROVISION_TABLE: "Comparación — provisión por etapa contra la referencia",
    "comparison.runs": "Corridas comparadas",
    "comparison.models": "Cifras de cada modelo comparado",
    "comparison.tests": "Pruebas entre pares de modelos",
    "comparison.samples": "Cada modelo en cada muestra",
    "comparison.variables": "Cada variable en cada modelo",
    "comparison.provision": "Provisión por etapa de cada corrida",
}
_BINNING_TABLE_PREFIX: Final = "binning.tables."
#: Prefijo de los perfiles por variable del análisis exploratorio (`UnivariateResult.profiles`,
#: aplanado por el builder con el nombre de la columna descrita).
_EDA_PROFILE_PREFIX: Final = "eda.univariate.profiles."
#: D-HLG-2: una tabla por muestra con los grupos del Hosmer-Lemeshow, en la subsección de
#: calibración (``validation.hosmer_lemeshow_groups.<muestra>``; la arma el builder).
HL_GROUP_TABLE_PREFIX: Final = "validation.hosmer_lemeshow_groups."


class ChapterSpec(BaseModel):
    """Capítulo declarado del documento: identidad, tipo de bloque y guía de placeholder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    kind: SectionKind
    numbered: bool = True
    placeholder_title: str = ""
    placeholder_guidance: tuple[str, ...] = ()
    requires_domain: str = ""
    """Dominio del que depende el capítulo. Si está informado y ese dominio **no corrió**, el
    capítulo **no se emite** (y la numeración de los siguientes se reajusta sola).

    Es el mecanismo de los capítulos **condicionales**: un informe de scorecard no debe traer un
    capítulo de provisiones vacío, y un informe con provisiones no debe declarar que no las cubre.
    Vacío (el default) = capítulo incondicional, se emite siempre.
    """
    requires_any_domain: tuple[str, ...] = ()
    """Variante *any-of* de ``requires_domain``: el capítulo se emite si **al menos uno** de estos
    dominios publicó card. Es el mecanismo de los capítulos cuyo cuerpo son subsecciones de
    dominio: un informe que no corrió ninguna etapa de scorecard (p. ej. la cadena standalone
    ``data → survival → provisioning_ifrs9``) no debe traer un capítulo «Resultados» vacío.
    Vacía (el default) = sin condición any-of.
    """
    requires_governance: bool = False
    """El capítulo se emite sólo si la corrida declaró ``governance`` (D-SC-13).

    Es el mismo tipo de predicado que ``requires_domain``: sin gobernanza no hay capítulo —ni vacío
    ni fabricado— y el documento no cambia una sola línea (D-SC-16).
    """
    requires_result: str = ""
    """Resultado atómico del que depende el capítulo.

    Este gate exige que el ``ReportInputBundle`` haya recolectado el DTO agregado bajo
    ``results[requires_result]``; una card resumen aislada no basta. Vacío = sin condición.
    """


# El documento. Portada y resumen ejecutivo los emite la plantilla (no son secciones lógicas: la
# portada son metadatos y el resumen es la vista de las métricas clave). Todo lo demás es sección.
CHAPTER_SPECS: Final[tuple[ChapterSpec, ...]] = (
    # La página ejecutiva (capa C de FLUJO-GUIADO-SCORECARD, D-FLU-4): el resumen final de la
    # corrida —los dos estados, las cifras clave, qué revisar, las decisiones humanas con motivo
    # y dónde queda cada archivo— desde los mismos constructores que `Scorecard.summary()` y que
    # la pestaña Resultados. Va tras la portada y antes del resumen ejecutivo: es materia
    # preliminar, sin número. CONDICIONAL any-of a los dominios del scorecard y a la provisión
    # IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-12): una provisión abre con SU resumen final —supuestos y
    # cinco cifras de provisión—. El builder además lo omite cuando el bundle no trae `summary` (un
    # bundle armado a mano, sin corrida) y cuando una corrida sin dominios del scorecard trae un
    # resumen que no es el de una provisión: no recibe el molde del scorecard.
    ChapterSpec(
        id=EXECUTIVE_SUMMARY_ID,
        title="Resumen de la corrida",
        kind="summary",
        numbered=False,
        requires_any_domain=(
            *RESULT_DOMAINS,
            "provisioning_ifrs9",
            "provisioning_internal",
            "monitoring",
            "comparison",
            "lgd_training",
        ),
    ),
    ChapterSpec(id="toc", title="Índice", kind="toc", numbered=False),
    ChapterSpec(
        id="introduction",
        title="Introducción",
        kind="prose",
        placeholder_title="Introducción",
        placeholder_guidance=(
            "Declara el propósito del informe y qué decisión habilita: ¿es una validación "
            "inicial previa a la puesta en producción, una revisión periódica o un "
            "recalibrado?",
            "Delimita el alcance (qué modelo y qué cartera cubre, qué queda fuera) e "
            "identifica la audiencia: Validación independiente, Comité de Riesgo, regulador.",
        ),
    ),
    # Capítulo CONDICIONAL a la gobernanza (capa 4 de SCORECARD-COMPLETO, D-SC-13): lo que la
    # institución declaró —propósito, supuestos, limitaciones, identidad de inventario— escrito
    # desde el config, con remisión a la ficha que el motor emite al cierre de la corrida.
    ChapterSpec(
        id="model_card",
        title="Ficha del modelo",
        kind="prose",
        requires_governance=True,
    ),
    ChapterSpec(
        id="context",
        title="Contexto del modelo y de la cartera",
        kind="prose",
        placeholder_title="Contexto del modelo",
        placeholder_guidance=(
            "Describe la cartera sobre la que se construyó el modelo: producto, segmento, "
            "volumen y período.",
            "Explicita la definición de incumplimiento utilizada (p. ej. 90+ días de mora) y "
            "por qué; declara las exclusiones aplicadas a la población y su justificación.",
        ),
    ),
    ChapterSpec(id="methodology", title="Metodología", kind="prose"),
    ChapterSpec(
        id="lgd_training", title="Entrenamiento LGD", kind="prose", requires_domain="lgd_training"
    ),
    # Capítulo CONDICIONAL any-of: sus subsecciones son los dominios del pipeline scorecard
    # (``RESULT_DOMAINS``). Una corrida que no ejecutó ninguno (p. ej. IFRS 9 standalone) no
    # emite un «Resultados» vacío: su resultado de negocio vive en el capítulo condicional
    # correspondiente (``provisions``/``ifrs9``) y la numeración se reajusta sola.
    ChapterSpec(id="results", title="Resultados", kind="prose", requires_any_domain=RESULT_DOMAINS),
    # Capítulo CONDICIONAL de validación formal (SDD-22): el DTO agregado es el oracle. Va
    # inmediatamente después de Resultados y antes de cualquier capítulo de provisiones.
    ChapterSpec(
        id="validation",
        title="Validación formal",
        kind="prose",
        requires_result="validation",
        placeholder_title="Veredicto de validación formal",
        placeholder_guidance=(
            "Emite el juicio humano sobre la aptitud del modelo para su uso previsto: aprobar, "
            "aprobar con observaciones o rechazar.",
            "Documenta observaciones, responsables, plazos y la fecha de la próxima revisión; "
            "el estado técnico del motor no sustituye este veredicto.",
        ),
    ),
    # Capítulo CONDICIONAL (SDD-28 D5): solo se emite si la corrida calculó provisiones. Va tras
    # Resultados —es un resultado de negocio, no una validación del scorecard— y antes de
    # Conclusiones, que pueden referirlo. En una corrida de scorecard no aparece y la numeración se
    # reajusta sola (``build_sections`` deriva los números de los capítulos emitidos).
    # D-CAP-1: se gatea por *any-of* sobre los tres dominios de provisiones, no por el orquestador.
    # 🔴 Con `requires_domain="provisioning"` una corrida de UN SOLO motor —la cadena neutra
    # `data → provisioning_internal → report`, que llega a `done` con informe— no traía este
    # capítulo, y su provisión salía sólo en el Anexo C, entre parámetros de configuración. La causa
    # era que el orquestador no puede existir con un motor solo: prohíbe `source_a == source_b`.
    # Gatear por el hecho («se calcularon provisiones») en vez de por la forma («se compararon dos
    # fuentes») cubre además el caso «sólo CMF», que tampoco tenía capítulo (D-CAP-3).
    ChapterSpec(
        id="provisions",
        title="Provisiones regulatorias",
        kind="prose",
        requires_any_domain=PROVISION_DOMAINS,
    ),
    # Capítulo CONDICIONAL de IFRS 9 (SDD-16): solo se emite si la corrida calculó la pérdida
    # crediticia esperada. Misma lógica que ``provisions``: es un resultado de negocio, va tras
    # Resultados y la numeración se reajusta sola cuando no aparece.
    ChapterSpec(
        id="ifrs9",
        title="Provisiones IFRS 9 / ECL",
        kind="prose",
        requires_domain="provisioning_ifrs9",
    ),
    # Capítulo CONDICIONAL del monitoreo (SDD-33, capa B): sólo se emite si la corrida monitoreó una
    # tarjeta. Es el resultado de la corrida —el veredicto y su serie—, va antes de Conclusiones y
    # la numeración se reajusta sola cuando no aparece.
    ChapterSpec(
        id="monitoring",
        title=DOMAIN_TITLES["monitoring"],
        kind="prose",
        requires_domain="monitoring",
    ),
    # Capítulo CONDICIONAL de la comparación (SDD-34, capa B): sólo si la corrida comparó modelos.
    ChapterSpec(
        id="comparison",
        title=DOMAIN_TITLES["comparison"],
        kind="prose",
        requires_domain="comparison",
    ),
    ChapterSpec(
        id="conclusions",
        title="Conclusiones y recomendación",
        kind="prose",
        placeholder_title="Conclusiones y recomendación",
        placeholder_guidance=(
            "Emite el juicio: ¿el modelo es apto para el uso previsto? La recomendación "
            "(aprobar, aprobar con observaciones o rechazar) la firma un humano, no el motor.",
            "Enumera las observaciones y condiciones de uso, con responsable y plazo para cada "
            "una, y fija la fecha de la próxima revisión.",
        ),
    ),
    ChapterSpec(id="limitations", title="Limitaciones y supuestos", kind="prose"),
    # Los anexos se numeran con letras (A/B/C) al construir el documento; el título no repite la
    # palabra "Anexo": la antepone el render, igual que hace con "1", "2"… en los capítulos.
    ChapterSpec(
        id=APPENDIX_LINEAGE_ID,
        title="Lineage y reproducibilidad",
        kind="appendix",
        numbered=False,
    ),
    ChapterSpec(
        id=APPENDIX_TABLES_ID,
        title="Tablas detalladas",
        kind="appendix",
        numbered=False,
    ),
    ChapterSpec(
        id=APPENDIX_PARAMETERS_ID,
        title="Parámetros completos",
        kind="appendix",
        numbered=False,
    ),
)

CANONICAL_SECTION_ORDER: Final[tuple[str, ...]] = tuple(spec.id for spec in CHAPTER_SPECS)
"""Orden canónico de los capítulos **posibles** del documento.

⚠️ **No es la lista de los capítulos emitidos.** Desde que existen capítulos condicionales
(``ChapterSpec.requires_domain``), un informe concreto emite un **subconjunto** de esta tupla,
preservando el orden relativo. Quien compare contra esta constante debe verificar *subsecuencia*,
no igualdad — un informe de scorecard no trae el capítulo de provisiones, y eso es lo correcto.
"""

_CHAPTER_INDEX: Final[dict[str, int]] = {spec.id: index for index, spec in enumerate(CHAPTER_SPECS)}
# Orden de las subsecciones dentro de cada capítulo que las admite.
_CHILD_ORDER: Final[dict[str, tuple[str, ...]]] = {
    "context": CONTEXT_DOMAINS,
    "methodology": tuple(step for step, _ in METHODOLOGY_STEPS),
    "results": RESULT_DOMAINS,
    "validation": tuple(family for family, _ in VALIDATION_FAMILIES),
    "provisions": PROVISION_DOMAINS,
    "ifrs9": _IFRS9_CHILDREN,
    "monitoring": tuple(MONITORING_SECTIONS),
    "comparison": tuple(COMPARISON_SECTIONS),
    APPENDIX_PARAMETERS_ID: APPENDIX_PARAMETER_DOMAINS,
}


def domain_section_id(parent_id: str, domain: str) -> str:
    """Deriva el id estable de una subsección de dominio dentro de su capítulo."""
    return f"{parent_id}.{domain}"


def section_sort_key(section_id: str) -> tuple[int, int]:
    """Clave de orden canónica de una sección: su capítulo y su posición dentro de él.

    Es la **única** definición del orden del documento. Un id desconocido cae al final en vez de
    romper el render: el informe nunca deja de emitirse por una sección inesperada.
    """
    parent, separator, child = section_id.partition(".")
    parent_index = _CHAPTER_INDEX.get(parent, len(CHAPTER_SPECS))
    if not separator:
        return (parent_index, 0)
    children = _CHILD_ORDER.get(parent, ())
    if child in children:
        return (parent_index, children.index(child) + 1)
    return (parent_index, len(children) + 1)


def ordered_sections(sections: Iterable[_SectionT]) -> tuple[_SectionT, ...]:
    """Ordena secciones por la clave canónica del documento.

    Vive aquí —y no en cada renderer— porque el orden del documento es **uno**: el HTML, el
    ``.qmd``, el ``.docx`` y la narrativa IA recorren los capítulos en la misma secuencia. Antes
    había una copia de esta función por consumidor, que es exactamente como se desincronizan.
    """
    return tuple(sorted(sections, key=lambda section: (*section_sort_key(section.id), section.id)))


def internal_grouping_label(grouping: str) -> str:
    """Rotula el agrupamiento interno efectivo sin asumir la configuración por defecto."""
    return {
        "score_band": "banda de score",
        "segment": "segmento",
        "provided": "grupo provisto",
    }.get(grouping, "grupo homogéneo")


def table_title(key: str, *, internal_grouping: str | None = None) -> str:
    """Traduce la clave interna de una tabla a un título legible por un humano.

    Las claves dinámicas (``binning.tables.<variable>``) nombran una variable del cliente: se
    muestra tal cual, entre comillas, sin inventarle acentos ni traducirla. Una clave desconocida
    degrada a su propio nombre en vez de romper el render.
    """
    if key == "provisioning_internal.groups" and internal_grouping:
        grouping_label = internal_grouping_label(internal_grouping)
        return f"{_TABLE_TITLES[key]} ({grouping_label})"
    if key in _TABLE_TITLES:
        return _TABLE_TITLES[key]
    if key.startswith(_BINNING_TABLE_PREFIX):
        variable = key[len(_BINNING_TABLE_PREFIX) :]
        return f"Tabla de binning WoE — variable «{variable}»"
    if key.startswith(_EDA_PROFILE_PREFIX):
        variable = key[len(_EDA_PROFILE_PREFIX) :]
        return f"Perfil frente al incumplimiento — variable «{variable}»"
    if key.startswith("validation.calibration_tie_groups."):
        from bayesrisk.report.prose import _PARTITION_LABELS

        muestra = key.removeprefix("validation.calibration_tie_groups.")
        return f"Diagnóstico descriptivo de calibración · {_PARTITION_LABELS.get(muestra, muestra)}"
    if key.startswith(HL_GROUP_TABLE_PREFIX):
        # Perezoso: la prosa importa este módulo.
        from bayesrisk.report.prose import _PARTITION_LABELS

        muestra = key[len(HL_GROUP_TABLE_PREFIX) :]
        return f"Hosmer-Lemeshow convencional por grupo · {_PARTITION_LABELS.get(muestra, muestra)}"
    return f"Tabla «{key}»"
