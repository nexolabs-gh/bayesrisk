"""El resumen comparable (SDD-34 §6.1, D-CMP-2): la huella del modelo, la receta y la lectura.

- El gate de la huella computacional: cada campo del manifiesto de la tarjeta está clasificado
  —entra o sale—, en los dos sentidos contra las claves que ``FittedScorecardBundle`` exige.
- La receta del PSI común es la de fábrica de ``stability``.
- La proyección: la procedencia (lineage, ancla, monitoreo, nombre de la columna) no mueve la
  huella; lo que puntúa, sí.
- La forma del resumen y dónde se busca en una carpeta.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bayesrisk.calibration.results import CalibrationParameters
from bayesrisk.comparison import comparable
from bayesrisk.comparison.exceptions import ComparisonDataError
from bayesrisk.scorecard import bundle as bundle_mod
from bayesrisk.stability.config import StabilityConfig

# ── el gate de la clasificación, en los dos sentidos ─────────────────────────────────────────


def test_cada_clave_del_manifiesto_esta_clasificada_y_nada_sobra() -> None:
    opcionales = {"unseen_reference", "master_scale", "monitoring_reference"}
    assert set(comparable.CAMPOS_DEL_MANIFIESTO) == set(bundle_mod._MANIFEST_KEYS) | opcionales


def test_cada_clave_del_modelo_esta_clasificada_y_nada_sobra() -> None:
    assert set(comparable.CAMPOS_DEL_MODELO) == set(bundle_mod._MODEL_KEYS) | {"clip"}


def test_cada_campo_de_la_calibracion_esta_clasificado_y_nada_sobra() -> None:
    assert set(comparable.CAMPOS_DE_LA_CALIBRACION) == set(CalibrationParameters.model_fields)


def test_cada_clave_de_la_escala_esta_clasificada_y_nada_sobra() -> None:
    assert set(comparable.CAMPOS_DE_LA_ESCALA) == set(bundle_mod._MASTER_SCALE_KEYS)


def test_la_procedencia_sale_y_lo_que_puntua_entra() -> None:
    """Lo que la pasada 2 de Codex encontró en la calibración, y lo que ya era procedencia."""
    s, e = comparable.SALE, comparable.ENTRA
    assert comparable.CAMPOS_DE_LA_CALIBRACION["anchor_source"] == s
    assert comparable.CAMPOS_DEL_MANIFIESTO["fit_lineage"] == s
    assert comparable.CAMPOS_DEL_MANIFIESTO["bundle_hash"] == s
    assert comparable.CAMPOS_DEL_MANIFIESTO["monitoring_reference"] == s
    assert comparable.CAMPOS_DEL_MANIFIESTO["row_identity"] == s
    assert comparable.CAMPOS_DEL_MANIFIESTO["rules_sha256"] == e
    assert comparable.CAMPOS_DEL_MODELO["beta"] == e
    assert comparable.CAMPOS_DE_LA_CALIBRACION["offset"] == e


# ── la receta común ──────────────────────────────────────────────────────────────────────────


def test_la_receta_comun_es_la_de_fabrica_de_stability() -> None:
    fabrica = StabilityConfig()
    assert {
        "bins": fabrica.psi_bins,
        "smoothing": fabrica.smoothing,
        "thresholds": [fabrica.psi_stable_threshold, fabrica.psi_review_threshold],
    } == comparable.RECETA_PSI_DE_FABRICA


# ── la huella computacional ──────────────────────────────────────────────────────────────────


def _manifiesto() -> dict[str, Any]:
    calibracion = {nombre: None for nombre in CalibrationParameters.model_fields}
    calibracion.update(
        method="intercept_offset",
        offset=-0.01,
        anchor_source="development_observed",
        anchor_kind="through_the_cycle",
        target_pd=0.2,
        isotonic_knots=[],
    )
    return {
        "schema_version": 4,
        "format": "nikodym.scorecard.bundle",
        "input_schema": {"columns": [{"name": "x", "dtype": "float"}]},
        "row_identity": {"index_name": "loan_id"},
        "treatment_policy": {"missing": "frozen_bin_or_not_scorable"},
        "special_catalog": {},
        "model": {
            "features": ["x"],
            "woe_columns": ["x__woe"],
            "intercept": -1.2,
            "beta": {"x": -1.05},
            "score_column": "score",
            "score_direction": "higher_is_lower_risk",
            "rounding_method": "nearest_integer",
            "min_score": None,
            "max_score": None,
            "clip": False,
            "calibration": calibracion,
        },
        "fit_lineage": {"config_hash": "a" * 64},
        "rules_sha256": "b" * 64,
        "files": {},
        "bundle_hash": "c" * 64,
        "unseen_reference": {},
        "master_scale": {
            "cuts": [500.0],
            "grade_pd": [0.1, 0.3],
            "approval_cutoff": None,
            "source": "formed",
        },
        "monitoring_reference": {"n_development": 100},
    }


@pytest.mark.parametrize(
    "ruta",
    [
        ("fit_lineage", "config_hash"),
        ("bundle_hash",),
        ("files",),
        ("monitoring_reference", "n_development"),
        ("row_identity", "index_name"),
        ("schema_version",),
        ("model", "score_column"),
        ("model", "calibration", "anchor_source"),
        ("model", "calibration", "target_pd"),
        ("master_scale", "source"),
    ],
)
def test_la_procedencia_no_mueve_la_huella_del_modelo(ruta: tuple[str, ...]) -> None:
    """El mismo modelo con otro config, otra corrida u otra fuente del ancla (pasadas 1 y 2)."""
    base = _manifiesto()
    otro = copy.deepcopy(base)
    nodo = otro
    for clave in ruta[:-1]:
        nodo = nodo[clave]
    nodo[ruta[-1]] = "otra procedencia"
    assert comparable.huella_computacional(otro) == comparable.huella_computacional(base)


@pytest.mark.parametrize(
    "ruta",
    [
        ("model", "beta", "x"),
        ("model", "intercept"),
        ("model", "calibration", "offset"),
        ("rules_sha256",),
        ("master_scale", "cuts"),
        ("treatment_policy", "missing"),
    ],
)
def test_lo_que_puntua_mueve_la_huella_del_modelo(ruta: tuple[str, ...]) -> None:
    base = _manifiesto()
    otro = copy.deepcopy(base)
    nodo = otro
    for clave in ruta[:-1]:
        nodo = nodo[clave]
    nodo[ruta[-1]] = "otro valor"
    assert comparable.huella_computacional(otro) != comparable.huella_computacional(base)


def test_un_campo_nuevo_de_la_tarjeta_no_entra_ni_sale_sin_decision() -> None:
    manifiesto = _manifiesto()
    manifiesto["campo_nuevo"] = 1
    with pytest.raises(ValueError, match="campo_nuevo"):
        comparable.huella_computacional(manifiesto)
    manifiesto = _manifiesto()
    manifiesto["model"]["calibration"]["parametro_nuevo"] = 1
    with pytest.raises(ValueError, match="parametro_nuevo"):
        comparable.huella_computacional(manifiesto)


# ── la huella del resumen y su forma ─────────────────────────────────────────────────────────


def _resumen_minimo() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "bayesrisk": "2.15.0",
        "family": "ifrs9",
        "name": "f4",
        "created_at": "2026-10-14T00:00:00+00:00",
        "config_hash": "h",
        "data_hash": "d",
        "portfolio_hash": "d",
        "currency": None,
        "missing": {},
        "as_of": "2025-06-30",
        "scenarios": [{"name": "base", "weight": 1.0}],
        "amount_columns": {"exposure": "ead", "balance": "drawn", "limit": "credit_limit"},
        "by_stage": [{"stage": 1, "n": 1, "exposure": 1.0, "ecl": 0.1, "coverage": 0.1}],
        "total": {"n": 1, "exposure": 1.0, "ecl": 0.1, "coverage": 0.1},
    }


def test_la_huella_del_resumen_no_depende_del_formato_del_archivo() -> None:
    resumen = _resumen_minimo()
    reformateado = json.loads(json.dumps(resumen, indent=4))
    assert comparable.huella(reformateado) == comparable.huella(resumen)
    alterado = copy.deepcopy(resumen)
    alterado["total"]["ecl"] = 0.2
    assert comparable.huella(alterado) != comparable.huella(resumen)


def test_validar_la_forma_no_transforma_valores_ni_huellas() -> None:
    resumen = _resumen_minimo()
    resumen["total"]["ecl"] = 1  # Es número JSON válido; el lector no lo convierte en 1.0.
    original = comparable.bytes_canonicos(resumen)
    assert comparable.validar(resumen) is resumen
    assert comparable.bytes_canonicos(resumen) == original


def test_un_resumen_de_otro_esquema_o_incompleto_se_rechaza() -> None:
    resumen = _resumen_minimo()
    with pytest.raises(ComparisonDataError, match="esquema"):
        comparable.validar({**resumen, "schema_version": 2})
    with pytest.raises(ComparisonDataError, match="familia"):
        comparable.validar({**resumen, "family": "monitoreo"})
    sin = dict(resumen)
    del sin["by_stage"]
    with pytest.raises(ComparisonDataError, match="faltan"):
        comparable.validar(sin)


@pytest.mark.parametrize("donde", ["archivo", "run_dir", "proyecto"])
def test_se_lee_desde_el_archivo_la_corrida_o_el_proyecto(tmp_path: Path, donde: str) -> None:
    resumen = _resumen_minimo()
    corrida = tmp_path / "proyecto" / "run"
    corrida.mkdir(parents=True)
    archivo = comparable.escribir(resumen, corrida)
    ruta = {"archivo": archivo, "run_dir": corrida, "proyecto": tmp_path / "proyecto"}[donde]
    leido, origen = comparable.leer(ruta)
    assert leido == resumen
    assert origen == archivo


def test_una_corrida_sin_resumen_dice_como_obtenerlo(tmp_path: Path) -> None:
    vieja = tmp_path / "vieja"
    (vieja / "study").mkdir(parents=True)
    with pytest.raises(ComparisonDataError, match=r"anterior a la 2\.15\.0.*Study\.load"):
        comparable.leer(vieja)
    with pytest.raises(ComparisonDataError, match="no existe"):
        comparable.leer(tmp_path / "nada")
