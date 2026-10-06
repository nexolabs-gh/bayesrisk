"""Paso orquestable de la capa ``provisioning_ifrs9`` (SDD-16 §4/§7/§9; CT-1).

``IfrsProvisioningStep`` implementa el :class:`~bayesrisk.core.steps.Step` nativo del dominio
``provisioning_ifrs9``: lee el ``data.frame`` económico y la term-structure lifetime del proveedor
configurado (survival/markov/forward), activa la dependencia condicional de PD calibrada sólo cuando
``pd.base_pd_source='calibration'``, delega el cálculo a :class:`IfrsProvisioningEngine` y publica
staging, detalle, term-structure de ECL, resumen, resultado y card bajo el dominio
``provisioning_ifrs9``.

**``requires`` dinámicos (CT-1, patrón SDD-20 §81).** ``from_config`` construye la lista de
dependencias: siempre ``('data', 'frame')``; ``('calibration', 'calibrated_pd_frame')`` si
``base_pd_source='calibration'``; y ``(<term_structure_source>, 'term_structure')`` con la fuente en
``{survival, markov, forward}``. Un artefacto requerido ausente levanta
:class:`~bayesrisk.core.exceptions.ArtifactNotFoundError` antes de calcular.

El módulo evita importar ``pandas``, el motor y sus dependencias numéricas en import time.
``bayesrisk.provisioning.ifrs9`` lo importa para ejecutar ``@register("standard",
domain="provisioning_ifrs9")`` sin contaminar el núcleo liviano; las dependencias tabulares se
cargan dentro de ``execute``.

Nomenclatura IFRS 9 (regla dura D-CONV-1): ``pd``/``lgd``/``ead``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast

from bayesrisk.core.audit import AuditEvent
from bayesrisk.core.exceptions import ArtifactNotFoundError, MissingDependencyError
from bayesrisk.core.mixins import AuditableMixin
from bayesrisk.core.registry import register
from bayesrisk.core.steps import ArtifactKey
from bayesrisk.core.time_units import known_time_units
from bayesrisk.provisioning.ifrs9.config import IfrsProvisioningConfig
from bayesrisk.provisioning.ifrs9.engine import (
    _TS_TIME_UNIT_COLUMN,
    _WARNING_TIME_UNIT_ASSUMED,
)
from bayesrisk.provisioning.ifrs9.exceptions import IfrsConfigError, IfrsInputError

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.core.study import Study
    from bayesrisk.provisioning.ifrs9.results import IfrsProvisionResult

    DataFrame: TypeAlias = pd.DataFrame
else:
    DataFrame: TypeAlias = Any
    IfrsProvisionResult: TypeAlias = Any
    Study: TypeAlias = Any

__all__ = ["IFRS9_PROVISIONING_ARTIFACTS", "IfrsProvisioningStep"]

IFRS9_PROVISIONING_ARTIFACTS: Final[tuple[str, ...]] = (
    "staging",
    "detail",
    "ecl_term_structure",
    "summary",
    "result",
    "card",
)
_CALIBRATION_SOURCE: Final = "calibration"
_IFRS9_EXTRA_MESSAGE: Final = "IfrsProvisioningStep requiere pandas; instale bayesrisk[scoring]."


@register("standard", domain="provisioning_ifrs9")
class IfrsProvisioningStep(AuditableMixin):
    """Orquesta provisiones IFRS 9/ECL y publica ``domain='provisioning_ifrs9'``."""

    name: str = "provisioning_ifrs9"
    requires: tuple[ArtifactKey, ...] = (("data", "frame"),)
    provides: tuple[ArtifactKey, ...] = tuple(
        ("provisioning_ifrs9", key) for key in IFRS9_PROVISIONING_ARTIFACTS
    )

    def __init__(self, config: IfrsProvisioningConfig) -> None:
        """Construye el paso desde la sección ``IfrsProvisioningConfig`` y arma ``requires``."""
        self.config = config
        self.requires = _requires_for(config)

    @classmethod
    def from_config(cls, cfg: IfrsProvisioningConfig) -> IfrsProvisioningStep:
        """Construye ``IfrsProvisioningStep`` desde ``BayesRiskConfig.provisioning_ifrs9``."""
        return cls(cfg)

    def emit(self, event: AuditEvent) -> None:
        """Permite pasar el step como ``AuditSink`` al motor IFRS 9."""
        self._audit.emit(event)

    def execute(self, study: Study, rng: np.random.Generator) -> IfrsProvisionResult:
        """Ejecuta provisiones IFRS 9 deterministas sin consumir ``rng`` y publica artefactos."""
        del rng  # El motor IFRS 9 v1 es determinista (SDD-16 §9): se descarta el azar.
        pd = _import_pandas()

        cfg = _ifrs_config_from_study(study, fallback=self.config)
        frame = _as_dataframe(
            _require_artifact(study, "data", "frame"),
            pd,
            "data.frame",
        ).copy(deep=True)
        as_of_date = _as_of_date_from_frame(frame, cfg)
        term_structure = _as_dataframe(
            _require_artifact(study, cfg.pd.term_structure_source, "term_structure"),
            pd,
            f"{cfg.pd.term_structure_source}.term_structure",
        ).copy(deep=True)
        calibrated_pd = _calibrated_pd_if_required(study, config=cfg, pd=pd)

        from bayesrisk.provisioning.ifrs9.engine import IfrsProvisioningEngine

        engine = IfrsProvisioningEngine.from_config(cfg)
        result = engine.calculate(
            frame,
            term_structure=term_structure,
            calibrated_pd=None if calibrated_pd is None else calibrated_pd.copy(deep=True),
            as_of_date=as_of_date,
            audit=self,
        )
        self._log_ifrs_decisions(config=cfg, result=result, term_structure=term_structure)
        self._publish_artifacts(study, result)
        return result

    def _publish_artifacts(self, study: Study, result: IfrsProvisionResult) -> None:
        """Publica los seis artefactos estables del dominio ``provisioning_ifrs9``."""
        study.artifacts.set("provisioning_ifrs9", "staging", result.staging.copy(deep=True))
        study.artifacts.set("provisioning_ifrs9", "detail", result.detail.copy(deep=True))
        study.artifacts.set(
            "provisioning_ifrs9",
            "ecl_term_structure",
            result.ecl_term_structure.copy(deep=True),
        )
        study.artifacts.set("provisioning_ifrs9", "summary", result.summary.copy(deep=True))
        study.artifacts.set("provisioning_ifrs9", "result", result.model_copy(deep=True))
        study.artifacts.set("provisioning_ifrs9", "card", result.card.model_copy(deep=True))

    def _log_ifrs_decisions(
        self,
        *,
        config: IfrsProvisioningConfig,
        result: IfrsProvisionResult,
        term_structure: DataFrame,
    ) -> None:
        """Registra las decisiones auditables exigidas por SDD-16 §9.

        Recibe la ``term_structure`` de ENTRADA —no basta ``result``— porque la unidad temporal
        declarada es una propiedad de la curva recibida y no sobrevive al cálculo: la salida ya
        publica los plazos convertidos (D-HOR-0).
        """
        from bayesrisk.provisioning.ifrs9.engine import effective_horizon_12m

        card = result.card
        self.log_decision(
            regla="ifrs9_term_structure_source",
            umbral=config.pd.term_structure_source,
            valor={"base_pd_source": config.pd.base_pd_source, "n_rows": card.n_rows},
            accion="leer_term_structure_lifetime",
        )
        self.log_decision(
            regla="ifrs9_pit",
            umbral=config.pd.pit_mode,
            valor={
                "rho": config.pd.rho,
                "rho_col": config.pd.rho_col,
                "systemic_factor_col": config.pd.systemic_factor_col,
            },
            accion="resolver_pd_pit",
        )
        self.log_decision(
            regla="ifrs9_pd_horizon",
            umbral={
                "horizon_12m_periods": config.pd.horizon_12m_periods,
                "max_lifetime_periods": config.pd.max_lifetime_periods,
            },
            valor={
                "falta_dato": card.falta_dato,
                # D-HOR-0: el soporte OBSERVADO de la curva, que es contra lo que se contrasta el
                # horizonte. Sin él, el audit trail registraba los dos campos de config y no había
                # forma de reconstruir por qué el aviso salió (o por qué no salió).
                "soporte_periodos": _period_bounds(term_structure),
                # FLUJO-GUIADO-IFRS9 §3.12: en blanco, el horizonte se infirió de la unidad de la
                # curva; la clave sólo viaja entonces, así que una corrida con el número declarado
                # registra exactamente lo de antes.
                **(
                    {
                        "horizon_12m_inferido": effective_horizon_12m(
                            None, _curva_de_las_activas(term_structure, result)
                        ),
                    }
                    if config.pd.horizon_12m_periods is None
                    else {}
                ),
            },
            accion="derivar_horizontes_pd",
        )
        self.log_decision(
            regla="ifrs9_lgd",
            umbral=config.lgd.method,
            valor={
                "lgd_floor": config.lgd.lgd_floor,
                "lgd_cap": config.lgd.lgd_cap,
                # La LGD forward de la term-structure no se consume en v1 (FALTA-DATO-IFRS-6).
                "lgd_forward_presente": "FALTA-DATO-IFRS-6" in card.falta_dato,
            },
            accion="estimar_lgd",
        )
        self.log_decision(
            regla="ifrs9_ead",
            umbral=config.ead.method,
            valor={
                "exposure_profile_col": config.ead.exposure_profile_col,
                # CASO-REAL-IFRS9 D-CRE-5: las filas con EAD 0 se separaron y sólo alimentaron la
                # curva. La clave sólo viaja entonces: una corrida sin ellas registra lo de antes.
                **(
                    {"n_rows_without_exposure": card.n_rows_without_exposure}
                    if card.n_rows_without_exposure
                    else {}
                ),
            },
            accion="estimar_ead",
        )
        self.log_decision(
            regla="ifrs9_staging",
            umbral={
                "sicr_pd_ratio_threshold": config.staging.sicr_pd_ratio_threshold,
                "dpd_sicr_backstop": config.staging.dpd_sicr_backstop,
                "dpd_default_backstop": config.staging.dpd_default_backstop,
            },
            valor={
                "n_stage1": card.n_stage1,
                "n_stage2": card.n_stage2,
                "n_stage3": card.n_stage3,
                "sicr_triggers": _trigger_counts(result.staging),
            },
            accion="asignar_staging",
        )
        self.log_decision(
            regla="ifrs9_scenarios",
            umbral=config.scenarios.source,
            valor={
                "scenarios": card.scenarios,
                "scenario_weights": card.scenario_weights,
                "forbid_mean_scenario": config.scenarios.forbid_mean_scenario,
            },
            accion="ponderar_escenarios",
        )
        self.log_decision(
            regla="ifrs9_ecl",
            umbral={
                "discount_convention": config.ecl.discount_convention,
                "stage3_direct": config.ecl.stage3_direct,
            },
            valor={
                "total_ead": card.total_ead,
                "total_ecl_reported": card.total_ecl_reported,
            },
            accion="calcular_ecl",
        )
        # D-HOR-0: `ifrs9_ecl` registra la CONVENCIÓN configurada; esta decisión registra lo
        # OBSERVADO en la curva que llegó, que es lo que decide el exponente del descuento. Sin
        # ella, un auditor no puede distinguir una curva declarada en años de una que se presumió.
        self.log_decision(
            regla="ifrs9_discount_time_unit",
            umbral={"unidades_convertibles": known_time_units()},
            valor={
                "unidades_observadas": _observed_time_units(term_structure),
                "unidad_presumida_anios": _WARNING_TIME_UNIT_ASSUMED in card.falta_dato,
            },
            accion="convertir_time_value_a_anios",
        )


def _requires_for(config: IfrsProvisioningConfig) -> tuple[ArtifactKey, ...]:
    """Construye las claves ``requires`` dinámicas del step según la config (CT-1, SDD-16 §4).

    La fuente de term-structure (``pd.term_structure_source``) es un ``Literal`` validado por config
    (``{survival, markov, forward}``), así que aquí sólo se ensambla la lista de dependencias.
    """
    requires: list[ArtifactKey] = [("data", "frame")]
    if config.pd.base_pd_source == _CALIBRATION_SOURCE:
        requires.append(("calibration", "calibrated_pd_frame"))
    requires.append((config.pd.term_structure_source, "term_structure"))
    return tuple(requires)


def _require_artifact(study: Study, domain: str, key: str) -> object:
    """Exige un artefacto presente en el ``ArtifactStore`` o levanta ``ArtifactNotFoundError``."""
    if not study.artifacts.has(domain, key):
        raise ArtifactNotFoundError(
            f"El paso 'provisioning_ifrs9' requiere el artefacto ('{domain}', '{key}'), "
            "ausente del ArtifactStore."
        )
    return study.artifacts.get(domain, key)


def _calibrated_pd_if_required(
    study: Study, *, config: IfrsProvisioningConfig, pd: Any
) -> DataFrame | None:
    """Lee la PD calibrada sólo cuando ``base_pd_source='calibration'`` la exige (CT-1)."""
    if config.pd.base_pd_source != _CALIBRATION_SOURCE:
        return None
    return _as_calibrated_dataframe(
        _require_artifact(study, "calibration", "calibrated_pd_frame"),
        pd,
        "calibration.calibrated_pd_frame",
    ).copy(deep=True)


def _ifrs_config_from_study(
    study: Study, *, fallback: IfrsProvisioningConfig
) -> IfrsProvisioningConfig:
    """Lee ``BayesRiskConfig.provisioning_ifrs9``; el config del paso es el respaldo standalone."""
    raw_config = getattr(study.config, "provisioning_ifrs9", None)
    if raw_config is None:
        return fallback
    if isinstance(raw_config, IfrsProvisioningConfig):
        return raw_config
    return IfrsProvisioningConfig.model_validate(raw_config)


def _as_of_date_from_frame(frame: DataFrame, config: IfrsProvisioningConfig) -> str:
    """Resuelve una fecha de cálculo única desde ``config.as_of_date_col`` (SDD-16 §4)."""
    column = config.as_of_date_col
    if column not in frame.columns:
        raise IfrsConfigError(
            "IfrsProvisioningStep requiere una fecha de cálculo única: "
            f"falta la columna as_of_date_col='{column}'."
        )
    values = tuple(
        dict.fromkeys(
            item
            for item in (str(raw).strip() for raw in cast(Any, frame[column].dropna().tolist()))
            if item
        )
    )
    if not values:
        raise IfrsConfigError(
            "IfrsProvisioningStep requiere una fecha de cálculo no nula en "
            f"as_of_date_col='{column}'."
        )
    if len(values) > 1:
        raise IfrsConfigError(
            "IfrsProvisioningStep requiere una sola fecha de cálculo por corrida: "
            f"as_of_date_col='{column}', valores={values!r}."
        )
    return values[0]


def _import_pandas() -> Any:
    """Importa ``pandas`` localmente para preservar el import liviano del paquete."""
    try:
        return importlib.import_module("pandas")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_IFRS9_EXTRA_MESSAGE) from exc


def _as_dataframe(value: object, pd: Any, artifact: str) -> DataFrame:
    """Valida un artefacto tabular de entrada antes de leerlo."""
    if isinstance(value, pd.DataFrame):
        return cast("DataFrame", value)
    raise IfrsInputError(
        f"El artefacto '{artifact}' debe ser un pandas.DataFrame; "
        f"tipo observado={type(value).__name__}."
    )


def _as_calibrated_dataframe(value: object, pd: Any, artifact: str) -> DataFrame:
    """Valida el artefacto de PD calibrada con error de configuración del step."""
    if isinstance(value, pd.DataFrame):
        return cast("DataFrame", value)
    raise IfrsConfigError(
        "base_pd_source='calibration' exige un artefacto de PD calibrada pandas.DataFrame: "
        f"artefacto='{artifact}', tipo observado={type(value).__name__}."
    )


def _curva_de_las_activas(term_structure: DataFrame, result: IfrsProvisionResult) -> DataFrame:
    """La curva de las operaciones que provisionó el motor (CASO-REAL-IFRS9 D-CRE-5).

    El motor infiere los 12 meses de la curva SIN las filas de exposición 0; el registro los
    infiere de la misma, o una fila cerrada con otra unidad haría morir el paso después de calcular.
    """
    activas = {str(rid) for rid in cast(Any, result.detail["row_id"]).tolist()}
    ids = [str(rid) for rid in cast(Any, term_structure["row_id"]).tolist()]
    return term_structure.loc[[rid in activas for rid in ids]]


def _period_bounds(term_structure: DataFrame) -> dict[str, int]:
    """Devuelve el primer y el último período de la curva recibida, sin truncar.

    Es el soporte **bruto**: lo que el motor contrasta contra ``horizon_12m_periods`` y contra
    ``max_lifetime_periods`` para distinguir un truncado deliberado de un horizonte mal declarado.
    """
    period = term_structure["period"]
    return {"min": int(period.min()), "max": int(period.max())}


def _observed_time_units(term_structure: DataFrame) -> tuple[str, ...]:
    """Lista las unidades temporales que la term-structure recibida declara, en orden estable.

    Tupla y no escalar porque ``forward`` concatena N fuentes: dos curvas con unidades distintas
    conviven en el mismo frame y el audit trail debe mostrarlas todas. Vacía significa que ninguna
    fila la declaró.
    """
    if _TS_TIME_UNIT_COLUMN not in term_structure.columns:
        return ()
    return tuple(
        sorted(
            {
                str(value)
                for value in term_structure[_TS_TIME_UNIT_COLUMN].tolist()
                if value is not None and str(value) != "nan"
            }
        )
    )


def _trigger_counts(staging: DataFrame) -> dict[str, int]:
    """Cuenta los gatillos SICR disparados desde ``staging.sicr_triggers`` (auditoría §9)."""
    counts: dict[str, int] = {}
    for codes in cast(Any, staging["sicr_triggers"]).tolist():
        for code in codes:
            name = str(code)
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))
