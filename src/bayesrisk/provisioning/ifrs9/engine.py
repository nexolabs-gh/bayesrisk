"""Orquestador económico IFRS 9 / ECL: encadena PD PIT, LGD, EAD, staging y ECL (SDD-16 §7).

:class:`IfrsProvisioningEngine` ejecuta la **secuencia canónica** del SDD-16 §7 sobre una operación
o cartera: transforma la PD a base point-in-time (PIT), deriva los horizontes 12m/lifetime, estima
LGD y EAD, asigna el Stage IFRS 9 por SICR y evalúa la ECL marginal descontada a la EIR, ponderando
outputs por escenario. Reutiliza los motores puros de bloques previos —``vasicek_pit`` /
``marginal_to_horizon`` (``pd_pit``), :class:`~bayesrisk.provisioning.lgd.LgdEngine`,
:class:`~bayesrisk.provisioning.ifrs9.ead.EadEngine`,
:class:`~bayesrisk.provisioning.ifrs9.staging.StagingEngine` y
:class:`~bayesrisk.provisioning.ifrs9.ecl.EclEngine`— y ensambla el
:class:`~bayesrisk.provisioning.ifrs9.results.IfrsProvisionResult` (staging, detalle, term-structure
de ECL, resumen y card) que consume el step ``provisioning_ifrs9``.

Determinismo (SDD-16 §9): el motor v1 no tiene componentes estocásticos. No muta los insumos (copias
defensivas del ``frame``, la term-structure y la PD calibrada), preserva el orden del ``frame`` en
``staging``/``detail`` y normaliza ``-0.0`` a ``0.0`` (delegado a los DTO/DataFrame de ``results``).

``pandas``/``numpy`` (y ``scipy`` para Vasicek) se importan de forma perezosa dentro de los métodos:
ni ``import bayesrisk.core`` ni ``import bayesrisk.provisioning.ifrs9`` deben arrastrar esas
dependencias en top-level.

Nomenclatura IFRS 9 (regla dura D-CONV-1): ``pd``/``lgd``/``ead``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping
from importlib import metadata
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.core.markers import governable_warnings, is_declared_warning
from bayesrisk.core.time_units import year_fraction
from bayesrisk.provisioning.ifrs9.config import IfrsProvisioningConfig
from bayesrisk.provisioning.ifrs9.contract import (
    ContractReading,
    _meses_por_periodo,
    check_contract_config,
    read_contract_terms,
    read_curve_by_contract,
)
from bayesrisk.provisioning.ifrs9.cycle import (
    CycleInputs,
    CycleShifter,
    check_scenario_coverage,
    cycle_anchor,
    first_future_month,
    period_windows,
    require_cycle,
    shift_term_structure,
)
from bayesrisk.provisioning.ifrs9.ead import EadEngine
from bayesrisk.provisioning.ifrs9.ecl import EclEngine, validate_scenario_weights
from bayesrisk.provisioning.ifrs9.exceptions import (
    IfrsConfigError,
    IfrsFaltaDatoError,
    IfrsInputError,
    IfrsTermStructureError,
)
from bayesrisk.provisioning.ifrs9.pd_pit import marginal_to_horizon, vasicek_pit
from bayesrisk.provisioning.ifrs9.results import (
    IfrsEclRecord,
    IfrsProvisionCard,
    IfrsProvisionResult,
    IfrsStageRecord,
)
from bayesrisk.provisioning.ifrs9.staging import StagingEngine
from bayesrisk.provisioning.lgd import LgdEngine
from bayesrisk.provisioning.segmentation import scheme_by_id

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.core.audit import AuditSink

    NDArrayFloat: TypeAlias = np.ndarray[Any, np.dtype[np.float64]]
    DataFrame: TypeAlias = pd.DataFrame
    Series: TypeAlias = pd.Series
else:
    AuditSink: TypeAlias = Any
    NDArrayFloat: TypeAlias = Any
    DataFrame: TypeAlias = Any
    Series: TypeAlias = Any

__all__ = ["IfrsProvisioningEngine", "effective_horizon_12m"]

# Etiqueta canónica del escenario único cuando la term-structure base (survival/markov) no puebla la
# columna ``scenario`` (queda ``None``); forward la puebla con nombres reales.
_SINGLE_SCENARIO_LABEL: str = "base"
# Columna de nombre fijo con la PD 12m anclada por SDD-10 cuando ``base_pd_source='calibration'``.
_CALIBRATED_PD_COLUMN: str = "pd_calibrated"
# Columnas del contrato tidy de term-structure que el motor exige antes de calcular (SDD-16 §6).
_TS_REQUIRED_COLUMNS: tuple[str, ...] = ("row_id", "period", "time_value", "pd_marginal")
# Columnas opcionales del contrato tidy que refuerzan las invariantes cuando están presentes.
_TS_SURVIVAL_COLUMN: str = "survival"
_TS_CUMULATIVE_COLUMN: str = "pd_cumulative"
_TS_SCENARIO_COLUMN: str = "scenario"
_TS_PD_BASIS_COLUMN: str = "pd_basis"
_TS_SCENARIO_WEIGHT_COLUMN: str = "scenario_weight"
# Etiqueta del escenario agregado en el resumen (la ECL reportada ya pondera todos los escenarios).
_SUMMARY_SCENARIO_LABEL: str = "all"
# Tolerancias de las invariantes tidy de la term-structure (SDD-16 §6).
_TS_INVARIANT_TOL: float = 1e-9
# Nombres de escenario vetados por el guard anti escenario medio (espejo de forward/SDD-20;
# cubre las tres fuentes porque se valida antes del branch por ``scenarios.source``).
_RESERVED_SCENARIO_NAMES: frozenset[str] = frozenset({"mean", "average", "weighted_mean_input"})
# La LGD condicionada que publica forward en la term-structure NO se consume en v1 (SDD-20
# FALTA-DATO-FWD-6, precedencia pendiente de SDD): el motor estima la LGD desde el ``frame``
# (``IfrsLgdConfig``) y declara el descarte con este aviso en vez de callarlo.
_TS_LGD_COLUMN: str = "lgd"
_WARNING_LGD_FORWARD_IGNORED: str = "FALTA-DATO-IFRS-6"

# D-HOR-0: la term-structure declara en qué unidad está su ``time_value`` y el motor lo convierte a
# años antes de usarlo como exponente del descuento. Cuando no la declara —columna ausente, vacía, o
# un literal no convertible como ``"period"``, el default de fábrica de survival/markov— se presume
# años y se deja constancia. La marca es `DATO-INSTITUCIONAL` porque la periodicidad de la curva
# sólo la sabe la institución: el motor se niega a inventarla y hace explícita la presunción.
#
# El código es `IFRS-7` y NO `IFRS-1`: el espacio de numeración `IFRS-N` está asignado en el
# catálogo de SDD-16 §6 y es compartido por las dos marcas —`IFRS-1` es el factor sistémico `Z`—. Un
# `git grep` sobre `src/` lo daría por libre, porque IFRS-1/2/3/5 son requisitos documentados que
# nunca se emiten en runtime.
_TS_TIME_UNIT_COLUMN: str = "time_unit"
_TS_YEARS_COLUMN: str = "time_value_years"
_WARNING_TIME_UNIT_ASSUMED: str = "DATO-INSTITUCIONAL-IFRS-7"

# D-HOR-0: `horizon_12m_periods` declara cuántos períodos de la curva cubren 12 meses, y hasta ahora
# nadie lo contrastaba contra la curva recibida. Con la unidad declarada, el período del horizonte
# cae en `time_value_years` y se puede VERIFICAR que dure un año: con el default de fábrica (12)
# sobre una curva anual, el «ECL a 12 meses» cubría doce años y sobrestimaba el Stage 1 unas 7,5
# veces, en silencio. El otro caso es el horizonte por debajo del primer período, donde Stage 1
# provisiona CERO. Es brecha del motor —el parámetro lo escribe el usuario, pero verificar que sea
# coherente con lo recibido es nuestro—, así que `FALTA-DATO` (mismo precedente que FWD-8). Ver
# `IFRS-2` en el catálogo de SDD-16 §6: ese código queda como requisito documentado y no se emite.
_WARNING_HORIZON_MISMATCH: str = "FALTA-DATO-IFRS-8"
# Tolerancia del chequeo «el período del horizonte dura ~1 año». Ancha a propósito: cubre 360 vs 365
# días, curvas que empiezan a contar en 0 y redondeos de calendario, y sigue cazando el error que
# importa —que el horizonte cubra 3 o 12 años en vez de uno—. Un gatillo estrecho dispararía sobre
# curvas legítimas, y un aviso que dispara sobre el caso correcto se aprende a ignorar.
_HORIZONTE_ANIO_TOL: float = 0.25

# D-CRP6-2: avisos **estructurales** de esta capa, los que el motor emite en toda corrida por una
# capacidad diferida propia. `fail_on_falta_dato` no los gobierna: se registran siempre en la card y
# nunca detienen. `FALTA-DATO-IFRS-4` declara que el perfil EAD(t) longitudinal está diferido a CT-3
# (`ead.py`), y se emite incluso cuando la institución entrega la EAD real —medido—, así que
# abortar por él dejaría el motor inservible con su propio valor por defecto. Que no detenga no lo
# absuelve: su arreglo es CT-3, y CRP-7 ya lo tiene asignado.
_STRUCTURAL_WARNINGS: frozenset[str] = frozenset({"FALTA-DATO-IFRS-4"})
# CASO-REAL-IFRS9 D-CRE-3: con la cuota del contrato, la operación que sigue la tabla de pagos deja
# de tener la EAD constante y pierde este aviso; las demás lo conservan (§3.3).
_WARNING_CONSTANT_EAD: str = "FALTA-DATO-IFRS-4"

# Rótulo hermano de ``ecl_by_scenario`` en ``metric_sections``. Esa cifra y ``total_ecl_reported``
# difieren por construcción, pero salían pegadas en el anexo de auditoría sin nada que lo explicara
# —y una diferencia de ~2x sin rótulo se lee como descuadre contable. El texto viaja en el propio
# artefacto, no en la plantilla del informe, para que acompañe a la cifra dondequiera que se lea
# ``results`` (anexo, payload de la UI, consumidor externo).
# CASO-REAL-IFRS9 D-CRE-2 (§3.2): el tramo de la curva que lee cada período posterior al corte.
_CURVE_SEGMENT_COLUMNS: tuple[str, ...] = ("curve_start", "curve_end")
# IFRS9-FIRMABLE D-FIR-1 (§3.1): el desplazamiento en logit de cada tramo, sólo con escenarios.
_CYCLE_SHIFT_COLUMN: str = "cycle_shift"

_ECL_BY_SCENARIO_BASIS: str = (
    "Diagnóstico auditable de la term-structure, no un desglose de total_ecl_reported: "
    "suma la ECL marginal descontada de cada escenario por separado, sin aplicar scenario_weights "
    "y sobre el horizonte completo de la curva, sin truncar Stage 1 a 12 meses. "
    "total_ecl_reported sí pondera por escenario y aplica ese corte por stage, de modo que ambas "
    "cifras no reconcilian entre sí: no deben sumarse ni compararse."
)

# Columnas canónicas de los artefactos (deben coincidir exactamente con ``results.py``, que las
# revalida al construir el ``IfrsProvisionResult``; una divergencia rompe los tests ruidosamente).
_STAGING_COLUMNS: tuple[str, ...] = (
    "row_id",
    "portfolio",
    "stage",
    "days_past_due",
    "pd_life_current",
    "pd_life_origination",
    "sicr_triggers",
    "low_credit_risk_exempt",
    "warning_codes",
)
_DETAIL_COLUMNS: tuple[str, ...] = (
    "row_id",
    "portfolio",
    "stage",
    "ead",
    "lgd",
    "eir",
    "pd_12m",
    "pd_life",
    "ecl_12m",
    "ecl_lifetime",
    "ecl_reported",
    "ecl_reported_unrounded",
    "rounding_difference",
    "scenario_weights",
    "pd_basis",
    "warning_codes",
)
# CASO-REAL-IFRS9 D-CRE-2 (§3.2): sólo con las fechas del contrato (espejo de ``results.py``).
_DETAIL_CONTRACT_COLUMNS: tuple[str, ...] = ("age_periods", "life_periods")
_SUMMARY_COLUMNS: tuple[str, ...] = (
    "portfolio",
    "stage",
    "scenario",
    "n_rows",
    "total_ead",
    "total_ecl_reported",
    "coverage_ratio",
    "warning_codes",
)

_NUMPY_MESSAGE: str = "IfrsProvisioningEngine requiere numpy; instale bayesrisk[scoring]."
_PANDAS_MESSAGE: str = "IfrsProvisioningEngine requiere pandas; instale bayesrisk[scoring]."


class IfrsProvisioningEngine:
    """Motor económico IFRS 9 que orquesta la secuencia canónica de la ECL (SDD-16 §7)."""

    config_cls: ClassVar[type[IfrsProvisioningConfig]] = IfrsProvisioningConfig

    def __init__(self, config: IfrsProvisioningConfig) -> None:
        """Inicializa el motor con la sección ``IfrsProvisioningConfig`` ya validada."""
        self._config = config

    @classmethod
    def from_config(cls, cfg: IfrsProvisioningConfig) -> Self:
        """Construye el motor desde ``IfrsProvisioningConfig`` (molde hermano ``from_config``)."""
        return cls(cfg)

    def calculate(
        self,
        frame: DataFrame,
        *,
        term_structure: DataFrame,
        calibrated_pd: DataFrame | None = None,
        as_of_date: str,
        audit: AuditSink | None = None,
        events_by_period: Mapping[int, int] | None = None,
        cycle: CycleInputs | None = None,
    ) -> IfrsProvisionResult:
        """Calcula la ECL IFRS 9 por operación y ensambla el :class:`IfrsProvisionResult`.

        Parameters
        ----------
        frame
            DataFrame económico (exposición/drawn/límite, dpd, EIR, rating, LGD/recovery, flags). No
            se muta (copia defensiva).
        term_structure
            Term-structure tidy lifetime PD del proveedor configurado (survival/markov/forward),
            con al menos ``row_id``/``period``/``time_value``/``pd_marginal``. No se muta.
        calibrated_pd
            PD 12m anclada por SDD-10 (columna ``pd_calibrated``); obligatoria sólo cuando
            ``pd.base_pd_source='calibration'``.
        as_of_date
            Fecha de cálculo/cierre contable de la provisión (texto no vacío).
        audit
            Sink de auditoría opcional (el step orquestador registra las decisiones de §9).
        events_by_period
            Los incumplimientos de la historia de la curva por período (``person_period`` de la
            card de ``discrete_hazard``). Sólo se leen con las fechas del contrato
            (CASO-REAL-IFRS9 D-CRE-2): la cola de la curva se extiende desde el último período
            con incumplimientos.
        cycle
            El modelo del ciclo que publica ``forward`` y la historia de la curva (IFRS9-FIRMABLE
            D-FIR-1…3). Sólo con ``pd.pit_mode='cycle'``: la tabla de escenario × tramo queda en
            ``cycle_by_period_`` tras calcular.

        Returns
        -------
        IfrsProvisionResult
            Contenedor con ``staging``/``detail``/``ecl_term_structure``/``summary``, los registros
            por operación y la card CT-2.

        Raises
        ------
        IfrsTermStructureError
            Si la term-structure incumple el contrato tidy o sus invariantes.
        IfrsConfigError
            Si el modo PIT, la fuente de PD base o la fuente de escenarios exige insumos ausentes.
        IfrsInputError
            Si faltan columnas raíz del ``frame`` o los identificadores no son únicos/alineables.
        MissingDependencyError
            Si falta ``numpy`` o ``pandas``.
        """
        # El step orquestador registra las decisiones §9; el motor es puro y determinista.
        del audit
        numpy = _import_numpy()
        pandas = _import_pandas()
        config = self._config
        _validate_as_of_date(as_of_date)
        check_contract_config(config, events_by_period)
        ciclo = config.pd.pit_mode == "cycle"
        self.cycle_by_period_: DataFrame | None = None
        if ciclo:
            _check_cycle_config(config)
            cycle = require_cycle(cycle)

        frame = _as_dataframe(frame, pandas, "data.frame").copy(deep=True)
        ts = _as_dataframe(term_structure, pandas, "term_structure").copy(deep=True)
        calibrated = (
            None
            if calibrated_pd is None
            else _as_dataframe(calibrated_pd, pandas, "calibrated_pd").copy(deep=True)
        )

        row_ids = _frame_row_ids(frame, config)
        # CASO-REAL-IFRS9 D-CRE-5 (§3.5): una fila sin exposición no es una operación de la
        # cartera. La historia de la curva vive en el mismo archivo —los préstamos cerrados entran
        # con EAD 0— y contarla como cartera daba «60.000 operaciones, Stage 3: 10.191» sobre
        # 9.593 préstamos vivos sin ninguno en Stage 3 (Lending Club). La EAD se calcula sobre
        # TODAS las filas —es lo que decide cuáles son operaciones— y las de EAD 0 se separan aquí,
        # antes de validar o leer cualquier otro insumo, de buscar su PD y de estagear: un dato
        # inválido en un préstamo cerrado ya no aborta la provisión. La ECL no cambia (aportaban
        # cero). El umbral es el cero exacto, sin perilla.
        ead_arr, row_warnings = self._estimate_ead(frame, numpy)
        activas = ead_arr > 0.0
        n_sin_exposicion = int(activas.size - int(activas.sum()))
        sin_exposicion = {rid for rid, activa in zip(row_ids, activas, strict=True) if not activa}
        if not bool(activas.any()):
            raise IfrsInputError(
                "Ninguna fila tiene exposición al corte (EAD > 0): no hay cartera que "
                "provisionar. Las filas con exposición 0 sólo aportan historia a la curva."
            )
        if n_sin_exposicion:
            posiciones = numpy.flatnonzero(activas)
            frame = frame.iloc[posiciones].copy(deep=True)
            row_ids = [row_ids[int(i)] for i in posiciones]
            row_warnings = [row_warnings[int(i)] for i in posiciones]
            ead_arr = ead_arr[posiciones]
        portfolios = _frame_column_texts(frame, config.portfolio_col, "portfolio_col")
        eir_arr = _frame_float_column(frame, config.ecl.eir_col, "eir", numpy)
        # CASO-REAL-IFRS9 D-CRE-2 y D-CRE-3: las fechas y la cuota del contrato, leídas y validadas
        # sólo en las operaciones con exposición, antes de tocar la curva.
        terms = (
            read_contract_terms(frame, config, as_of_date=as_of_date, row_ids=row_ids)
            if config.lee_fechas_del_contrato()
            else None
        )

        if sin_exposicion and "row_id" in ts.columns:
            # D-CRE-5: la curva de una fila sin exposición tampoco se valida ni decide el horizonte
            # (pasada 1 de Codex): se retira antes que nada, y la cobertura y la malla de
            # componentes van contra las activas. La curva de una fila que el archivo no trae no
            # se retira: sigue siendo un error de cobertura.
            ts_ids = [str(value) for value in ts["row_id"].to_numpy()]
            ts = ts.loc[[rid not in sin_exposicion for rid in ts_ids]].copy(deep=True)
        _validate_term_structure(ts, numpy)
        # FLUJO-GUIADO-IFRS9 §3.12 (OK de Cami, 2026-10-05): un horizonte de 12 meses en blanco se
        # infiere de la unidad de la curva, antes de que nada lo lea; declarado, no se toca. Los
        # tres que lo usan —la PD a 12 meses, el chequeo D-ECL-0 y la ECL— reciben este número.
        horizonte_12m = effective_horizon_12m(config.pd.horizon_12m_periods, ts)
        # Con las fechas, la vida de cada operación la corta el contrato y `max_lifetime_periods`
        # la acota desde el corte (§3.2-3): la curva publicada no se trunca, que la cola la lee.
        ts = _prepare_term_structure(ts, config, numpy, truncar_vida=terms is None)
        _check_row_coverage(row_ids, [str(value) for value in ts["row_id"].to_numpy()])
        # Lo que se declara de la curva RECIBIDA —la LGD forward descartada, la unidad presumida y
        # el horizonte de 12 meses que no dura un año (D-ECL-0)— se mide sobre la curva publicada,
        # antes de leerla por contrato (§3.2-8).
        lgd_forward = _ts_lgd_present(ts)
        sin_unidad = _ts_row_ids_sin_unidad(ts)
        horizonte_inconmensurable = _horizonte_inconmensurable(ts, horizonte_12m, numpy)

        shifter: CycleShifter | None = None
        ts_ttc: DataFrame | None = None
        lectura_ttc: ContractReading | None = None
        if ciclo:
            # IFRS9-FIRMABLE D-FIR-1…4: el ancla y el desplazamiento por tramo de calendario, con
            # los escenarios y sus pesos del modelo de `forward`; antes de leer la curva.
            assert cycle is not None
            primer_mes = first_future_month(as_of_date)
            check_scenario_coverage(cycle.model, first_month=primer_mes)
            meses = _meses_por_periodo(ts)
            ancla = cycle_anchor(
                cycle.model, cycle.history, months_per_period=meses, first_month=primer_mes
            )
            shifter = CycleShifter(
                cycle.model, ancla, months_per_period=meses, first_month=primer_mes
            )
            ts_ttc = ts
        else:
            weights = self._resolve_weights(ts, numpy)
        lectura: ContractReading | None = None
        if terms is not None:
            lectura = read_curve_by_contract(
                ts,
                terms=terms,
                row_ids=row_ids,
                ead_by_rid=dict(zip(row_ids, (float(v) for v in ead_arr), strict=True)),
                events_by_period=cast("Mapping[int, int]", events_by_period),
                max_lifetime=config.pd.max_lifetime_periods,
                deltas=None if shifter is None else shifter.deltas,
                weights=None if shifter is None else shifter.weights,
            )
            if shifter is not None:
                # La misma lectura sin desplazamiento: la ECL a lo largo del ciclo (§3.1).
                lectura_ttc = read_curve_by_contract(
                    ts,
                    terms=terms,
                    row_ids=row_ids,
                    ead_by_rid=dict(zip(row_ids, (float(v) for v in ead_arr), strict=True)),
                    events_by_period=cast("Mapping[int, int]", events_by_period),
                    max_lifetime=config.pd.max_lifetime_periods,
                )
                ts_ttc = lectura_ttc.term_structure
            ts = lectura.term_structure
            # D-CRE-3: una operación que sigue la tabla de pagos ya no tiene la EAD constante.
            row_warnings = [
                tuple(c for c in codes if c != _WARNING_CONSTANT_EAD)
                if rid in lectura.amortizing
                else codes
                for rid, codes in zip(row_ids, row_warnings, strict=True)
            ]
        elif shifter is not None:
            ts = shift_term_structure(ts, shifter)
        if shifter is not None:
            # Los pesos son los del modelo (`scenario_weight` en la curva), con las mismas
            # validaciones que los de `forward`: positivos, que suman 1, sin escenario medio.
            weights = self._resolve_weights(ts, numpy)
        pit_marginal = self._resolve_pit_marginal(ts, config, numpy)
        ts = ts.assign(pd_marginal=pit_marginal)

        pd_12m_by_rid, pd_life_by_rid = _weighted_horizons(ts, horizonte_12m, weights, pandas)
        if config.pd.base_pd_source == "calibration":
            pd_12m_by_rid = _calibrated_pd_12m(calibrated, row_ids, numpy)

        pd_life_arr = numpy.array([pd_life_by_rid[rid] for rid in row_ids], dtype=numpy.float64)
        pd_pit_arr = numpy.array([pd_12m_by_rid[rid] for rid in row_ids], dtype=numpy.float64)

        lgd_arr = self._estimate_lgd(frame, eir_arr, numpy, pandas)
        if lgd_forward:
            row_warnings = [(*codes, _WARNING_LGD_FORWARD_IGNORED) for codes in row_warnings]
        # Por `row_id` y no en bloque, a diferencia de IFRS-6: con `forward` conviven filas que
        # declaran la unidad y filas que no. La marca sale sea cual sea `discount_convention`,
        # porque describe una propiedad del INPUT y no de una rama de cálculo aguas abajo:
        # condicionarla a la convención haría que la misma curva sea «declarada» o «no declarada»
        # según un ajuste posterior, que es el agujero que D-HOR-0 cierra.
        if sin_unidad:
            row_warnings = [
                (*codes, _WARNING_TIME_UNIT_ASSUMED) if rid in sin_unidad else codes
                for rid, codes in zip(row_ids, row_warnings, strict=True)
            ]
        # En bloque, a diferencia de IFRS-7: el horizonte es un escalar de config. Se mide curva a
        # curva (D-ECL-0), pero basta una desajustada para que la «ECL a 12 meses» de la corrida
        # no lo sea, y la marca la gobierna `fail_on_falta_dato` para la corrida entera.
        if horizonte_inconmensurable:
            row_warnings = [(*codes, _WARNING_HORIZON_MISMATCH) for codes in row_warnings]
        stage_arr, triggers, exempt = self._assign_staging(frame, pd_life_arr, pd_pit_arr, pandas)

        lgd_by_rid = dict(zip(row_ids, (float(value) for value in lgd_arr), strict=True))
        ead_by_rid = dict(zip(row_ids, (float(value) for value in ead_arr), strict=True))
        eir_by_rid = dict(zip(row_ids, (float(value) for value in eir_arr), strict=True))

        components = _components_frame(
            ts,
            row_ids,
            lgd_by_rid,
            ead_by_rid,
            pandas,
            ead_por_periodo=None if lectura is None else lectura.ead,
        )
        ecl_ts, ecl_detail = EclEngine.from_config(config.ecl).compute(
            components,
            eir=pandas.Series(eir_arr, index=row_ids),
            stages=pandas.Series(stage_arr, index=row_ids),
            weights=weights,
            horizon_12m=horizonte_12m,
        )
        if lectura is not None or shifter is not None:
            ecl_ts = _con_tramo_de_la_curva(ecl_ts, components)
        seccion_ciclo: dict[str, Any] | None = None
        if shifter is not None:
            assert ts_ttc is not None
            seccion_ciclo = _ecl_del_ciclo(
                config=config,
                shifter=shifter,
                components=components,
                ts_ttc=ts_ttc,
                lectura_ttc=lectura_ttc,
                row_ids=row_ids,
                lgd_by_rid=lgd_by_rid,
                ead_by_rid=ead_by_rid,
                eir_arr=eir_arr,
                stage_arr=stage_arr,
                horizonte_12m=horizonte_12m,
                pandas=pandas,
            )
            self.cycle_by_period_ = shifter.by_period(
                _ventanas_por_periodo(ts_ttc, lectura is not None, shifter, pandas)
            )

        pd_basis = "ttc" if config.pd.pit_mode == "ttc_only" else "pit"
        origination = _origination_pd_life(frame, config, numpy)
        context = _OperationContext(
            row_ids=row_ids,
            portfolios=portfolios,
            days_past_due=_frame_int_column(frame, config.staging.days_past_due_col, numpy),
            pd_life=pd_life_arr,
            pd_pit=pd_pit_arr,
            origination_pd_life=origination,
            lgd=lgd_by_rid,
            ead=ead_by_rid,
            eir=eir_by_rid,
            triggers=triggers,
            exempt=exempt,
            warnings=dict(zip(row_ids, row_warnings, strict=True)),
            weights=weights,
            pd_basis=pd_basis,
        )
        return self._assemble_result(
            context=context,
            ecl_detail=ecl_detail,
            ecl_term_structure=ecl_ts,
            as_of_date=as_of_date,
            n_rows_without_exposure=n_sin_exposicion,
            lectura=lectura,
            pandas=pandas,
            seccion_ciclo=seccion_ciclo,
        )

    # --- Etapas económicas (reutilizan los motores puros de bloques previos) -------------------

    def _resolve_weights(self, ts: DataFrame, numpy: Any) -> dict[str, float]:
        """Resuelve los pesos de escenario según ``scenarios.source`` (SDD-16 §5/§7).

        CRP-5: la validación de los pesos —positivos, que cubren los escenarios y suman 1— se
        aplica **aquí**, antes de que :func:`_weighted_horizons` los use para ponderar la PD 12m y
        lifetime. Antes vivía sólo en ``EclEngine``, es decir después de haber calculado con el
        número malo: el veredicto era correcto y el momento no. ``EclEngine`` la conserva como
        defensa en profundidad, porque también se le puede invocar directamente.
        """
        scenarios_present = _ordered_unique(
            str(value) for value in ts[_TS_SCENARIO_COLUMN].tolist()
        )
        if self._config.scenarios.forbid_mean_scenario:
            reservados = sorted(
                name for name in scenarios_present if name.lower() in _RESERVED_SCENARIO_NAMES
            )
            if reservados:
                raise IfrsConfigError(
                    "forbid_mean_scenario=True veta escenarios medios reservados en la "
                    f"term-structure: {reservados} (se ponderan outputs por escenario, "
                    "nunca inputs macro promediados)."
                )
        source = self._config.scenarios.source
        if source == "single":
            if len(scenarios_present) != 1:
                raise IfrsConfigError(
                    "scenarios.source='single' exige exactamente un escenario en la "
                    f"term-structure; presentes={scenarios_present}."
                )
            resolved = {scenarios_present[0]: 1.0}
        elif source == "config":
            resolved = {
                str(key): float(value) for key, value in self._config.scenarios.weights.items()
            }
            if set(resolved) != set(scenarios_present):
                raise IfrsConfigError(
                    "scenarios.source='config' exige pesos que cubran exactamente los escenarios "
                    f"presentes (pesos={sorted(resolved)}, escenarios={scenarios_present})."
                )
        else:
            resolved = _forward_weights(ts, scenarios_present, numpy)
        return validate_scenario_weights(resolved, set(scenarios_present))

    def _resolve_pit_marginal(
        self, ts: DataFrame, config: IfrsProvisioningConfig, numpy: Any
    ) -> NDArrayFloat:
        """Resuelve la PD marginal PIT según ``pit_mode`` (consume_pit/apply_vasicek/ttc_only)."""
        marginal = numpy.asarray(ts["pd_marginal"].to_numpy(), dtype=numpy.float64)
        pit_mode = config.pd.pit_mode
        if pit_mode in ("ttc_only", "cycle"):
            # `cycle`: la curva ya viene desplazada por escenario (D-FIR-1).
            return cast("NDArrayFloat", marginal)
        if pit_mode == "consume_pit":
            _require_pit_basis(ts)
            return cast("NDArrayFloat", marginal)
        return _apply_vasicek(ts, config, marginal, numpy)

    def _estimate_lgd(
        self, frame: DataFrame, eir_arr: NDArrayFloat, numpy: Any, pandas: Any
    ) -> NDArrayFloat:
        """Estima la LGD por operación con :class:`LgdEngine`, en orden del ``frame``."""
        eir_series = pandas.Series(eir_arr, index=frame.index)
        lgd_frame = LgdEngine.from_config(self._config.lgd).estimate(frame, eir=eir_series)
        return cast("NDArrayFloat", numpy.asarray(lgd_frame["lgd"].to_numpy(), dtype=numpy.float64))

    def _estimate_ead(
        self, frame: DataFrame, numpy: Any
    ) -> tuple[NDArrayFloat, list[tuple[str, ...]]]:
        """Estima el nivel de EAD por operación (constante por período) con :class:`EadEngine`."""
        ead_frame = EadEngine.from_config(self._config.ead).estimate(frame, periods=[1])
        level = numpy.asarray(ead_frame["ead"].to_numpy(), dtype=numpy.float64)
        warnings = [
            tuple(str(code) for code in codes) for codes in ead_frame["warning_codes"].tolist()
        ]
        return cast("NDArrayFloat", level), warnings

    def _assign_staging(
        self,
        frame: DataFrame,
        pd_life_arr: NDArrayFloat,
        pd_pit_arr: NDArrayFloat,
        pandas: Any,
    ) -> tuple[Any, list[tuple[str, ...]], list[bool]]:
        """Asigna el Stage IFRS 9 por operación con :class:`StagingEngine` (SICR/backstops)."""
        staging = StagingEngine.from_config(self._config.staging).assign(
            frame,
            pd_life=pandas.Series(pd_life_arr, index=frame.index),
            pd_pit=pandas.Series(pd_pit_arr, index=frame.index),
        )
        stages = staging["stage"].to_numpy()
        triggers = [
            tuple(str(code) for code in codes) for codes in staging["sicr_triggers"].tolist()
        ]
        exempt = [bool(flag) for flag in staging["low_credit_risk_exempt"].tolist()]
        return stages, triggers, exempt

    # --- Ensamblado de artefactos (SDD-16 §4/§6) ------------------------------------------------

    def _assemble_result(
        self,
        *,
        context: _OperationContext,
        ecl_detail: DataFrame,
        ecl_term_structure: DataFrame,
        as_of_date: str,
        n_rows_without_exposure: int,
        lectura: ContractReading | None,
        pandas: Any,
        seccion_ciclo: dict[str, Any] | None = None,
    ) -> IfrsProvisionResult:
        """Construye ``staging``/``detail``/``summary``, los registros y la card (SDD-16 §4/§6)."""
        ecl_by_rid = {
            str(rid): (
                float(e12),
                float(elife),
                float(erep),
                float(eunrounded),
                float(delta),
                int(stage),
            )
            for rid, e12, elife, erep, eunrounded, delta, stage in zip(
                ecl_detail["row_id"].tolist(),
                ecl_detail["ecl_12m"].tolist(),
                ecl_detail["ecl_lifetime"].tolist(),
                ecl_detail["ecl_reported"].tolist(),
                ecl_detail["ecl_reported_unrounded"].tolist(),
                ecl_detail["rounding_difference"].tolist(),
                ecl_detail["stage"].tolist(),
                strict=True,
            )
        }
        staging_rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []
        stage_records: list[IfrsStageRecord] = []
        ecl_records: list[IfrsEclRecord] = []
        for index, rid in enumerate(context.row_ids):
            (
                ecl_12m,
                ecl_lifetime,
                ecl_reported,
                ecl_reported_unrounded,
                rounding_difference,
                stage,
            ) = ecl_by_rid[rid]
            portfolio = context.portfolios[index]
            dpd = int(context.days_past_due[index])
            pd_life = float(context.pd_life[index])
            pd_12m = float(context.pd_pit[index])
            origination = (
                None
                if context.origination_pd_life is None
                else float(context.origination_pd_life[index])
            )
            warnings = context.warnings[rid]
            staging_rows.append(
                {
                    "row_id": rid,
                    "portfolio": portfolio,
                    "stage": stage,
                    "days_past_due": dpd,
                    "pd_life_current": pd_life,
                    "pd_life_origination": origination,
                    "sicr_triggers": context.triggers[index],
                    "low_credit_risk_exempt": context.exempt[index],
                    "warning_codes": warnings,
                }
            )
            detail_rows.append(
                {
                    "row_id": rid,
                    "portfolio": portfolio,
                    "stage": stage,
                    "ead": context.ead[rid],
                    "lgd": context.lgd[rid],
                    "eir": context.eir[rid],
                    "pd_12m": pd_12m,
                    "pd_life": pd_life,
                    "ecl_12m": ecl_12m,
                    "ecl_lifetime": ecl_lifetime,
                    "ecl_reported": ecl_reported,
                    "ecl_reported_unrounded": ecl_reported_unrounded,
                    "rounding_difference": rounding_difference,
                    "scenario_weights": dict(context.weights),
                    "pd_basis": context.pd_basis,
                    "warning_codes": warnings,
                    **(
                        {}
                        if lectura is None
                        else {
                            "age_periods": lectura.age_periods[rid],
                            "life_periods": lectura.life_periods[rid],
                        }
                    ),
                }
            )
            stage_records.append(
                IfrsStageRecord(
                    row_id=rid,
                    stage=cast("Any", stage),
                    days_past_due=dpd,
                    pd_life_current=pd_life,
                    pd_life_origination=origination,
                    sicr_triggers=context.triggers[index],
                    low_credit_risk_exempt=context.exempt[index],
                    warnings=warnings,
                )
            )
            ecl_records.append(
                IfrsEclRecord(
                    row_id=rid,
                    stage=cast("Any", stage),
                    ead=context.ead[rid],
                    lgd=context.lgd[rid],
                    eir=context.eir[rid],
                    ecl_12m=ecl_12m,
                    ecl_lifetime=ecl_lifetime,
                    ecl_reported=ecl_reported,
                    ecl_reported_unrounded=ecl_reported_unrounded,
                    rounding_difference=rounding_difference,
                    scenario_weights=dict(context.weights),
                    pd_basis=cast("Any", context.pd_basis),
                    warnings=warnings,
                )
            )
        staging = pandas.DataFrame(staging_rows, columns=list(_STAGING_COLUMNS))
        detail = pandas.DataFrame(
            detail_rows,
            columns=[*_DETAIL_COLUMNS, *(() if lectura is None else _DETAIL_CONTRACT_COLUMNS)],
        )
        summary = _summary_frame(detail_rows, pandas)
        card = self._build_card(
            detail_rows=detail_rows,
            weights=context.weights,
            pd_basis=context.pd_basis,
            as_of_date=as_of_date,
            ecl_term_structure=ecl_term_structure,
            n_rows_without_exposure=n_rows_without_exposure,
            lectura=lectura,
            seccion_ciclo=seccion_ciclo,
        )
        return IfrsProvisionResult(
            staging=staging,
            detail=detail,
            ecl_term_structure=ecl_term_structure,
            summary=summary,
            stage_records=tuple(stage_records),
            ecl_records=tuple(ecl_records),
            card=card,
        )

    def _build_card(
        self,
        *,
        detail_rows: list[dict[str, Any]],
        weights: dict[str, float],
        pd_basis: str,
        as_of_date: str,
        ecl_term_structure: DataFrame,
        n_rows_without_exposure: int,
        lectura: ContractReading | None,
        seccion_ciclo: dict[str, Any] | None = None,
    ) -> IfrsProvisionCard:
        """Construye la ``IfrsProvisionCard`` CT-2 con totales, conteos y secciones métricas."""
        stages = [int(row["stage"]) for row in detail_rows]
        total_ead = sum(float(row["ead"]) for row in detail_rows)
        total_ecl = sum(float(row["ecl_reported"]) for row in detail_rows)
        falta_dato = _ordered_unique(
            code
            for row in detail_rows
            for code in row["warning_codes"]
            if is_declared_warning(str(code))
        )
        # D-CRP6-1: aquí es donde la capa conoce **todas** sus marcas, así que es donde el flag
        # decide. Sólo las gobernables detienen (D-CRP6-2); las estructurales siguen viajando en
        # `falta_dato` para que el audit trail las conserve.
        gobernables = governable_warnings(falta_dato, structural=_STRUCTURAL_WARNINGS)
        if self._config.fail_on_falta_dato and gobernables:
            detalle = ", ".join(gobernables)
            raise IfrsFaltaDatoError(
                f"Corrida abortada por avisos declarados: {detalle}. Use fail_on_falta_dato=False "
                "para registrarlos en el resultado y continuar."
            )
        metric_sections = {
            "staging_migration": {
                "stage_1": stages.count(1),
                "stage_2": stages.count(2),
                "stage_3": stages.count(3),
            },
            "ecl_by_scenario": _ecl_by_scenario(ecl_term_structure),
            "ecl_by_scenario_basis": _ECL_BY_SCENARIO_BASIS,
            "term_structure_summary": {
                "n_rows": len(ecl_term_structure.index),
                "n_scenarios": len(weights),
            },
            "rounding": {
                "policy": self._config.ecl.rounding,
                "total_difference": sum(float(row["rounding_difference"]) for row in detail_rows),
            },
            # IFRS9-FIRMABLE D-FIR-1 (§3.1): sólo con escenarios, para que una corrida sin ellos
            # publique exactamente la card de antes.
            **({} if seccion_ciclo is None else seccion_ciclo),
        }
        return IfrsProvisionCard(
            as_of_date=as_of_date,
            # Ver D-SEG-3: el esquema de carteras viaja en el resultado para que el orquestador
            # pueda contrastarlo contra el de la otra fuente sin adivinar.
            segmentation=scheme_by_id(
                self._config.portfolio_scheme, column=self._config.portfolio_col
            ),
            term_structure_source=self._config.pd.term_structure_source,
            pit_mode=self._config.pd.pit_mode,
            n_rows=len(detail_rows),
            n_rows_without_exposure=n_rows_without_exposure,
            n_stage1=stages.count(1),
            n_stage2=stages.count(2),
            n_stage3=stages.count(3),
            **({} if lectura is None else _campos_del_contrato(lectura)),
            total_ead=total_ead,
            total_ecl_reported=total_ecl,
            scenarios=tuple(weights),
            scenario_weights=dict(weights),
            dependency_versions=_dependency_versions(self._config),
            falta_dato=tuple(falta_dato),
            metric_sections=metric_sections,
        )


class _OperationContext:
    """Contexto por operación en orden del ``frame`` para ensamblar los artefactos (interno)."""

    def __init__(
        self,
        *,
        row_ids: list[str],
        portfolios: list[str],
        days_past_due: NDArrayFloat,
        pd_life: NDArrayFloat,
        pd_pit: NDArrayFloat,
        origination_pd_life: NDArrayFloat | None,
        lgd: dict[str, float],
        ead: dict[str, float],
        eir: dict[str, float],
        triggers: list[tuple[str, ...]],
        exempt: list[bool],
        warnings: dict[str, tuple[str, ...]],
        weights: dict[str, float],
        pd_basis: str,
    ) -> None:
        """Almacena las estructuras por operación ya alineadas al orden del ``frame``."""
        self.row_ids = row_ids
        self.portfolios = portfolios
        self.days_past_due = days_past_due
        self.pd_life = pd_life
        self.pd_pit = pd_pit
        self.origination_pd_life = origination_pd_life
        self.lgd = lgd
        self.ead = ead
        self.eir = eir
        self.triggers = triggers
        self.exempt = exempt
        self.warnings = warnings
        self.weights = weights
        self.pd_basis = pd_basis


# --- Helpers de contrato / extracción de columnas -------------------------------------------------


def _validate_as_of_date(as_of_date: str) -> None:
    """Exige una fecha de cálculo de texto no vacío (SDD-16 §4)."""
    if not isinstance(as_of_date, str) or not as_of_date.strip():
        raise IfrsInputError("as_of_date debe ser un texto no vacío.")


def _frame_row_ids(frame: DataFrame, config: IfrsProvisioningConfig) -> list[str]:
    """Deriva los identificadores de operación (``row_id_col`` o índice) y exige unicidad."""
    column = config.row_id_col
    if column is not None:
        if column not in frame.columns:
            raise IfrsInputError(f"row_id_col '{column}' no está en el frame.")
        raw = frame[column].tolist()
    else:
        raw = frame.index.tolist()
    row_ids = [str(value) for value in raw]
    if len(set(row_ids)) != len(row_ids):
        raise IfrsInputError("Los identificadores de operación (row_id) deben ser únicos.")
    return row_ids


def _frame_column_texts(frame: DataFrame, column: str, label: str) -> list[str]:
    """Extrae una columna de texto obligatoria del ``frame`` como lista de ``str``."""
    if column not in frame.columns:
        raise IfrsInputError(f"{label} '{column}' no está en el frame.")
    return [str(value) for value in frame[column].tolist()]


def _frame_float_column(frame: DataFrame, column: str, label: str, numpy: Any) -> NDArrayFloat:
    """Extrae una columna float64 finita obligatoria del ``frame``."""
    if column not in frame.columns:
        raise IfrsInputError(f"La columna '{column}' ({label}) no está en el frame.")
    return _to_float_array(frame[column].to_numpy(), label, numpy)


def _frame_int_column(frame: DataFrame, column: str, numpy: Any) -> NDArrayFloat:
    """Extrae una columna entera finita (días de mora) validada aguas arriba por el staging."""
    return _to_float_array(frame[column].to_numpy(), column, numpy)


def _origination_pd_life(
    frame: DataFrame, config: IfrsProvisioningConfig, numpy: Any
) -> NDArrayFloat | None:
    """Extrae la PD lifetime en origen si el gatillo cuantitativo la declara, o ``None``."""
    column = config.staging.origination_pd_life_col
    if column is None:
        return None
    return _frame_float_column(frame, column, "origination_pd_life", numpy)


def _validate_term_structure(ts: DataFrame, numpy: Any) -> None:
    """Valida el contrato tidy y las invariantes de la term-structure (SDD-16 §6)."""
    missing = [column for column in _TS_REQUIRED_COLUMNS if column not in ts.columns]
    if missing:
        raise IfrsTermStructureError(
            f"La term-structure debe contener {_TS_REQUIRED_COLUMNS}; "
            f"columnas faltantes: {missing}."
        )
    if ts.shape[0] == 0:
        raise IfrsTermStructureError("La term-structure no puede estar vacía.")
    marginal = _ts_float(ts, "pd_marginal", numpy)
    if bool(numpy.any((marginal < 0.0) | (marginal > 1.0))):
        raise IfrsTermStructureError("pd_marginal de la term-structure debe estar en [0, 1].")
    if _TS_SURVIVAL_COLUMN in ts.columns and _TS_CUMULATIVE_COLUMN in ts.columns:
        survival = _ts_float(ts, _TS_SURVIVAL_COLUMN, numpy)
        cumulative = _ts_float(ts, _TS_CUMULATIVE_COLUMN, numpy)
        if bool(numpy.any(numpy.abs(cumulative - (1.0 - survival)) > _TS_INVARIANT_TOL)):
            raise IfrsTermStructureError(
                "La term-structure rompe la invariante pd_cumulative = 1 - survival."
            )


def _ts_float(ts: DataFrame, column: str, numpy: Any) -> NDArrayFloat:
    """Extrae una columna float64 finita de la term-structure con error de contrato tidy."""
    try:
        array = numpy.asarray(ts[column].to_numpy(), dtype=numpy.float64)
    except (ValueError, TypeError) as exc:
        raise IfrsTermStructureError(
            f"La columna '{column}' de la term-structure debe ser numérica."
        ) from exc
    if not bool(numpy.all(numpy.isfinite(array))):
        raise IfrsTermStructureError(f"La columna '{column}' de la term-structure debe ser finita.")
    return cast("NDArrayFloat", array)


def effective_horizon_12m(declared: int | None, term_structure: DataFrame) -> int:
    """Los períodos de la curva que cubren 12 meses: el declarado o, en blanco, el de su unidad.

    En blanco (``horizon_12m_periods=None``, lo que siembra el trabajo «Provisiones IFRS 9» de la
    pantalla) se infiere de la unidad que declara la curva con la misma regla que la puerta guiada
    ``bayesrisk.Ecl``: ``round(1 / year_fraction(unidad))`` —1 con años, 4 con trimestres, 12 con
    meses—. Una sola fuente para el motor, el paso que lo registra y el resumen que lo cuenta.

    La inferencia exige que TODAS las filas declaren una unidad reconocida y que sea una sola
    duración (``"year"`` y ``"años"`` valen lo mismo): con filas sin unidad, una unidad que
    :mod:`bayesrisk.core.time_units` no convierte o curvas de periodicidades distintas no hay un
    número que inferir, y se detiene con el arreglo en palabras en vez de suponer uno.

    Raises
    ------
    IfrsConfigError
        Si el horizonte está en blanco y la curva no permite inferirlo.
    """
    if declared is not None:
        return declared
    fracciones = {year_fraction(unidad) for unidad in _time_unit_values(term_structure)}
    if len(fracciones) != 1 or None in fracciones:
        raise IfrsConfigError(
            "«Períodos que cubren 12 meses» está en blanco para inferirlo de la unidad de la "
            "curva, y la curva no declara una sola unidad reconocida: declara la unidad de su "
            "duración —año, semestre, trimestre, mes, semana o día— o el número de períodos que "
            "cubren 12 meses."
        )
    (fraccion,) = fracciones
    return max(1, round(1.0 / cast("float", fraccion)))


def _time_unit_values(ts: DataFrame) -> list[str | None]:
    """Devuelve la unidad temporal declarada por fila, o ``None`` donde no la haya.

    La columna es opcional (CT-2 aditivo): una curva anterior a D-HOR-0, o de un productor de
    terceros, no la trae y debe seguir corriendo.
    """
    if _TS_TIME_UNIT_COLUMN not in ts.columns:
        return [None] * ts.shape[0]
    return [
        None if value is None or _is_missing(value) else str(value)
        for value in ts[_TS_TIME_UNIT_COLUMN].tolist()
    ]


def _prepare_term_structure(
    ts: DataFrame, config: IfrsProvisioningConfig, numpy: Any, *, truncar_vida: bool = True
) -> DataFrame:
    """Normaliza ``scenario``, convierte ``time_value`` a años y trunca por ``max_lifetime``.

    La conversión vive aquí —y no en ``EclEngine``— porque esta es la función que normaliza lo que
    los productores dejaron ambiguo, ya recibe el ``config``, y su salida alimenta por igual a
    ``_weighted_horizons``, ``_components_frame`` y el motor ECL: un solo punto, aguas arriba de
    todo (D-HOR-0).
    """
    scenario = [
        _SINGLE_SCENARIO_LABEL if value is None or _is_missing(value) else str(value)
        for value in (
            ts[_TS_SCENARIO_COLUMN].tolist()
            if _TS_SCENARIO_COLUMN in ts.columns
            else [None] * ts.shape[0]
        )
    ]
    period = _ts_float(ts, "period", numpy)
    if bool(numpy.any(period < 1.0)) or bool(numpy.any(period != numpy.floor(period))):
        raise IfrsTermStructureError(
            "period de la term-structure debe ser un entero mayor o igual a 1."
        )
    time_value = _ts_float(ts, "time_value", numpy)
    # List comprehension y no `.map()`/`.fillna()`: sobre una columna `object` con `None` esas dos
    # emiten el `FutureWarning` de downcasting de pandas >= 2.2, y con `filterwarnings=["error"]`
    # eso tumba la suite entera. Mismo patrón que la normalización de `scenario`, arriba.
    years = [
        valor * (year_fraction(unidad) or 1.0)
        for valor, unidad in zip(time_value.tolist(), _time_unit_values(ts), strict=True)
    ]
    prepared = ts.copy(deep=True)
    prepared[_TS_SCENARIO_COLUMN] = scenario
    prepared[_TS_YEARS_COLUMN] = years
    max_lifetime = config.pd.max_lifetime_periods
    if max_lifetime is not None and truncar_vida:
        prepared = prepared.loc[period <= max_lifetime].copy(deep=True)
        if prepared.shape[0] == 0:
            raise IfrsTermStructureError(
                f"No quedan períodos con period <= max_lifetime={max_lifetime} en la "
                "term-structure."
            )
    return prepared


def _is_missing(value: Any) -> bool:
    """Indica si un escalar de ``scenario`` es un faltante (``NaN``) sin importar pandas."""
    return isinstance(value, float) and math.isnan(value)


def _ts_row_ids_sin_unidad(ts: DataFrame) -> set[str]:
    """Devuelve los ``row_id`` con alguna fila cuya unidad temporal no sea convertible.

    Por fila y no por frame: ``forward`` concatena N term-structures en una sola tabla, así que
    unas filas pueden declarar la unidad y otras no. Un veredicto por frame marcaría de más o de
    menos, y en ambos casos mentiría.
    """
    unidades = _time_unit_values(ts)
    row_ids = [str(value) for value in ts["row_id"].to_numpy()]
    return {
        row_id
        for row_id, unidad in zip(row_ids, unidades, strict=True)
        if year_fraction(unidad) is None
    }


def _horizonte_inconmensurable(ts: DataFrame, horizonte: int, numpy: Any) -> bool:
    """Indica si ``horizon_12m_periods`` no es conmensurable con alguna curva recibida.

    Dos criterios, y **ninguno de los dos es «el horizonte alcanza el soporte»**. Ese era el modo A
    de la §1 de la enmienda, y programarlo demostró que es un gatillo **equivocado**: una curva
    mensual de 12 períodos con ``horizon_12m_periods=12`` —la configuración de fábrica, y el caso
    más común que existe— tiene el horizonte cubriendo toda la curva **y es correcta**: es una
    curva lifetime de doce meses, donde que Stage 1 iguale a Stage 2 es la contabilidad esperada,
    no un defecto. Un aviso que dispara ahí se aprende a ignorar, y como es gobernable, además
    abortaba la corrida.

    Los dos se miden **por curva** ``(row_id, scenario)`` —la misma agrupación con que
    ``marginal_to_horizon`` suma la PD a 12 meses— y basta una curva desajustada (D-ECL-0): un frame
    admite curvas de unidades y soportes distintos (``forward`` concatena fuentes), y mirar el frame
    entero dejaba que una mensual de 12 períodos escondiera a una anual de 5, o a otra que empieza
    en el mes 18 (pasada 1 de Codex sobre la capa 0).

    - **La ventana de 12 meses está vacía** (``H`` bajo el primer período de la curva): la máscara
      no selecciona nada y Stage 1 provisiona **cero**, sin error. No necesita unidad: es un defecto
      cualquiera sea la periodicidad, también en una curva que no la declara.
    - **La ventana no dura un año.** Con la unidad declarada, el instante cae en
      ``time_value_years`` y se **verifica** en vez de inferirse (D-HOR-0); nunca se presume
      ``period == time_value``: cuatro cortes trimestrales expresados en años tienen ``period`` 1…4
      y el horizonte correcto es 4. Sea ``sel`` el mayor período de la curva que no supera ``H`` (el
      último que suma la ventana) y ``d`` su duración en años: con ``H`` en la curva o en un hueco,
      dispara si ``|d - 1| > tol``; con ``H`` más allá del último período, la ventana suma la curva
      entera y dispara sólo si ``d > 1 + tol`` —una curva que entera dura un año o menos tiene la
      ECL a 12 meses igual a la lifetime, y ésa es la contabilidad correcta—. Medido: con el
      default ``H = 12`` sobre una curva anual de cinco períodos, la corrida terminaba con la ECL al
      doble. Una curva sin unidad convertible se salta **sola** en este criterio: ahí
      ``time_value_years`` es una presunción del propio motor, acusar al usuario con ella sería
      acusarlo de un supuesto ajeno, y ``DATO-INSTITUCIONAL-IFRS-7`` ya cubre ese caso.

    La tolerancia es ancha a propósito. Un año son 12 meses, 4 trimestres o 52 semanas, pero también
    365 días contra los 360 de alguna convención, o un `time_value` que arranca en 0 en vez de en el
    fin del primer período. El aviso busca el error de **orden de magnitud** —doce años donde debía
    haber uno—, no la discrepancia de calendario; un gatillo estrecho dispararía sobre curvas
    legítimas y se aprendería a ignorar.
    """
    for puntos, con_unidad in _curvas_por_operacion(ts, numpy).values():
        ventana = [punto for punto in puntos if punto[0] <= horizonte]
        if not ventana:
            return True
        if not con_unidad:
            continue
        _, duracion = max(ventana)
        if horizonte > max(periodo for periodo, _ in puntos):
            if duracion > 1.0 + _HORIZONTE_ANIO_TOL:
                return True
        elif abs(duracion - 1.0) > _HORIZONTE_ANIO_TOL:
            return True
    return False


def _curvas_por_operacion(
    ts: DataFrame, numpy: Any
) -> dict[tuple[str, str], tuple[list[tuple[float, float]], bool]]:
    """Agrupa la curva por ``(row_id, scenario)``: sus puntos y si su duración se puede medir.

    Cada curva trae sus ``(period, time_value_years)`` y si declara una unidad convertible en todas
    sus filas: una sola fila sin unidad basta para no medir su duración.
    """
    anios = (
        _ts_float(ts, _TS_YEARS_COLUMN, numpy).tolist()
        if _TS_YEARS_COLUMN in ts.columns
        else [math.nan] * ts.shape[0]
    )
    convertible: dict[str | None, bool] = {}
    curvas: dict[tuple[str, str], tuple[list[tuple[float, float]], bool]] = {}
    for row_id, escenario, periodo, anio, unidad in zip(
        (str(value) for value in ts["row_id"].to_numpy()),
        (str(value) for value in ts[_TS_SCENARIO_COLUMN].to_numpy()),
        _ts_float(ts, "period", numpy).tolist(),
        anios,
        _time_unit_values(ts),
        strict=True,
    ):
        if unidad not in convertible:
            convertible[unidad] = year_fraction(unidad) is not None
        puntos, con_unidad = curvas.get((row_id, escenario), ([], True))
        puntos.append((periodo, anio))
        medible = convertible[unidad] and not math.isnan(anio)
        curvas[(row_id, escenario)] = (puntos, con_unidad and medible)
    return curvas


def _ts_lgd_present(ts: DataFrame) -> bool:
    """Indica si la term-structure trae una columna ``lgd`` con al menos un valor no nulo.

    Forward publica la columna toda-``None`` cuando el satellite no proyecta LGD; ese caso no
    cuenta como LGD forward presente (no habría nada que descartar).
    """
    if _TS_LGD_COLUMN not in ts.columns:
        return False
    return bool(ts[_TS_LGD_COLUMN].notna().any())


def _require_pit_basis(ts: DataFrame) -> None:
    """Exige que la term-structure venga etiquetada ``pd_basis='pit'`` para ``consume_pit``."""
    if _TS_PD_BASIS_COLUMN not in ts.columns:
        raise IfrsConfigError(
            "pit_mode='consume_pit' exige una term-structure PIT (columna pd_basis='pit'); "
            "la term-structure entrante no la trae (¿es TTC de survival/markov?)."
        )
    basis = {str(value) for value in ts[_TS_PD_BASIS_COLUMN].tolist()}
    if basis != {"pit"}:
        raise IfrsConfigError(
            "pit_mode='consume_pit' exige pd_basis='pit' en toda la term-structure; "
            f"observado={sorted(basis)}."
        )


def _forbid_pit_basis(ts: DataFrame) -> None:
    """Rechaza aplicar Vasicek sobre una term-structure ya PIT (guard anti doble ajuste macro).

    Espejo de :func:`_require_pit_basis`: columna ``pd_basis`` ausente (survival/markov) o toda
    ``'ttc'`` pasa; cualquier otro conjunto (``'pit'`` de forward, mixto o faltantes) se rechaza.
    """
    if _TS_PD_BASIS_COLUMN not in ts.columns:
        return
    basis = {str(value) for value in ts[_TS_PD_BASIS_COLUMN].tolist()}
    if basis != {"ttc"}:
        raise IfrsConfigError(
            "pit_mode='apply_vasicek' sólo admite term-structures TTC; la entrante declara "
            f"pd_basis={sorted(basis)} (¿curvas PIT de forward? use pit_mode='consume_pit' "
            "para evitar el doble ajuste macro)."
        )


def _apply_vasicek(
    ts: DataFrame, config: IfrsProvisioningConfig, marginal: NDArrayFloat, numpy: Any
) -> NDArrayFloat:
    """Transforma la PD TTC a PIT con Vasicek monofactorial (``rho`` escalar, ``Z``) (SDD-16 §3).

    IFRS9-FIRMABLE D-FIR-6 (§3.6): la transformación de Vasicek está definida para la
    probabilidad condicional del período —el riesgo ``h``—, no para la PD marginal, que es
    incondicional. Por curva ``(row_id, escenario)`` se recupera ``h_t = m_t / S_{t-1}``, se
    transforma con el ``Z`` de su fila y se recompone ``m'_t = S'_{t-1} · h'_t``. Sobre la marginal,
    con ``Z = -1`` y ``rho = 0,10``, 126 operaciones del paquete quedaban con PD de vida mayor
    que 1.
    """
    _forbid_pit_basis(ts)
    rho = config.pd.rho
    if rho is None:
        raise IfrsConfigError(
            "pit_mode='apply_vasicek' exige un rho escalar (pd.rho) en tiempo de cálculo."
        )
    column = config.pd.systemic_factor_col
    if column is None or column not in ts.columns:
        raise IfrsConfigError(
            "pit_mode='apply_vasicek' exige la columna del factor sistémico Z "
            "(pd.systemic_factor_col) en la term-structure."
        )
    z = _ts_float(ts, column, numpy)
    pandas = _import_pandas()
    curvas = [
        f"{rid}\x1f{escenario}"
        for rid, escenario in zip(
            (str(v) for v in ts["row_id"].tolist()),
            (str(v) for v in ts[_TS_SCENARIO_COLUMN].tolist()),
            strict=True,
        )
    ]
    periodo = _ts_float(ts, "period", numpy)
    orden = numpy.lexsort((periodo, numpy.asarray(curvas, dtype=object)))
    claves = numpy.asarray(curvas, dtype=object)[orden]
    esperado = pandas.Series(periodo[orden]).groupby(claves).cumcount().to_numpy() + 1
    if bool(numpy.any(periodo[orden] != esperado)):
        raise IfrsTermStructureError(
            "pit_mode='apply_vasicek' transforma el riesgo de cada período, y la curva de cada "
            "operación tiene que ir del período 1 al último sin saltos para recuperarlo."
        )
    m = marginal[orden]
    acumulada = pandas.Series(m).groupby(claves).cumsum().to_numpy()
    previa = 1.0 - (acumulada - m)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        riesgo = numpy.clip(numpy.where(previa > 0.0, m / previa, 0.0), 0.0, 1.0)
    pit = vasicek_pit(riesgo, rho=rho, z=z[orden])
    # Producto acumulado y no suma de logaritmos: un riesgo transformado de 1 daba NaN (pasada 1
    # de Codex sobre el código).
    sobrevive = pandas.Series(1.0 - numpy.minimum(pit, 1.0)).groupby(claves).cumprod()
    antes = sobrevive.groupby(claves).shift(1, fill_value=1.0).to_numpy()
    nueva = numpy.maximum(antes - sobrevive.to_numpy(), 0.0)
    salida = numpy.empty_like(nueva)
    salida[orden] = nueva
    return cast("NDArrayFloat", numpy.where(salida == 0.0, 0.0, salida))


def _forward_weights(ts: DataFrame, scenarios_present: list[str], numpy: Any) -> dict[str, float]:
    """Extrae los pesos por escenario de la columna ``scenario_weight`` de forward (SDD-16 §5)."""
    if _TS_SCENARIO_WEIGHT_COLUMN not in ts.columns:
        raise IfrsConfigError(
            "scenarios.source='forward' exige la columna scenario_weight en la term-structure."
        )
    weight = _ts_float(ts, _TS_SCENARIO_WEIGHT_COLUMN, numpy)
    scenarios = [str(value) for value in ts[_TS_SCENARIO_COLUMN].tolist()]
    resolved: dict[str, float] = {}
    for name, value in zip(scenarios, (float(item) for item in weight), strict=True):
        if name in resolved and resolved[name] != value:
            raise IfrsConfigError(
                f"El peso del escenario '{name}' no es constante en la term-structure de forward."
            )
        resolved[name] = value
    return {name: resolved[name] for name in scenarios_present}


def _weighted_horizons(
    ts: DataFrame,
    horizon_12m: int,
    weights: dict[str, float],
    pandas: Any,
) -> tuple[dict[str, float], dict[str, float]]:
    """Deriva y pondera por escenario la PD 12m/lifetime por operación (SDD-16 §7)."""
    ts_pd = ts.loc[:, ["row_id", _TS_SCENARIO_COLUMN, "period", "pd_marginal"]].copy(deep=True)
    horizons = marginal_to_horizon(ts_pd, horizon_periods=horizon_12m)
    weight_series = horizons[_TS_SCENARIO_COLUMN].map(weights)
    weighted = pandas.DataFrame(
        {
            "row_id": [str(value) for value in horizons["row_id"].to_numpy()],
            "_pd_12m": horizons["pd_12m"].to_numpy() * weight_series.to_numpy(),
            "_pd_life": horizons["pd_life"].to_numpy() * weight_series.to_numpy(),
        }
    )
    grouped = weighted.groupby("row_id", sort=False, dropna=False).agg(
        pd_12m=("_pd_12m", "sum"), pd_life=("_pd_life", "sum")
    )
    pd_12m = {str(rid): float(value) for rid, value in grouped["pd_12m"].items()}
    pd_life = {str(rid): float(value) for rid, value in grouped["pd_life"].items()}
    return pd_12m, pd_life


def _calibrated_pd_12m(
    calibrated: DataFrame | None, row_ids: list[str], numpy: Any
) -> dict[str, float]:
    """Ancla la PD 12m a la PD calibrada de SDD-10 (``base_pd_source='calibration'``)."""
    if calibrated is None:
        raise IfrsConfigError(
            "base_pd_source='calibration' exige el frame de PD calibrada "
            "(calibration.calibrated_pd_frame)."
        )
    if _CALIBRATED_PD_COLUMN not in calibrated.columns:
        raise IfrsConfigError(
            f"El frame de PD calibrada debe contener la columna '{_CALIBRATED_PD_COLUMN}'."
        )
    keys = [str(index) for index in calibrated.index]
    mapping = dict(zip(keys, calibrated[_CALIBRATED_PD_COLUMN].tolist(), strict=True))
    missing = [rid for rid in row_ids if rid not in mapping]
    if missing:
        raise IfrsConfigError(f"El frame de PD calibrada no cubre las operaciones: {missing}.")
    # CASO-REAL-IFRS9 D-CRE-5 (pasada 3 de Codex): se valida sólo la PD de las operaciones que se
    # provisionan; la de una fila sin exposición no se usa, y una vacía no aborta la provisión.
    values = _to_float_array([mapping[rid] for rid in row_ids], _CALIBRATED_PD_COLUMN, numpy)
    return dict(zip(row_ids, (float(value) for value in values), strict=True))


def _components_frame(
    ts: DataFrame,
    row_ids: list[str],
    lgd_by_rid: dict[str, float],
    ead_by_rid: dict[str, float],
    pandas: Any,
    *,
    ead_por_periodo: NDArrayFloat | None = None,
) -> DataFrame:
    """Arma la malla tidy de componentes para ``EclEngine`` en orden del ``frame`` (SDD-16 §7).

    ``ead_por_periodo`` es la exposición de cada fila de ``ts`` cuando la operación sigue la tabla
    de pagos de su cuota (CASO-REAL-IFRS9 D-CRE-3); sin ella, la de la operación en cada período.
    Con la curva leída por contrato, la malla lleva además el tramo de la curva de cada período.
    """
    order = {rid: index for index, rid in enumerate(row_ids)}
    ts_row_ids = [str(value) for value in ts["row_id"].to_numpy()]
    columnas: dict[str, Any] = {
        "row_id": ts_row_ids,
        "scenario": [str(value) for value in ts[_TS_SCENARIO_COLUMN].tolist()],
        "period": ts["period"].to_numpy(),
        "time_value": ts["time_value"].to_numpy(),
        "time_value_years": ts[_TS_YEARS_COLUMN].to_numpy(),
        "pd_marginal": ts["pd_marginal"].to_numpy(),
        "lgd": [lgd_by_rid[rid] for rid in ts_row_ids],
        "ead": (
            [ead_by_rid[rid] for rid in ts_row_ids] if ead_por_periodo is None else ead_por_periodo
        ),
    }
    for tramo in (*_CURVE_SEGMENT_COLUMNS, _CYCLE_SHIFT_COLUMN):
        if tramo in ts.columns:
            columnas[tramo] = ts[tramo].to_numpy()
    columnas["_order"] = [order[rid] for rid in ts_row_ids]
    components = pandas.DataFrame(columnas)
    components = components.sort_values(
        ["_order", "scenario", "period"], kind="mergesort"
    ).reset_index(drop=True)
    return cast("DataFrame", components.drop(columns="_order"))


def _con_tramo_de_la_curva(ecl_ts: DataFrame, components: DataFrame) -> DataFrame:
    """Añade a la ``ecl_term_structure`` el tramo de la curva de cada período (§3.2, aditivo).

    Y, con escenarios, el desplazamiento de cada tramo (IFRS9-FIRMABLE D-FIR-1): copia las
    columnas de la malla que estén.

    ``EclEngine`` arma su salida fila a fila de la malla, en el mismo orden y sin filtrar (el motor
    no le pasa ``max_lifetime``): el tramo se copia por posición, y se comprueba.
    """
    if not (
        len(ecl_ts.index) == len(components.index)
        and (ecl_ts["row_id"].to_numpy() == components["row_id"].to_numpy()).all()
        and (ecl_ts["period"].to_numpy() == components["period"].to_numpy()).all()
    ):
        raise IfrsTermStructureError(
            "La term-structure de ECL no se alinea con la malla de componentes."
        )
    salida = ecl_ts.copy(deep=True)
    for tramo in (*_CURVE_SEGMENT_COLUMNS, _CYCLE_SHIFT_COLUMN):
        if tramo in components.columns:
            salida[tramo] = components[tramo].to_numpy()
    return salida


def _ventanas_por_periodo(
    ts_ttc: DataFrame, por_contrato: bool, shifter: CycleShifter, pandas: Any
) -> DataFrame:
    """Las ventanas de calendario que la corrida usó de verdad, para ``cycle_by_period``.

    Una fila por período y largo distintos: con las fechas del contrato, el tramo ``t`` empieza en
    ``(t - 1)·u`` y dura lo que la operación vive en él —el último de cada una puede ser parcial
    (pasada 2 de Codex: publicar sólo el período completo describía meses que nadie consumió)—;
    sin ellas, la ventana de la grilla de la curva (:func:`period_windows`).
    """
    if por_contrato:
        u = shifter.months_per_period
        periodo = pandas.to_numeric(ts_ttc["period"])
        largo = (
            pandas.to_numeric(ts_ttc["curve_end"]) - pandas.to_numeric(ts_ttc["curve_start"])
        ) * u
        ventanas = pandas.DataFrame(
            {"period": periodo, "start": (periodo - 1) * u, "length": largo}
        )
    else:
        ventanas = period_windows(ts_ttc)[["period", "start", "length"]]
    redondeo = ventanas.assign(
        _largo=ventanas["length"].round(9), _inicio=ventanas["start"].round(9)
    )
    unicas: DataFrame = (
        redondeo.drop_duplicates(["period", "_inicio", "_largo"])
        .sort_values(["period", "_largo"], kind="mergesort")
        .drop(columns=["_inicio", "_largo"])
    )
    return unicas.reset_index(drop=True)


def _check_cycle_config(config: IfrsProvisioningConfig) -> None:
    """Lo que el ajuste por ciclo exige de la sección (D-FIR-1), comprobado también por código.

    Raises
    ------
    IfrsConfigError
        Si la curva no es la de ``survival``, los pesos no vienen de ``forward`` o la PD a 12
        meses se toma de la calibración.
    """
    if config.pd.term_structure_source != "survival":
        raise IfrsConfigError(
            "pd.pit_mode='cycle' desplaza el riesgo de la curva de supervivencia por tramo de "
            f"calendario; la de {config.pd.term_structure_source} no es una curva por edad."
        )
    if config.scenarios.source != "forward":
        raise IfrsConfigError(
            "pd.pit_mode='cycle' pondera con los pesos de los escenarios de la institución, que "
            "trae la sección forward: usa scenarios.source='forward'."
        )
    if config.pd.base_pd_source == "calibration":
        raise IfrsConfigError(
            "pd.pit_mode='cycle': la PD a 12 meses sale de la curva ajustada por escenario; la "
            "calibración la fijaría sin el ciclo. Usa pd.base_pd_source='term_structure'."
        )


def _ecl_del_ciclo(
    *,
    config: IfrsProvisioningConfig,
    shifter: CycleShifter,
    components: DataFrame,
    ts_ttc: DataFrame,
    lectura_ttc: ContractReading | None,
    row_ids: list[str],
    lgd_by_rid: dict[str, float],
    ead_by_rid: dict[str, float],
    eir_arr: NDArrayFloat,
    stage_arr: Any,
    horizonte_12m: int,
    pandas: Any,
) -> dict[str, Any]:
    """La ECL reportada de cada escenario y la de desplazamiento cero, sin redondear (§3.1).

    Con la MISMA etapa y el mismo horizonte por etapa que el total ponderado: así
    ``Σ_k w_k · ecl_reported_by_scenario[k]`` es la suma de ``detail.ecl_reported_unrounded``; el
    redondeo se aplica después de ponderar y su puente es ``rounding.total_difference``. La de
    desplazamiento cero es la curva sin escenarios —la de la 2.7.0— con esa misma etapa.
    """
    motor = EclEngine.from_config(config.ecl)
    eir = pandas.Series(eir_arr, index=row_ids)
    etapas = pandas.Series(stage_arr, index=row_ids)
    por_escenario: dict[str, float] = {}
    for nombre in shifter.names:
        malla = components.loc[components["scenario"].astype(str) == nombre].reset_index(drop=True)
        _ts, detalle = motor.compute(
            malla, eir=eir, stages=etapas, weights={nombre: 1.0}, horizon_12m=horizonte_12m
        )
        por_escenario[nombre] = float(detalle["ecl_reported_unrounded"].sum())
    malla_ttc = _components_frame(
        ts_ttc,
        row_ids,
        lgd_by_rid,
        ead_by_rid,
        pandas,
        ead_por_periodo=None if lectura_ttc is None else lectura_ttc.ead,
    )
    etiqueta = str(malla_ttc["scenario"].iloc[0])
    _ts, detalle_ttc = motor.compute(
        malla_ttc, eir=eir, stages=etapas, weights={etiqueta: 1.0}, horizon_12m=horizonte_12m
    )
    return {
        "ecl_reported_by_scenario": por_escenario,
        "ecl_reported_ttc": float(detalle_ttc["ecl_reported_unrounded"].sum()),
        "cycle": {
            **shifter.anchor.as_section(),
            "first_future_month": shifter.first_month,
            "reversion_months": int(shifter.model.reversion_months),
            "first_year_shift": shifter.first_year_shift(),
        },
    }


def _campos_del_contrato(lectura: ContractReading) -> dict[str, Any]:
    """Los campos aditivos de la card cuando la curva se leyó con las fechas (§3.2 y §3.3)."""
    return {
        "contract_dates": True,
        "n_matured_with_balance": lectura.n_matured_with_balance,
        "ead_matured_with_balance": lectura.ead_matured_with_balance,
        "tail_from_period": lectura.tail_from_period,
        "ead_beyond_observed_curve": lectura.ead_beyond_observed_curve,
        "n_amortizing": len(lectura.amortizing),
        "n_installment_not_amortizing": lectura.n_installment_not_amortizing,
        "ead_installment_not_amortizing": lectura.ead_installment_not_amortizing,
    }


def _summary_frame(detail_rows: list[dict[str, Any]], pandas: Any) -> DataFrame:
    """Agrega el resumen por ``portfolio`` x ``stage`` con cobertura y warnings (SDD-16 §6)."""
    groups: dict[tuple[str, int], dict[str, Any]] = {}
    for row in detail_rows:
        key = (str(row["portfolio"]), int(row["stage"]))
        bucket = groups.setdefault(
            key,
            {"n_rows": 0, "total_ead": 0.0, "total_ecl_reported": 0.0, "warnings": []},
        )
        bucket["n_rows"] += 1
        bucket["total_ead"] += float(row["ead"])
        bucket["total_ecl_reported"] += float(row["ecl_reported"])
        bucket["warnings"].extend(row["warning_codes"])
    summary_rows: list[dict[str, Any]] = []
    for portfolio, stage in sorted(groups):
        bucket = groups[(portfolio, stage)]
        total_ead = float(bucket["total_ead"])
        total_ecl = float(bucket["total_ecl_reported"])
        coverage = total_ecl / total_ead if total_ead > 0.0 else 0.0
        summary_rows.append(
            {
                "portfolio": portfolio,
                "stage": stage,
                "scenario": _SUMMARY_SCENARIO_LABEL,
                "n_rows": int(bucket["n_rows"]),
                "total_ead": total_ead,
                "total_ecl_reported": total_ecl,
                "coverage_ratio": coverage,
                "warning_codes": tuple(_ordered_unique(bucket["warnings"])),
            }
        )
    return cast("DataFrame", pandas.DataFrame(summary_rows, columns=list(_SUMMARY_COLUMNS)))


def _ecl_by_scenario(ecl_term_structure: DataFrame) -> dict[str, float]:
    """Suma la ECL marginal (sin ponderar) por escenario como diagnóstico auditable CT-2."""
    grouped = ecl_term_structure.groupby("scenario", sort=True, dropna=False)["ecl_marginal"].sum()
    return {str(scenario): float(value) for scenario, value in grouped.items()}


def _check_row_coverage(frame_row_ids: list[str], ts_row_ids: list[str]) -> None:
    """Exige que la term-structure cubra exactamente las operaciones del ``frame``."""
    frame_set = set(frame_row_ids)
    ts_set = set(ts_row_ids)
    if frame_set != ts_set:
        faltan = sorted(frame_set - ts_set)
        sobran = sorted(ts_set - frame_set)
        # D-CRE-6: si NINGÚN identificador coincide, la causa casi nunca es una curva incompleta
        # sino que la curva y la provisión identifican las operaciones por cosas distintas (una
        # columna en una y el índice en la otra). Por código no hay preflight que lo avise; el
        # mensaje lo dice además de las listas.
        causa = (
            " Ningún identificador coincide: la curva y la provisión no identifican las "
            "operaciones igual. Declara la misma columna en survival.input.id_col y en "
            "provisioning_ifrs9.row_id_col, o ninguna de las dos."
            if frame_set.isdisjoint(ts_set)
            else ""
        )
        raise IfrsTermStructureError(
            "La term-structure debe cubrir exactamente las operaciones del frame "
            f"(sin curva={faltan}, sin operación={sobran}).{causa}"
        )


def _ordered_unique(values: Any) -> list[str]:
    """Devuelve los elementos únicos preservando el orden de aparición (determinismo)."""
    return list(dict.fromkeys(str(value) for value in values))


def _to_float_array(values: Any, name: str, numpy: Any) -> NDArrayFloat:
    """Castea a float64 y exige valores finitos, mapeando fallos a ``IfrsInputError``."""
    try:
        array = numpy.asarray(values, dtype=numpy.float64)
    except (ValueError, TypeError) as exc:
        raise IfrsInputError(f"El campo '{name}' debe ser numérico.") from exc
    if not bool(numpy.all(numpy.isfinite(array))):
        raise IfrsInputError(f"El campo '{name}' debe contener sólo valores finitos.")
    return cast("NDArrayFloat", array)


def _as_dataframe(value: Any, pandas: Any, artifact: str) -> DataFrame:
    """Valida que un insumo sea un ``pandas.DataFrame`` antes de leerlo."""
    if isinstance(value, pandas.DataFrame):
        return cast("DataFrame", value)
    raise IfrsInputError(
        f"El insumo '{artifact}' debe ser un pandas.DataFrame; "
        f"tipo observado={type(value).__name__}."
    )


def _dependency_versions(config: IfrsProvisioningConfig) -> dict[str, str]:
    """Recolecta versiones de dependencias según los enfoques ejercidos (auditoría §9)."""
    distributions = {"pandas": "pandas", "numpy": "numpy"}
    if config.pd.pit_mode == "apply_vasicek":
        distributions["scipy"] = "scipy"
    if config.lgd.method in ("beta_regression", "fractional_response"):
        distributions["statsmodels"] = "statsmodels"
    versions: dict[str, str] = {}
    for public_name, distribution in distributions.items():
        try:
            versions[public_name] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[public_name] = "no_instalado"
    return versions


def _import_numpy() -> Any:
    """Importa ``numpy`` bajo demanda para preservar el import liviano del núcleo."""
    try:
        return importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_NUMPY_MESSAGE) from exc


def _import_pandas() -> Any:
    """Importa ``pandas`` bajo demanda para preservar el import liviano del núcleo."""
    try:
        return importlib.import_module("pandas")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_PANDAS_MESSAGE) from exc
