"""Los 12 meses del Stage 1 en blanco se infieren de la unidad de la curva (IFRS9 §3.12).

Pasada 1 de Codex sobre la capa B, con OK de Cami del 2026-10-05: el trabajo «Provisiones IFRS 9»
de la pantalla pregunta la unidad y el horizonte de la curva, pero los 12 meses quedaban en el 12
de fábrica, plegados en «Avanzado»: con una curva anual la corrida se detenía con
``FALTA-DATO-IFRS-8``. ``bayesrisk.Ecl`` los infiere de la unidad; ahora el motor también, cuando el
campo viene en blanco (``null``), con la misma regla y una sola función
(:func:`~bayesrisk.provisioning.ifrs9.engine.effective_horizon_12m`).

Es aditivo: un número declarado se usa tal cual y la corrida registra exactamente lo de antes.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import bayesrisk
from bayesrisk.core.config import BayesRiskConfig, config_hash
from bayesrisk.provisioning.ifrs9.engine import effective_horizon_12m
from bayesrisk.provisioning.ifrs9.exceptions import IfrsConfigError
from bayesrisk.ui.datasets import materialize
from bayesrisk.ui.jobs import list_jobs
from bayesrisk.ui.presets import ifrs9_preset

pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")


def _curva(*unidades: str | None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": [str(i) for i in range(len(unidades))],
            "period": [1] * len(unidades),
            "time_value": [1.0] * len(unidades),
            "pd_marginal": [0.01] * len(unidades),
            "time_unit": list(unidades),
        }
    )


@pytest.mark.parametrize(
    ("unidad", "periodos"),
    [("year", 1), ("años", 1), ("semester", 2), ("quarter", 4), ("meses", 12), ("week", 52)],
)
def test_en_blanco_se_infiere_de_la_unidad_con_la_regla_de_la_puerta(
    unidad: str, periodos: int
) -> None:
    assert effective_horizon_12m(None, _curva(unidad, unidad)) == periodos


def test_declarado_se_usa_tal_cual_aunque_la_curva_no_tenga_unidad() -> None:
    assert effective_horizon_12m(12, _curva(None)) == 12
    assert effective_horizon_12m(1, _curva("month")) == 1


@pytest.mark.parametrize(
    "unidades",
    [("year", "month"), ("year", None), ("period",), ("quincena",)],
    ids=["mezcla", "una-fila-sin-unidad", "indice", "no-reconocida"],
)
def test_sin_una_sola_unidad_reconocida_se_detiene_y_dice_el_arreglo(
    unidades: tuple[str | None, ...],
) -> None:
    with pytest.raises(IfrsConfigError, match="declara la unidad de su duración"):
        effective_horizon_12m(None, _curva(*unidades))


def test_sin_columna_de_unidad_tampoco_infiere() -> None:
    with pytest.raises(IfrsConfigError, match="Períodos que cubren 12 meses"):
        effective_horizon_12m(None, _curva("year").drop(columns=["time_unit"]))


# ───────────────────────────── corridas reales ─────────────────────────────


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def datos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))


def _f4(datos: Path, **pd_ifrs9: Any) -> dict[str, Any]:
    cfg = copy.deepcopy(ifrs9_preset()["config"])
    cfg["data"]["load"]["source"] = str(datos)
    cfg["report"] = None
    cfg["provisioning_ifrs9"]["pd"].update(pd_ifrs9)
    return cfg


def _correr(cfg: dict[str, Any], run_dir: Path) -> Any:
    return bayesrisk.run(BayesRiskConfig.model_validate(cfg), run_dir=run_dir)


def _decision_del_horizonte(run_dir: Path) -> dict[str, Any]:
    trail = (run_dir / "audit_trail.jsonl").read_text(encoding="utf-8").splitlines()
    for linea in trail:
        evento = json.loads(linea)
        carga = evento.get("payload") or {}
        if evento.get("kind") == "decision" and carga.get("regla") == "ifrs9_pd_horizon":
            return dict(carga)
    raise AssertionError("la corrida no registró ifrs9_pd_horizon")


def test_f4_en_blanco_es_bit_a_bit_f4_y_lo_declara(
    datos: Path, tmp_path: Path, _semilla: None
) -> None:
    """El preset F4 (curva anual, 12 meses = 1) con el campo en blanco calcula LO MISMO."""
    declarado = _correr(_f4(datos), tmp_path / "declarado")
    inferido = _correr(_f4(datos, horizon_12m_periods=None), tmp_path / "inferido")
    assert declarado.run_context.status == "done", declarado.run_context.error
    assert inferido.run_context.status == "done", inferido.run_context.error
    for clave in ("summary", "detail", "staging", "ecl_term_structure"):
        pd.testing.assert_frame_equal(
            inferido.artifacts.get("provisioning_ifrs9", clave),
            declarado.artifacts.get("provisioning_ifrs9", clave),
            check_exact=True,
        )
    # Lo dice el registro de auditoría, y sólo cuando infirió: lo declarado registra lo de antes.
    assert _decision_del_horizonte(tmp_path / "inferido")["valor"]["horizon_12m_inferido"] == 1
    assert "horizon_12m_inferido" not in _decision_del_horizonte(tmp_path / "declarado")["valor"]
    # Declararlo en blanco es OTRO config: su identidad cambia, y la del número declarado no (los
    # hashes de los presets publicados los fija su propio golden).
    assert config_hash(BayesRiskConfig.model_validate(_f4(datos))) != config_hash(
        BayesRiskConfig.model_validate(_f4(datos, horizon_12m_periods=None))
    )


def test_el_trabajo_de_la_pantalla_con_curva_anual_llega_a_la_provision(
    datos: Path, tmp_path: Path, _semilla: None
) -> None:
    """El flujo de la pantalla: lo que el trabajo siembra, más lo que pregunta, corre entero.

    Contracara: con el 12 de fábrica —lo que sembraba antes— la misma corrida se detiene con
    ``FALTA-DATO-IFRS-8`` (el caso de §1.4 de la enmienda).
    """
    job = next(j for j in list_jobs(incluir_referencia=True) if j["id"] == "provisiones_ifrs9")
    sembrados = dict((ruta, valor) for ruta, valor in job["overrides"])
    assert sembrados["provisioning_ifrs9.pd.horizon_12m_periods"] is None
    cfg = _f4(datos, horizon_12m_periods=None)
    cfg["data"]["target"] = sembrados["data.target"]
    cfg["data"]["partition"] = sembrados["data.partition"]
    cfg["survival"]["input"]["pd_source"] = sembrados["survival.input.pd_source"]
    # Las respuestas a las preguntas del trabajo (unidad y horizonte de la curva anual del paquete).
    cfg["survival"]["time_grid"].update({"time_unit": "year", "horizon_periods": 5})
    study = _correr(cfg, tmp_path / "pantalla")
    assert study.run_context.status == "done", study.run_context.error
    assert _decision_del_horizonte(tmp_path / "pantalla")["valor"]["horizon_12m_inferido"] == 1
    assert "FALTA-DATO-IFRS-8" not in study.artifacts.get("provisioning_ifrs9", "card").falta_dato

    cfg_viejo = copy.deepcopy(cfg)
    cfg_viejo["provisioning_ifrs9"]["pd"]["horizon_12m_periods"] = 12
    viejo = _correr(cfg_viejo, tmp_path / "fabrica")
    assert viejo.run_context.status == "failed"
    assert "FALTA-DATO-IFRS-8" in str(viejo.run_context.error)


def test_el_resumen_dice_que_lo_infirio(datos: Path, tmp_path: Path, _semilla: None) -> None:
    from bayesrisk.guided.summaries import _supuestos

    study = _correr(_f4(datos, horizon_12m_periods=None), tmp_path / "resumen")
    assert study.run_context.status == "done", study.run_context.error
    supuesto = next(s for s in _supuestos(study) if s.startswith("Los 12 meses del Stage 1"))
    assert supuesto == (
        "Los 12 meses del Stage 1 son el primer período de la curva (1 año), inferido de su unidad"
    )
    declarado = _correr(_f4(datos), tmp_path / "resumen-declarado")
    assert "inferido" not in next(
        s for s in _supuestos(declarado) if s.startswith("Los 12 meses del Stage 1")
    )
