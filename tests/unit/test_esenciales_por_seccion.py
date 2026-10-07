"""Golden bidireccional de los campos esenciales por sección (SDD-31 D-SIM-4; enmienda §3.8).

La marca es un metadato del schema —``json_schema_extra={"ui_essential": True}``— y este gate la
ata en los dos sentidos: **una marca que no esté en el golden** pone rojo (nadie amplía los
esenciales sin decirlo aquí) y **una entrada del golden sin marca** también (nadie los pierde en
silencio). El tope vigente es **6 por sección** (Cami, 2026-09-18, SDD-31 §12.1) y se mide sobre lo
que la pantalla muestra a la vez: en una unión discriminada —la estrategia de partición— cuenta
la rama con más esenciales, no la suma de todas, porque el formulario pinta una rama por vez. Su
única excepción es ``provisioning_ifrs9`` con **12** (FLUJO-GUIADO-IFRS9 §8-4, Cami, 2026-10-03, con
7: las siete columnas de la entrada mínima de la provisión, la marca de incumplimiento incluida;
ampliada a 10 por CASO-REAL-IFRS9 §8-3, Cami, 2026-10-05: las tres columnas opcionales del contrato,
otorgamiento, vencimiento y cuota; y a 12 por IFRS9-FIRMABLE §8-5, Cami, 2026-10-07: las dos PD del
modelo, la de hoy y la del otorgamiento).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

from bayesrisk.ui.routes import schema_payload

TOPE_ESENCIALES_POR_SECCION: Final = 6
#: La única excepción al tope, sólo para esta sección (FLUJO-GUIADO-IFRS9 §8-4; 7 → 10 por
#: CASO-REAL-IFRS9 §8-3; 10 → 12 por IFRS9-FIRMABLE §8-5).
EXCEPCION_AL_TOPE: Final[dict[str, int]] = {"provisioning_ifrs9": 12}

#: Los caminos marcados, por sección, tal como los pinta la tabla §3.8 de la enmienda del
#: scorecard (39 marcas en sus 12 secciones; ``eda`` no tiene ninguna: todo default, el resumen lo
#: muestra) y la §3.7 de FLUJO-GUIADO-IFRS9 (``survival`` 5 y ``provisioning_ifrs9`` 7, 10 desde
#: CASO-REAL-IFRS9 §8-3 y 12 desde IFRS9-FIRMABLE §8-5): 56 marcas y 54 caminos en 14 secciones.
#: Un mismo camino puede vivir en varias ramas de una unión (``holdout_fraction``) y se lista una
#: vez.
ESENCIALES_POR_SECCION: Final[dict[str, tuple[str, ...]]] = {
    "data": (
        "data.load.source",
        "data.schema.unique_keys",
        "data.target.bad_rule",
        "data.partition.strategy.cohort_col",
        "data.partition.strategy.date_col",
        "data.partition.strategy.holdout_fraction",
        "data.partition.strategy.oot_cohorts",
        "data.partition.strategy.oot_from",
    ),
    "eda": (),
    "binning": (
        "binning.categorical_columns",
        "binning.feature_columns",
        "binning.max_n_bins",
        "binning.min_bin_size",
        "binning.monotonic_trend",
    ),
    "selection": (
        "selection.correlation.threshold",
        "selection.min_iv",
        "selection.vif.threshold",
    ),
    "model": (
        "model.sign_policy.action",
        "model.stepwise.enabled",
        "model.stepwise.entry_p_value",
        "model.stepwise.exit_p_value",
    ),
    "scorecard": ("scorecard.pdo", "scorecard.target_odds", "scorecard.target_score"),
    "calibration": ("calibration.anchor_source", "calibration.target_pd"),
    "performance": ("performance.n_deciles",),
    "stability": ("stability.psi_review_threshold", "stability.psi_stable_threshold"),
    "validation": ("validation.families",),
    "report": (
        "report.document.author",
        "report.document.entity",
        "report.document.model_name",
        "report.document.portfolio",
        "report.formats",
    ),
    "governance": (
        "governance.author",
        "governance.purpose",
        "governance.review_period_months",
    ),
    # FLUJO-GUIADO-IFRS9 D-ECL-6: los argumentos de la curva y de la provisión en `bayesrisk.Ecl`.
    "survival": (
        "survival.input.covariate_cols",
        "survival.input.duration_col",
        "survival.input.event_col",
        "survival.time_grid.horizon_periods",
        "survival.time_grid.time_unit",
    ),
    "provisioning_ifrs9": (
        "provisioning_ifrs9.as_of_date_col",
        "provisioning_ifrs9.ead.ead_col",
        "provisioning_ifrs9.ecl.eir_col",
        "provisioning_ifrs9.lgd.lgd_col",
        "provisioning_ifrs9.portfolio_col",
        "provisioning_ifrs9.staging.days_past_due_col",
        "provisioning_ifrs9.staging.is_default_col",
        # CASO-REAL-IFRS9 D-CRE-8 (§8-3): las tres del contrato, opcionales.
        "provisioning_ifrs9.origination_date_col",
        "provisioning_ifrs9.maturity_date_col",
        "provisioning_ifrs9.ead.installment_col",
        # IFRS9-FIRMABLE D-FIR-11 (§8-5): las dos PD del modelo, opcionales.
        "provisioning_ifrs9.pd.pd_12m_col",
        "provisioning_ifrs9.staging.origination_pd_12m_col",
    ),
}

#: Lo que la pantalla muestra a la vez por sección (la rama más cargada de la partición: fecha o
#: cohorte con su frontera y su holdout). Es la cifra 2 de SDD-31 §5 para el scorecard.
ESENCIALES_VISIBLES_A_LA_VEZ: Final[dict[str, int]] = {
    "data": 6,
    "eda": 0,
    "binning": 5,
    "selection": 3,
    "model": 4,
    "scorecard": 3,
    "calibration": 2,
    "performance": 1,
    "stability": 2,
    "validation": 1,
    "report": 5,
    "governance": 3,
    "survival": 5,
    "provisioning_ifrs9": 12,
}


def _schema() -> tuple[dict[str, Any], dict[str, Any]]:
    schema = schema_payload()["json_schema"]
    return schema, schema.get("$defs", {})


def _resolver(nodo: Any, defs: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(nodo, dict):
        return {}
    if "$ref" in nodo:
        base = _resolver(defs.get(nodo["$ref"].rsplit("/", 1)[-1], {}), defs)
        return {**base, **{k: v for k, v in nodo.items() if k != "$ref"}}
    return nodo


def _ramas(nodo: dict[str, Any], defs: dict[str, Any]) -> list[dict[str, Any]]:
    """Las ramas objeto de una unión, resueltas; la rama nula no cuenta."""
    ramas = []
    for rama in nodo.get("anyOf") or nodo.get("oneOf") or []:
        if isinstance(rama, dict) and rama.get("type") != "null":
            resuelta = _resolver(rama, defs)
            if resuelta.get("properties") or resuelta.get("type"):
                ramas.append(resuelta)
    return ramas


def _marcas(nodo: Any, defs: dict[str, Any], prefijo: str, visto: tuple[str, ...]) -> set[str]:
    """Todos los caminos marcados bajo ``nodo``, en todas las ramas (sin ``[]`` de listas)."""
    nodo = _resolver(nodo, defs)
    salida: set[str] = set()
    if nodo.get("ui_essential") is True:
        salida.add(prefijo)
    ref = nodo.get("title", "") + str(sorted(nodo.get("properties", {})))
    if ref in visto:
        return salida
    for rama in _ramas(nodo, defs):
        salida |= _marcas({k: v for k, v in rama.items()}, defs, prefijo, (*visto, ref))
    for nombre, hijo in nodo.get("properties", {}).items():
        camino = f"{prefijo}.{nombre}" if prefijo else nombre
        salida |= _marcas(hijo, defs, camino, (*visto, ref))
    items = nodo.get("items")
    if isinstance(items, dict):
        salida |= _marcas(items, defs, prefijo, (*visto, ref))
    return salida


def _visibles_a_la_vez(nodo: Any, defs: dict[str, Any], visto: tuple[str, ...]) -> int:
    """Marcas que la pantalla muestra a la vez: en una unión, la rama con más; el nodo cuenta."""
    nodo = _resolver(nodo, defs)
    total = 1 if nodo.get("ui_essential") is True else 0
    ref = nodo.get("title", "") + str(sorted(nodo.get("properties", {})))
    if ref in visto:
        return total
    ramas = _ramas(nodo, defs)
    if len(ramas) > 1:
        return total + max(_visibles_a_la_vez(rama, defs, (*visto, ref)) for rama in ramas)
    if len(ramas) == 1:
        return total + _visibles_a_la_vez(ramas[0], defs, (*visto, ref))
    for hijo in nodo.get("properties", {}).values():
        total += _visibles_a_la_vez(hijo, defs, (*visto, ref))
    items = nodo.get("items")
    if isinstance(items, dict):
        total += _visibles_a_la_vez(items, defs, (*visto, ref))
    return total


def _secciones() -> dict[str, dict[str, Any]]:
    schema, _defs = _schema()
    return {
        nombre: hijo
        for nombre, hijo in schema.get("properties", {}).items()
        if nombre in ESENCIALES_POR_SECCION
    }


def test_el_golden_cubre_las_catorce_secciones() -> None:
    """Las doce del scorecard y las dos de cálculo de IFRS 9: survival y provisioning_ifrs9."""
    assert len(ESENCIALES_POR_SECCION) == 14
    assert set(_secciones()) == set(ESENCIALES_POR_SECCION)
    # 37 caminos del scorecard (39 marcas: un camino de la partición vive en varias ramas) y 17
    # de IFRS 9 (12 hasta CASO-REAL-IFRS9 §8-3; 15 hasta IFRS9-FIRMABLE §8-5).
    assert sum(len(caminos) for caminos in ESENCIALES_POR_SECCION.values()) == 54


def test_cada_marca_del_schema_esta_en_el_golden_y_cada_entrada_del_golden_esta_marcada() -> None:
    """Bidireccional: ni marcas sin declarar ni entradas sin marca (SDD-31 §11)."""
    _, defs = _schema()
    for seccion, nodo in _secciones().items():
        marcadas = _marcas(nodo, defs, seccion, ())
        esperadas = set(ESENCIALES_POR_SECCION[seccion])
        assert marcadas == esperadas, (
            f"{seccion}: marcas sin golden {sorted(marcadas - esperadas)}; "
            f"golden sin marca {sorted(esperadas - marcadas)}"
        )


def test_ninguna_seccion_muestra_mas_de_seis_esenciales_a_la_vez() -> None:
    """Salvo ``provisioning_ifrs9``, con doce: la excepción vale para ella y para ninguna otra."""
    _, defs = _schema()
    for seccion, nodo in _secciones().items():
        visibles = _visibles_a_la_vez(nodo, defs, ())
        assert visibles == ESENCIALES_VISIBLES_A_LA_VEZ[seccion], (seccion, visibles)
        tope = EXCEPCION_AL_TOPE.get(seccion, TOPE_ESENCIALES_POR_SECCION)
        assert visibles <= tope, (seccion, visibles)
    assert set(EXCEPCION_AL_TOPE) == {"provisioning_ifrs9"}


def test_la_marca_no_es_una_hoja_del_config() -> None:
    """``ui_essential`` es metadato: no aparece como campo de ningún modelo (D-FLU-12)."""
    from bayesrisk.core.config.schema import BayesRiskConfig

    assert "ui_essential" not in BayesRiskConfig.model_fields
    schema, _ = _schema()
    assert "ui_essential" not in schema.get("properties", {})


# ──────────── capa B (D-FLU-8): la marca de sección y el espejo del front ────────────

_ESSENTIALS_TS: Final = (
    Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "essentials.ts"
)


def _rama_de_seccion(nodo: Any, defs: dict[str, Any]) -> dict[str, Any]:
    """La rama con campos de una sección de primer nivel, como la resuelve el formulario."""
    for rama in _ramas(_resolver(nodo, defs), defs):
        return rama
    return _resolver(nodo, defs)


def test_las_catorce_secciones_declaran_sus_esenciales_y_ninguna_otra() -> None:
    """``ui_essentials_declared`` (``declara_esenciales``) va en las catorce y en ninguna más.

    Es la marca que hace que la pantalla divida la sección (D-FLU-8): sin ella se pinta entera.
    No se deduce contando marcas porque ``eda`` declara cero esenciales y también se divide.
    """
    schema, defs = _schema()
    declaradas = {
        nombre
        for nombre, nodo in schema.get("properties", {}).items()
        if _rama_de_seccion(nodo, defs).get("ui_essentials_declared") is True
    }
    assert declaradas == set(ESENCIALES_POR_SECCION), (
        f"sin golden: {sorted(declaradas - set(ESENCIALES_POR_SECCION))}; "
        f"sin marca: {sorted(set(ESENCIALES_POR_SECCION) - declaradas)}"
    )


def _golden_del_front() -> dict[str, tuple[str, ...]]:
    """Lee ``ESSENTIALS_BY_SECTION`` de ``web/src/lib/essentials.ts`` sin ejecutar el bundle."""
    texto = _ESSENTIALS_TS.read_text(encoding="utf-8")
    cuerpo = re.search(
        r"^export const ESSENTIALS_BY_SECTION: Record<string, readonly string\[\]> = \{\n(.*?)^\}",
        texto,
        re.S | re.M,
    )
    assert cuerpo is not None, "essentials.ts no declara `ESSENTIALS_BY_SECTION`"
    golden: dict[str, tuple[str, ...]] = {}
    for seccion, lista in re.findall(r"^  (\w+): \[(.*?)\],?$", cuerpo.group(1), re.S | re.M):
        golden[seccion] = tuple(re.findall(r'"([^"]+)"', lista))
    assert golden, "ESSENTIALS_BY_SECTION quedó sin entradas legibles"
    return golden


def test_el_front_espeja_el_golden_de_esenciales_en_los_dos_sentidos() -> None:
    """El golden del front (`essentials.ts`) es el mismo que éste, sección a sección.

    Una marca que se añada o se quite mueve los dos goldens en el mismo commit, o este gate lo
    dice (molde ``MODEL_CARD_NO_PINTADO``: dos fuentes con un solo gate).
    """
    front = _golden_del_front()
    assert set(front) == set(ESENCIALES_POR_SECCION), sorted(
        set(front) ^ set(ESENCIALES_POR_SECCION)
    )
    for seccion, caminos in ESENCIALES_POR_SECCION.items():
        assert sorted(front[seccion]) == sorted(caminos), seccion


def test_el_gate_del_espejo_caza_lo_que_promete() -> None:
    """Control negativo permanente del lector del golden TS: un camino de más o de menos se ve."""
    front = _golden_del_front()
    alterado = {**front, "eda": ("eda.univariate.columns",)}
    assert alterado != dict(ESENCIALES_POR_SECCION)
    sin_uno = {**front, "report": tuple(front["report"][:-1])}
    assert sorted(sin_uno["report"]) != sorted(ESENCIALES_POR_SECCION["report"])
