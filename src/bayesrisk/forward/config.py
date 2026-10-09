"""Config declarativo de la capa ``forward`` (SDD-20 §5).

:class:`ForwardConfig` es la sección ``forward`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`: proyecciones macro, modelos satellite,
escenarios ponderados y reversión TTC para forward-looking. Toda clase hereda de
:class:`~bayesrisk.core.config.BayesRiskBaseConfig` (``extra='forbid'`` y ``frozen=True``); cada
campo declara ``title``/``description`` y metadatos ``ui_*`` para que la UI (SDD-23) sea un editor
del mismo config. La sección es computacional, por lo que entra al ``config_hash`` global cuando
está activa.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import warnings
from math import isclose, isfinite
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig, declara_esenciales
from bayesrisk.forward.exceptions import (
    ForwardConfigError,
    ForwardScenarioError,
    PitConsistencyError,
    SatelliteModelError,
)

MacroSourceType = Literal["path", "artifact", "dataframe"]
MacroModelKind = Literal["arima", "sarima", "arimax", "auto_arima", "var", "vecm", "scenario_paths"]
SatelliteMode = Literal["fit", "fixed_coefficients", "reference_rate"]
TargetComponent = Literal["pd", "lgd"]
TermStructureSource = Literal["survival", "markov"]
PdBasisAssumption = Literal["pit", "ttc"]
TtcReversionMethod = Literal["linear_logit", "none"]
TtcAnchor = Literal["input_term_structure", "historical_mean"]

__all__ = [
    "ForwardConfig",
    "ForwardInputConfig",
    "ForwardValidationConfig",
    "MacroModelConfig",
    "MacroModelKind",
    "MacroSourceConfig",
    "MacroSourceType",
    "PdBasisAssumption",
    "SatelliteConfig",
    "SatelliteMode",
    "ScenarioConfig",
    "ScenarioDefinitionConfig",
    "TargetComponent",
    "TermStructureSource",
    "TtcAnchor",
    "TtcReversionConfig",
    "TtcReversionMethod",
]

#: Prefijo de la ruta de este dominio en ``BayesRiskConfig``, para anclar sus errores (D-EXI-5).
#:
#: ⚠️ En UN solo sitio y no repetido en cada ``raise``: la ruta que el error declara tiene que ser
#: **absoluta desde la raíz del config** —el ``except`` que la traduce vive en el endpoint y atrapa
#: la validación del ``BayesRiskConfig`` entero, así que ahí ya no se sabe qué sección la emitió—, y
#: eso ata al dominio con el nombre de su campo en la raíz. Concentrado aquí, lo vigila un gate que
#: exige que toda ruta declarada resuelva contra ``BayesRiskConfig``.
_LOC_SECCION: tuple[str, ...] = ("forward",)

_AUTO_ORDER_KINDS: frozenset[str] = frozenset({"arima", "sarima", "arimax"})
_REQUIRES_MULTIVARIATE: frozenset[str] = frozenset({"var", "vecm"})
_RESERVED_SCENARIO_NAMES: frozenset[str] = frozenset({"mean", "average", "weighted_mean_input"})
_REQUIRED_SCENARIOS: frozenset[str] = frozenset({"base", "adverse", "severe"})
_STRESS_SCENARIOS: frozenset[str] = frozenset({"adverse", "severe"})


def _is_non_finite_number(value: Any) -> bool:
    """Indica si un valor numérico serializable representa NaN o infinito."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return not isfinite(numeric)


class MacroSourceConfig(BayesRiskBaseConfig):
    """Configuración de fuente y columnas macroeconómicas."""

    type: MacroSourceType = Field(
        default="path",
        title="Tipo de fuente macro",
        description="De dónde se lee la historia macro: un archivo o el resultado de una etapa.",
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Fuente macro", "ui_order": 1},
    )
    path: str | None = Field(
        default=None,
        title="Tabla de historia",
        description=(
            "El archivo con la historia de la tasa de referencia y sus variables macro. La "
            "pantalla lo escribe al subir la tabla."
        ),
        json_schema_extra={
            # IFRS9-FIRMABLE D-FIR-11 (§13): uno de los tres esenciales de la pantalla —la tabla de
            # historia—, que la pantalla escribe al subirla.
            "ui_essential": True,
            "ui_widget": "text_input",
            "ui_group": "Fuente macro",
            "ui_order": 2,
        },
    )
    artifact_domain: str | None = Field(
        default=None,
        title="Dominio de artefacto macro",
        description="La etapa que publicó la historia, cuando se lee de un resultado.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Fuente macro", "ui_order": 3},
    )
    artifact_key: str | None = Field(
        default=None,
        title="Clave de artefacto macro",
        description="El resultado de esa etapa que trae la historia.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Fuente macro", "ui_order": 4},
    )
    time_col: str = Field(
        default="period",
        title="Columna temporal macro",
        description="Columna de período o fecha ordenable del histórico macro.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Fuente macro", "ui_order": 5},
    )
    frequency: str | None = Field(
        default=None,
        title="Frecuencia macro",
        description="Frecuencia declarativa opcional de la serie macro.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Fuente macro", "ui_order": 6},
    )
    variable_cols: tuple[str, ...] = Field(
        default=...,
        min_length=1,
        title="Variables macro proyectadas",
        description=(
            "Las variables macro de la historia. Con los escenarios de la institución, las "
            "columnas comunes a las dos tablas: se leen al subirlas."
        ),
        json_schema_extra={"ui_widget": "multiselect", "ui_group": "Fuente macro", "ui_order": 7},
    )
    exogenous_cols: tuple[str, ...] = Field(
        default=(),
        title="Variables exógenas",
        description="Columnas exógenas requeridas por la ruta ARIMAX.",
        json_schema_extra={"ui_widget": "multiselect", "ui_group": "Fuente macro", "ui_order": 8},
    )

    @model_validator(mode="before")
    @classmethod
    def _check_variables_raw(cls, data: Any) -> Any:
        """Valida temprano ``variable_cols`` vacío para levantar ``ForwardConfigError``."""
        if not isinstance(data, dict) or "variable_cols" not in data:
            return data
        raw = data["variable_cols"]
        if raw is None:
            raise ForwardConfigError(
                "macro_source.variable_cols no puede estar vacío.",
                # D-EXI-5: el error se ANCLA a su campo, para que el formulario pueda llevar ahí al
                # usuario en vez de dejarle un mensaje sin control. La ruta va absoluta desde la
                # raíz del config, y un gate exige que resuelva contra `BayesRiskConfig`.
                loc=(*_LOC_SECCION, "input", "macro_source", "variable_cols"),
            )
        try:
            values = tuple(raw)
        except TypeError:
            return data
        if values == ():
            raise ForwardConfigError(
                "macro_source.variable_cols no puede estar vacío.",
                loc=(*_LOC_SECCION, "input", "macro_source", "variable_cols"),
            )
        return data

    @model_validator(mode="after")
    def _check_fuente_y_columnas(self) -> Self:
        """Valida fuente macro, columnas proyectadas y colisión con ``time_col``."""
        if self.time_col in self.variable_cols:
            raise ForwardConfigError(
                "macro_source.variable_cols no puede contener time_col.",
                # El campo que hay que corregir es la lista: `time_col` describe un hecho del
                # archivo macro (cuál es su eje temporal), y lo que sobra es haberlo incluido
                # además entre las variables proyectadas.
                loc=(*_LOC_SECCION, "input", "macro_source", "variable_cols"),
            )
        if self.type == "path" and not self.path:
            raise ForwardConfigError(
                "macro_source.type='path' exige macro_source.path.",
                loc=(*_LOC_SECCION, "input", "macro_source", "path"),
            )
        if self.type == "artifact" and (not self.artifact_domain or not self.artifact_key):
            # Sin `loc` a propósito (D-EXI-5): la condición es una disyunción sobre DOS campos y el
            # mensaje nombra los dos, así que anclar en uno mandaría al usuario al campo que sí
            # estaba escrito cada vez que el ausente fuera el otro. Vacío significa exactamente eso.
            raise ForwardConfigError(
                "macro_source.type='artifact' exige artifact_domain y artifact_key."
            )
        return self


class MacroModelConfig(BayesRiskBaseConfig):
    """Configuración del modelo de proyección macro."""

    kind: MacroModelKind = Field(
        default="arima",
        title="Tipo de modelo macro",
        description=(
            "Cómo se proyecta la macro: ARIMA, SARIMA o ARIMAX, auto_arima, VAR o VECM; con los "
            "escenarios de la institución, sus trayectorias tal cual."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Modelo macro", "ui_order": 1},
    )
    horizon_periods: int = Field(
        default=12,
        ge=1,
        title="Horizonte macro",
        description="Número de períodos a proyectar.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Modelo macro", "ui_order": 2},
    )
    arima_order: tuple[int, int, int] = Field(
        default=(1, 0, 0),
        title="Orden ARIMA",
        description="Orden (p,d,q) usado por ARIMA/SARIMA/ARIMAX.",
        json_schema_extra={"ui_widget": "number_tuple", "ui_group": "Modelo macro", "ui_order": 3},
    )
    seasonal_order: tuple[int, int, int, int] | None = Field(
        default=None,
        title="Orden estacional",
        description="Orden estacional opcional (P,D,Q,s) para SARIMA.",
        json_schema_extra={"ui_widget": "number_tuple", "ui_group": "Modelo macro", "ui_order": 4},
    )
    var_lags: int | None = Field(
        default=None,
        ge=1,
        title="Rezagos del VAR",
        description="Número de rezagos para modelos VAR.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Modelo macro", "ui_order": 5},
    )
    vecm_rank: int | None = Field(
        default=None,
        ge=1,
        title="Rango VECM",
        description="Rango de cointegración para VECM cuando se define explícitamente.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Modelo macro", "ui_order": 6},
    )
    use_pmdarima_auto_order: bool = Field(
        default=False,
        title="Orden automático (pmdarima)",
        description="Activa selección automática de orden para ARIMA/SARIMA/ARIMAX univariado.",
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Modelo macro", "ui_order": 7},
    )
    auto_arima_random: bool = Field(
        default=False,
        title="Búsqueda aleatoria de auto_arima",
        description="Permite la búsqueda aleatoria de auto_arima; exige fijar su semilla.",
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Modelo macro", "ui_order": 8},
    )
    random_state: int | None = Field(
        default=None,
        title="Semilla de auto_arima",
        description="La semilla de la búsqueda aleatoria de auto_arima, cuando está activada.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Modelo macro", "ui_order": 9},
    )
    ljung_box_lags: tuple[int, ...] = Field(
        default=(6, 12),
        title="Rezagos de Ljung-Box",
        description="Rezagos con que se diagnostica la autocorrelación de los residuos.",
        json_schema_extra={"ui_widget": "number_list", "ui_group": "Diagnóstico", "ui_order": 1},
    )
    fail_on_ljung_box: bool = Field(
        default=False,
        title="Fallar por Ljung-Box",
        description="Activado, un diagnóstico de Ljung-Box fallido detiene el ajuste.",
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Diagnóstico", "ui_order": 2},
    )

    @model_validator(mode="after")
    def _check_azar_auto_arima(self) -> Self:
        """Exige semilla explícita si ``auto_arima_random`` queda activo."""
        if self.auto_arima_random and self.random_state is None:
            raise ForwardConfigError(
                "auto_arima_random=True exige random_state explícito.",
                loc=(*_LOC_SECCION, "macro", "random_state"),  # D-EXI-5
            )
        return self

    @model_validator(mode="after")
    def _check_sarima_seasonal_order(self) -> Self:
        """Exige un ``seasonal_order`` estacional real cuando ``kind='sarima'``.

        Sin esta validación, ``kind='sarima'`` con ``seasonal_order=None`` (o un orden
        estacional degenerado como ``(0, 0, 0, s)`` o ``s<2``) corre como ARIMA plano en
        ``statsmodels`` pero se etiqueta ``SARIMA`` en diagnostics/card/log: el audit trail
        miente. Se aborta con error explícito en vez de degradar en silencio.
        """
        if self.kind != "sarima":
            return self
        if self.seasonal_order is None:
            raise ForwardConfigError(
                "kind='sarima' exige seasonal_order (P,D,Q,s) explícito; sin él correría "
                "como ARIMA plano etiquetado SARIMA.",
                loc=(*_LOC_SECCION, "macro", "seasonal_order"),  # D-EXI-5
            )
        seasonal_p, seasonal_d, seasonal_q, seasonal_periods = self.seasonal_order
        if seasonal_periods < 2:
            raise ForwardConfigError(
                "kind='sarima' exige un período estacional s>=2 en seasonal_order; "
                f"recibido s={seasonal_periods}.",
                loc=(*_LOC_SECCION, "macro", "seasonal_order"),
            )
        if (seasonal_p, seasonal_d, seasonal_q) == (0, 0, 0):
            raise ForwardConfigError(
                "kind='sarima' exige al menos un término estacional (P, D o Q) no nulo; "
                "seasonal_order=(0,0,0,s) equivale a ARIMA sin estacionalidad.",
                loc=(*_LOC_SECCION, "macro", "seasonal_order"),
            )
        return self


class SatelliteConfig(BayesRiskBaseConfig):
    """Configuración del modelo satélite de PD y LGD."""

    mode: SatelliteMode = Field(
        default="fit",
        title="Modo del modelo satélite",
        description=(
            "Ajustar coeficientes desde datos, cargar coeficientes fijos auditados o estimar la "
            "sensibilidad sobre una tasa de incumplimiento de referencia larga."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Modelo satélite", "ui_order": 1},
    )
    factor_cols: tuple[str, ...] = Field(
        default=...,
        min_length=1,
        title="Variables del modelo satélite",
        description=(
            "Las variables macro que explican la tasa. Con los escenarios de la institución, "
            "las mismas de las dos tablas."
        ),
        json_schema_extra={
            "ui_widget": "multiselect",
            "ui_group": "Modelo satélite",
            "ui_order": 2,
        },
    )
    segment_col: str | None = Field(
        default=None,
        title="Columna de segmento",
        description="Columna de segmento opcional, para coeficientes por grupo.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Modelo satélite", "ui_order": 3},
    )
    target_components: tuple[TargetComponent, ...] = Field(
        default=("pd",),
        title="Componentes objetivo",
        description="Qué ajusta el modelo satélite: la PD y, si se pide, la LGD.",
        json_schema_extra={
            "ui_widget": "multiselect",
            "ui_group": "Modelo satélite",
            "ui_order": 4,
        },
    )
    reference_scenario: str = Field(
        default="base",
        title="Escenario de referencia",
        description="Escenario base contra el que se calculan deltas macro.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Modelo satélite", "ui_order": 5},
    )
    coefficient_table_path: str | None = Field(
        default=None,
        title="Tabla de coeficientes",
        description="Ruta opcional a coeficientes fijos auditados.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Modelo satélite", "ui_order": 6},
    )
    min_history_periods: int = Field(
        default=12,
        ge=3,
        title="Historia mínima",
        description="Mínimo de períodos de historia para aceptar el ajuste del modelo satélite.",
        json_schema_extra={
            "ui_widget": "number_input",
            "ui_group": "Modelo satélite",
            "ui_order": 7,
        },
    )
    # IFRS9-FIRMABLE D-FIR-2 (§3.2): la única hoja nueva de la capa A. Sin una tasa de referencia
    # larga, la sensibilidad saldría de la historia corta de la cartera: medido, con el signo
    # invertido en Lending Club y sin identificar en Freddie Mac (§1.3 de la enmienda).
    reference_rate_col: str = Field(
        default="default_rate",
        title="Columna de la tasa de referencia",
        description=(
            "Columna de la historia con la tasa de incumplimiento de referencia, como fracción "
            "(un 0,9 % va como 0,009)."
        ),
        json_schema_extra={
            "ui_help": (
                "La tasa de incumplimiento de referencia larga —del sistema por cartera o la "
                "propia, si cruza un ciclo— con que se estima cuánto se mueve el riesgo con la "
                "macro. Va como fracción: un 0,9 % se escribe 0,009. Puede faltar al principio o "
                "al final de la tabla; en medio, no."
            ),
            # IFRS9-FIRMABLE D-FIR-11 (§13): esencial de la pantalla, con su default.
            "ui_essential": True,
            "ui_widget": "text_input",
            "ui_group": "Modelo satélite",
            "ui_order": 8,
        },
    )

    @model_validator(mode="before")
    @classmethod
    def _check_factores_raw(cls, data: Any) -> Any:
        """Valida temprano ``factor_cols`` vacío como error estructural de config."""
        if not isinstance(data, dict) or "factor_cols" not in data:
            return data
        raw = data["factor_cols"]
        if raw is None:
            raise ForwardConfigError(
                "satellite.factor_cols no puede estar vacío.",
                loc=(*_LOC_SECCION, "satellite", "factor_cols"),  # D-EXI-5
            )
        try:
            values = tuple(raw)
        except TypeError:
            return data
        if values == ():
            raise ForwardConfigError(
                "satellite.factor_cols no puede estar vacío.",
                loc=(*_LOC_SECCION, "satellite", "factor_cols"),
            )
        return data


class ScenarioDefinitionConfig(BayesRiskBaseConfig):
    """Definición declarativa de un escenario macro."""

    name: str = Field(
        default=...,
        title="Nombre del escenario",
        description="El nombre del escenario: base, adverso, severo o el de tu tabla.",
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Escenarios", "ui_order": 1},
    )
    weight: float = Field(
        default=...,
        ge=0.0,
        le=1.0,
        title="Peso del escenario",
        description="Peso no negativo del escenario; los pesos deben sumar 1.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Escenarios", "ui_order": 2},
    )
    macro_path_path: str | None = Field(
        default=None,
        title="Trayectoria del escenario",
        description=(
            "El archivo con la trayectoria macro del escenario. La pantalla lo escribe al subir "
            "la tabla de escenarios."
        ),
        json_schema_extra={"ui_widget": "text_input", "ui_group": "Escenarios", "ui_order": 3},
    )
    shocks: dict[str, float] = Field(
        default_factory=dict,
        title="Choques macro",
        description="Choques por variable macro, aditivos o declarados.",
        json_schema_extra={"ui_widget": "key_value", "ui_group": "Escenarios", "ui_order": 4},
    )
    description: str | None = Field(
        default=None,
        title="Descripción",
        description="Una descripción opcional del escenario.",
        json_schema_extra={"ui_widget": "text_area", "ui_group": "Escenarios", "ui_order": 5},
    )

    @field_validator("weight", mode="before")
    @classmethod
    def _check_weight_finito(cls, value: Any) -> Any:
        """Normaliza ``-0.0`` y rechaza pesos no finitos.

        ⚠️ Sin ``loc`` (D-EXI-5) y no por olvido: este campo vive dentro de una FILA de
        ``forward.scenarios.scenarios``, así que su ruta necesita el índice de la fila —y un
        ``field_validator`` no lo conoce: Pydantic le pasa el valor y el nombre del campo, nunca su
        posición en la secuencia del padre—. Una ruta sin índice no enfoca ningún control, y
        adivinar uno mandaría al usuario a otro escenario.
        """
        if _is_non_finite_number(value):
            raise ForwardScenarioError("scenario.weight debe ser un número finito.")
        return 0.0 if value == 0.0 else float(value)

    @field_validator("shocks", mode="after")
    @classmethod
    def _check_shocks_finitos(cls, value: dict[str, float]) -> dict[str, float]:
        """Normaliza ``-0.0`` y rechaza shocks no finitos.

        Sin ``loc`` por la misma razón medida que ``_check_weight_finito``: el campo vive en una
        fila de ``forward.scenarios.scenarios`` cuyo índice el validador no conoce.
        """
        normalized: dict[str, float] = {}
        for name, shock in value.items():
            if not isfinite(shock):
                raise ForwardScenarioError(f"El shock macro '{name}' debe ser finito.")
            normalized[name] = 0.0 if shock == 0.0 else float(shock)
        return normalized


class ScenarioConfig(BayesRiskBaseConfig):
    """Escenarios macro ponderados y bloqueo del escenario medio único."""

    scenarios: tuple[ScenarioDefinitionConfig, ...] = Field(
        default=(
            ScenarioDefinitionConfig(name="base", weight=0.60),
            ScenarioDefinitionConfig(name="adverse", weight=0.30),
            ScenarioDefinitionConfig(name="severe", weight=0.10),
        ),
        title="Escenarios",
        description=(
            "Los escenarios con sus pesos, que suman 1. Con los escenarios de la institución, "
            "los de tu tabla: la pantalla los llena al subirla."
        ),
        json_schema_extra={
            # IFRS9-FIRMABLE D-FIR-11 (§13): esencial de la pantalla —los escenarios con sus
            # pesos—, que la pantalla llena al subir la tabla de escenarios.
            "ui_essential": True,
            "ui_widget": "editable_table",
            "ui_group": "Escenarios",
            "ui_order": 1,
        },
    )
    forbid_mean_scenario: bool = Field(
        default=True,
        title="Prohibir escenario medio",
        description=(
            "Impide usar un escenario promedio en lugar de ponderar escenarios: la pérdida no "
            "es lineal en la macro."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Escenarios", "ui_order": 2},
    )
    require_at_least_three: bool = Field(
        default=True,
        title="Exigir tres escenarios",
        description=(
            "Activado, exige los escenarios base, adverso y severo. No aplica a los escenarios de "
            "la institución, que se nombran libremente."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Escenarios", "ui_order": 3},
    )


class TtcReversionConfig(BayesRiskBaseConfig):
    """Configuración de reversión TTC en escala logit."""

    enabled: bool = Field(
        default=True,
        title="Activar reversión TTC",
        description="Mezcla gradualmente la PD puntual (PIT) hacia el ancla TTC.",
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Reversión TTC", "ui_order": 1},
    )
    reasonable_supportable_periods: int = Field(
        default=12,
        ge=1,
        title="Horizonte razonable y soportable",
        description="Períodos con la PD puntual antes de empezar a revertir hacia la TTC.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Reversión TTC", "ui_order": 2},
    )
    reversion_periods: int = Field(
        default=24,
        ge=1,
        title="Períodos de reversión",
        description="Períodos en que la PD se mezcla gradualmente hacia la TTC.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Reversión TTC", "ui_order": 3},
    )
    method: TtcReversionMethod = Field(
        default="linear_logit",
        title="Método de reversión",
        description="Cómo se revierte hacia la TTC; «none» no revierte.",
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Reversión TTC", "ui_order": 4},
    )
    ttc_anchor: TtcAnchor = Field(
        default="input_term_structure",
        title="Ancla TTC",
        description="Fuente del ancla TTC usada por la reversión.",
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Reversión TTC", "ui_order": 5},
    )


class ForwardInputConfig(BayesRiskBaseConfig):
    """Configuración de insumos macro y term-structures."""

    macro_source: MacroSourceConfig = Field(
        default=...,
        title="Fuente macro",
        description="Histórico macro y variables proyectadas.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Entrada", "ui_order": 1},
    )
    term_structure_sources: tuple[TermStructureSource, ...] = Field(
        default=("survival", "markov"),
        title="Curvas de PD de entrada",
        description="Las etapas cuyas curvas de PD de por vida se ajustan con la macro.",
        json_schema_extra={"ui_widget": "multiselect", "ui_group": "Entrada", "ui_order": 2},
    )
    pd_basis_assumption: PdBasisAssumption | None = Field(
        default=None,
        title="Base de la PD de entrada",
        description=(
            "Si la curva de entrada es a lo largo del ciclo (TTC) o puntual (PIT), cuando la "
            "curva no lo dice."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "PIT/TTC", "ui_order": 1},
    )
    require_pit_consistency: bool = Field(
        default=True,
        title="Exigir consistencia PIT",
        description="Activado, la base PIT o TTC de la curva tiene que quedar declarada.",
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "PIT/TTC", "ui_order": 2},
    )

    @model_validator(mode="after")
    def _check_pd_basis_assumption(self) -> Self:
        """Exige supuesto PIT/TTC si el contrato no trae ``pd_basis`` resuelto."""
        if self.require_pit_consistency and self.pd_basis_assumption is None:
            raise PitConsistencyError(
                "pd_basis_assumption es requerido cuando la term-structure no trae pd_basis.",
                loc=(*_LOC_SECCION, "input", "pd_basis_assumption"),  # D-EXI-5: lo que falta
            )
        return self


class ForwardValidationConfig(BayesRiskBaseConfig):
    """Configuración de tolerancias numéricas forward-looking."""

    probability_tol: float = Field(
        default=1e-10,
        gt=0.0,
        lt=1e-3,
        title="Tolerancia de probabilidad",
        description="Tolerancia para validar probabilidades dentro de [0, 1].",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Validación", "ui_order": 1},
    )
    weight_sum_tol: float = Field(
        default=1e-12,
        gt=0.0,
        lt=1e-3,
        title="Tolerancia de la suma de pesos",
        description="Tolerancia para validar que los pesos de escenarios sumen 1.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Validación", "ui_order": 2},
    )
    monotonic_tol: float = Field(
        default=1e-10,
        gt=0.0,
        lt=1e-3,
        title="Tolerancia monotonicidad",
        description="Tolerancia para validar curvas acumuladas no decrecientes.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Validación", "ui_order": 3},
    )
    fail_on_missing_scenario_paths: bool = Field(
        default=True,
        title="Fallar si faltan trayectorias (deprecado)",
        description=(
            "Ya no tiene efecto: que un escenario adverso o severo sin trayectoria ni choques "
            "detenga la corrida lo decide «Fallar ante falta de dato», el mismo ajuste que "
            "gobierna el resto de los avisos declarados."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Validación", "ui_order": 4},
    )

    @model_validator(mode="after")
    def _avisar_flag_deprecado(self) -> Self:
        """Avisa del retiro de ``fail_on_missing_scenario_paths`` (D-CRP6-5).

        Sólo cuando llega en ``False``: es el único valor cuyo efecto cambia. Antes bastaba para
        apagar la comprobación aunque ``fail_on_falta_dato`` estuviera en ``True``; ahora no la
        apaga, y quien dependiera de eso tiene que enterarse. En ``True`` el comportamiento es
        idéntico al anterior y avisar sería ruido.
        """
        if not self.fail_on_missing_scenario_paths:
            warnings.warn(
                "fail_on_missing_scenario_paths está DEPRECADO en ForwardValidationConfig y ya no "
                "tiene efecto: la decisión de detener la corrida ante un escenario adverse/severe "
                "sin trayectoria ni shocks la toma fail_on_falta_dato (CRP-6). Retire el campo; "
                "para no detenerse use fail_on_falta_dato=False.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self


class ForwardConfig(BayesRiskBaseConfig):
    """Proyecta la PD con variables macroeconómicas y convierte entre PD PIT y PD TTC."""

    # Tres esenciales (IFRS9-FIRMABLE D-FIR-11, §13; capa C): la tabla de historia, la columna de
    # la tasa de referencia —con su default— y los escenarios con sus pesos. El resto, en
    # «Avanzado»: la vía con modelo macro (ARIMA, VAR) y las tolerancias.
    model_config = ConfigDict(json_schema_extra=declara_esenciales)

    schema_version: str = Field(
        default="1.0.0",
        title="Versión del sub-schema forward",
        description="Versión local del schema de forward para migraciones futuras.",
        json_schema_extra={"ui_widget": "hidden", "ui_group": "General", "ui_order": 0},
    )
    type: Literal["standard"] = Field(
        default="standard",
        title="Tipo de sección forward",
        description="Variante de la sección forward; hoy solo existe la estándar.",
        json_schema_extra={"ui_widget": "hidden", "ui_group": "General", "ui_order": 1},
    )
    input: ForwardInputConfig = Field(
        default=...,
        title="Entrada",
        description="La historia macro y las curvas de PD de entrada.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Entrada", "ui_order": 1},
    )
    satellite: SatelliteConfig = Field(
        default=...,
        title="Modelo satélite",
        description="Cómo se traduce la macro al riesgo: la sensibilidad de la PD (y la LGD).",
        json_schema_extra={"ui_widget": "section", "ui_group": "Modelo satélite", "ui_order": 1},
    )
    macro: MacroModelConfig = Field(
        default_factory=MacroModelConfig,
        title="Modelo macro",
        description="Cómo se proyecta la macro y sus diagnósticos.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Modelo macro", "ui_order": 1},
    )
    scenarios: ScenarioConfig = Field(
        default_factory=ScenarioConfig,
        title="Escenarios",
        description="Escenarios macro, sus pesos y el bloqueo del escenario medio único.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Escenarios", "ui_order": 1},
    )
    ttc_reversion: TtcReversionConfig = Field(
        default_factory=TtcReversionConfig,
        title="Reversión TTC",
        description="Horizonte razonable, reversión y ancla TTC.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Reversión TTC", "ui_order": 1},
    )
    validation: ForwardValidationConfig = Field(
        default_factory=ForwardValidationConfig,
        title="Validación",
        description="Tolerancias numéricas y política ante escenarios incompletos.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Validación", "ui_order": 1},
    )
    fail_on_falta_dato: bool = Field(
        default=True,
        title="Fallar ante falta de dato",
        description=(
            "Activado, un escenario adverso o severo sin trayectoria macro ni choques propios "
            "detiene la corrida en vez de quedar registrado como aviso declarado y seguir."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Gobernanza", "ui_order": 1},
    )

    @model_validator(mode="after")
    def _check_invariantes(self) -> Self:
        """Valida invariantes cruzados de SDD-20 §5."""
        macro_cols = set(self.input.macro_source.variable_cols)
        if self.macro.kind in _REQUIRES_MULTIVARIATE and len(macro_cols) < 2:
            raise ForwardConfigError(
                "kind='var'/'vecm' exige al menos dos variable_cols.",
                # D-EXI-5: «X exige Y» ancla en Y, que es lo que falta.
                loc=(*_LOC_SECCION, "input", "macro_source", "variable_cols"),
            )
        if self.macro.kind == "arimax" and not self.input.macro_source.exogenous_cols:
            raise ForwardConfigError(
                "kind='arimax' exige macro_source.exogenous_cols no vacío.",
                loc=(*_LOC_SECCION, "input", "macro_source", "exogenous_cols"),
            )
        if self.macro.use_pmdarima_auto_order and (
            self.macro.kind not in _AUTO_ORDER_KINDS or len(macro_cols) != 1
        ):
            raise ForwardConfigError(
                "use_pmdarima_auto_order=True solo aplica a ARIMA/SARIMA/ARIMAX univariado.",
                # El interruptor ES el campo a corregir aunque la condición mire tres: apagarlo
                # resuelve el conflicto SIEMPRE, mientras que cambiar `kind` sólo lo resuelve si
                # además hay una única variable macro, y viceversa.
                loc=(*_LOC_SECCION, "macro", "use_pmdarima_auto_order"),
            )
        if (
            self.ttc_reversion.enabled
            and self.ttc_reversion.method != "none"
            and self.macro.horizon_periods < self.ttc_reversion.reasonable_supportable_periods
        ):
            # Sin `loc` a propósito (D-EXI-5): es una desigualdad entre dos horizontes que el
            # usuario elige por separado, en subsecciones distintas, y ninguno falta ni es inválido
            # por sí solo. No hay un campo que corregir sino una relación entre dos que corregir.
            raise ForwardConfigError(
                "macro.horizon_periods debe ser >= "
                "ttc_reversion.reasonable_supportable_periods para reversión TTC."
            )
        via_de_escenarios = _check_via_de_escenarios(self)
        _check_scenarios(
            self.scenarios,
            self.validation.weight_sum_tol,
            nombres_libres=via_de_escenarios,
        )
        _check_missing_stress_scenarios(self)
        missing_factors = sorted(set(self.satellite.factor_cols) - macro_cols)
        if missing_factors:
            raise SatelliteModelError(
                f"satellite.factor_cols debe ser subconjunto de variables macro proyectadas: "
                f"{missing_factors}.",
                # Los valores rechazados VIVEN en `factor_cols`: `variable_cols` es lo que el
                # modelo macro proyecta de verdad, o sea la fuente contra la que se coteja.
                loc=(*_LOC_SECCION, "satellite", "factor_cols"),
            )
        return self


def _check_via_de_escenarios(cfg: ForwardConfig) -> bool:
    """La vía de los escenarios de la institución (IFRS9-FIRMABLE D-FIR-2 y D-FIR-4, §3.4).

    ``satellite.mode = "reference_rate"`` y ``macro.kind = "scenario_paths"`` van juntos: la
    sensibilidad sale de la tasa de referencia y la previsión son las trayectorias de la
    institución, sin modelo macro. En esta vía cada escenario trae su trayectoria y ningún choque,
    hay al menos dos y todos pesan más que cero; los nombres son libres (no se exigen base, adverse
    y severe). Devuelve si la corrida va por esta vía.
    """
    por_tasa = cfg.satellite.mode == "reference_rate"
    por_trayectorias = cfg.macro.kind == "scenario_paths"
    if por_tasa != por_trayectorias:
        mensaje = (
            "satellite.mode='reference_rate' y macro.kind='scenario_paths' van juntos: la "
            "sensibilidad se estima sobre la tasa de referencia y los escenarios son las "
            "trayectorias de la institución, sin modelo macro."
        )
        # D-EXI-5: se ancla en la hoja que quedó sola.
        if por_tasa:
            raise ForwardConfigError(mensaje, loc=(*_LOC_SECCION, "macro", "kind"))
        raise ForwardConfigError(mensaje, loc=(*_LOC_SECCION, "satellite", "mode"))
    if not por_tasa:
        return False
    if not cfg.satellite.reference_rate_col.strip():
        raise ForwardConfigError(
            "satellite.reference_rate_col no puede estar vacío.",
            loc=(*_LOC_SECCION, "satellite", "reference_rate_col"),
        )
    source = cfg.input.macro_source
    if cfg.satellite.reference_rate_col in (*source.variable_cols, source.time_col):
        raise ForwardConfigError(
            "satellite.reference_rate_col es la tasa que se explica: no puede ser la fecha ni "
            "una de las variables macro.",
            loc=(*_LOC_SECCION, "satellite", "reference_rate_col"),
        )
    escenarios = cfg.scenarios.scenarios
    if len(escenarios) < 2:
        raise ForwardScenarioError(
            "Con los escenarios de la institución hacen falta al menos dos: uno solo no es un "
            "rango (IFRS 9 5.5.17(a)).",
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )
    sin_trayectoria = [e.name for e in escenarios if not e.macro_path_path]
    if sin_trayectoria:
        raise ForwardScenarioError(
            "Con macro.kind='scenario_paths' cada escenario trae su trayectoria "
            f"(macro_path_path): faltan {sin_trayectoria}.",
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )
    con_choques = [e.name for e in escenarios if e.shocks]
    if con_choques:
        raise ForwardScenarioError(
            "Con macro.kind='scenario_paths' las trayectorias se toman tal cual: los choques "
            f"constantes son de la vía con modelo macro ({con_choques}).",
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )
    sin_peso = [e.name for e in escenarios if not e.weight > 0.0]
    if sin_peso:
        raise ForwardScenarioError(
            f"Los escenarios {sin_peso} pesan cero: un escenario sin peso no es parte del rango.",
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )
    return True


def _check_scenarios(
    scenarios: ScenarioConfig, weight_sum_tol: float, *, nombres_libres: bool = False
) -> None:
    """Valida unicidad, escenarios requeridos, nombres reservados y suma de pesos.

    Con ``nombres_libres`` —la vía de los escenarios de la institución— no se exigen base,
    adverse y severe: los nombra la institución (§3.4).
    """
    names = [scenario.name for scenario in scenarios.scenarios]
    if len(set(names)) != len(names):
        raise ForwardScenarioError(
            "scenario.scenarios no puede contener nombres duplicados.",
            # D-EXI-5: la lista es el control que el usuario edita, y ahí viven los nombres
            # repetidos. Se ancla en la lista y no en una fila porque el conflicto es de al menos
            # dos filas a la vez, así que un índice sería elegir arbitrariamente una de ellas.
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )

    name_set = set(names)
    if scenarios.require_at_least_three and not nombres_libres:
        missing = sorted(_REQUIRED_SCENARIOS - name_set)
        if missing:
            raise ForwardScenarioError(
                f"scenario.scenarios debe incluir base, adverse y severe: faltan {missing}.",
                loc=(*_LOC_SECCION, "scenarios", "scenarios"),
            )
    if scenarios.forbid_mean_scenario:
        reserved = sorted(name_set & _RESERVED_SCENARIO_NAMES)
        if reserved:
            raise ForwardScenarioError(
                f"forbid_mean_scenario=True veta escenarios medios reservados: {reserved}.",
                # Se ancla en la lista y no en el interruptor: `forbid_mean_scenario` es la guarda
                # metodológica —un escenario medio no es la media de los escenarios— y apagarla es
                # la salida que existe para no tomar; lo que hay que corregir son los nombres.
                loc=(*_LOC_SECCION, "scenarios", "scenarios"),
            )
    total_weight = sum(scenario.weight for scenario in scenarios.scenarios)
    if not isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=weight_sum_tol):
        # Sin `loc` a propósito (D-EXI-5): que una suma no dé 1 no es defecto de ningún peso en
        # particular, y la tolerancia con que se juzga vive además en otra subsección
        # (`validation.weight_sum_tol`). Es el caso canónico de invariante entre campos.
        raise ForwardScenarioError(
            f"Los pesos de escenarios deben sumar 1; suma observada={total_weight!r}."
        )


def _check_missing_stress_scenarios(cfg: ForwardConfig) -> None:
    """Valida DATO-INSTITUCIONAL-FWD-1 para escenarios adverse/severe sin path ni shocks."""
    # D-CRP6-5: la decisión es de `fail_on_falta_dato` y de nadie más. El AND con
    # `fail_on_missing_scenario_paths` era apagado silencioso: el usuario dejaba el flag principal
    # en True y la carencia no lo detenía, sin que nada se lo dijera.
    if not cfg.fail_on_falta_dato:
        return
    missing = [
        scenario.name
        for scenario in cfg.scenarios.scenarios
        if scenario.name in _STRESS_SCENARIOS
        and not scenario.macro_path_path
        and not scenario.shocks
    ]
    if missing:
        raise ForwardScenarioError(
            "DATO-INSTITUCIONAL-FWD-1: adverse/severe deben declarar macro_path_path o shocks; "
            f"faltan {missing}.",
            # D-EXI-5: lo que falta son datos de las filas de esta lista, que es el control donde
            # se escriben. No baja a `macro_path_path` ni a `shocks` porque son alternativas —basta
            # cualquiera de las dos— y porque pueden faltar en varios escenarios a la vez.
            loc=(*_LOC_SECCION, "scenarios", "scenarios"),
        )
