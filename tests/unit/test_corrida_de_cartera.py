"""Una corrida de cartera no declara target ni partición (D-ECL-2; FLUJO-GUIADO-IFRS9 §3.3).

La provisión IFRS 9 no lee la definición de «malo» ni las muestras Desarrollo/Holdout/OOT: medido
en S28, con target y partición cualesquiera la ECL sale bit a bit igual. Pero ``DataConfig`` los
exigía, y no había forma de declarar «sin muestras». Desde D-ECL-2 las dos claves siguen siendo
obligatorias —olvidarlas sigue siendo un error— y aceptan ``null`` explícito, los dos a la vez o
ninguno; el motor no siembra un criterio institucional para llenar el hueco (D-OBL-5).

Los tests nacen rojos sobre ``fd0e75c`` (``DataConfig`` rechazaba ``null``) salvo los que fijan lo
que NO debe cambiar: el ``config_hash`` y las columnas producidas de F1 y F4.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

import bayesrisk
from bayesrisk.core.config import BayesRiskConfig, config_hash
from bayesrisk.core.dataset_check import check_dataset, columnas_producidas_por_seccion
from bayesrisk.data.config import SECCIONES_QUE_MODELAN_EL_INCUMPLIMIENTO, DataConfig
from bayesrisk.data.step import DataStep
from bayesrisk.governance.config import GovernanceConfig
from bayesrisk.guided.summaries import (
    SummaryContext,
    build_stage_summary,
    partition_label_from_config,
)
from bayesrisk.ui import datasets
from bayesrisk.ui.presets import ifrs9_preset, standard_preset
from bayesrisk.ui.serializers import serialize_study

_RAIZ = Path(__file__).resolve().parents[2]
_HASH_F1 = "1063d6cfef0448c502b5f63c7e1f9f5b7ef234b0663b2d02a7527c52652c8633"
_HASH_F4 = "f688fce704ad36414a7c4e5f4e7c10e9455c9d50a0802b3f3ec90bb97ff4b9c7"
_PRODUCIDAS_CON_TARGET = frozenset({"target", "label_status", "partition", "ttd"})


def _cartera(cfg: dict[str, Any]) -> dict[str, Any]:
    """El mismo config con target y partición en ``null`` explícito."""
    out = deepcopy(cfg)
    out["data"]["target"] = None
    out["data"]["partition"] = None
    return out


def _data(cfg: dict[str, Any]) -> DataConfig:
    return DataConfig.model_validate(cfg["data"])


# ─────────────────────────── el contrato de la sección ───────────────────────────


def test_target_y_particion_aceptan_null_explicito() -> None:
    data = _data(_cartera(ifrs9_preset()["config"]))

    assert data.target is None
    assert data.partition is None
    assert data.es_corrida_de_cartera


@pytest.mark.parametrize("clave", ["target", "partition"])
def test_la_clave_sigue_siendo_obligatoria(clave: str) -> None:
    """Olvidar la clave sigue siendo un error: ``null`` es una declaración, la ausencia no."""
    seccion = _cartera(ifrs9_preset()["config"])["data"]
    del seccion[clave]

    with pytest.raises(ValidationError, match=clave):
        DataConfig.model_validate(seccion)


@pytest.mark.parametrize("anulada", ["target", "partition"])
def test_target_y_particion_van_juntos(anulada: str) -> None:
    seccion = deepcopy(ifrs9_preset()["config"]["data"])
    seccion[anulada] = None

    with pytest.raises(ValidationError, match="van juntas"):
        DataConfig.model_validate(seccion)


def test_los_config_hash_de_f1_y_f4_no_se_mueven() -> None:
    """Todo YAML vigente declara las dos claves con valor: ningún hash existente cambia."""
    assert config_hash(BayesRiskConfig.model_validate(standard_preset()["config"])) == _HASH_F1
    assert config_hash(BayesRiskConfig.model_validate(ifrs9_preset()["config"])) == _HASH_F4


def test_provides_depende_del_config() -> None:
    """Patrón de ``SurvivalStep.requires``: el DAG sólo ve lo que el paso anuncia."""
    con_target = DataStep.from_config(_data(ifrs9_preset()["config"]))
    cartera = DataStep.from_config(_data(_cartera(ifrs9_preset()["config"])))

    assert {clave for _, clave in con_target.provides} == {
        "frame",
        "splits",
        "labels",
        "special",
        "data_hash",
        "data_card",
    }
    assert {clave for _, clave in cartera.provides} == {
        "frame",
        "special",
        "data_hash",
        "data_card",
    }


def test_columnas_que_produce_vacia_en_una_corrida_de_cartera() -> None:
    assert _data(_cartera(ifrs9_preset()["config"])).columnas_que_produce() == frozenset()
    assert _data(ifrs9_preset()["config"]).columnas_que_produce() == _PRODUCIDAS_CON_TARGET
    assert _data(standard_preset()["config"]).columnas_que_produce() == _PRODUCIDAS_CON_TARGET


def test_columnas_producidas_por_seccion_de_f1_y_f4_intactas() -> None:
    """Medido sobre ``fd0e75c``: toda sección salvo ``data`` puede nombrar las cuatro columnas."""
    for preset in (standard_preset(), ifrs9_preset()):
        producidas = columnas_producidas_por_seccion(
            BayesRiskConfig.model_validate(preset["config"])
        )
        assert producidas["data"] == ()
        assert {
            seccion: frozenset(columnas)
            for seccion, columnas in producidas.items()
            if seccion != "data"
        } == dict.fromkeys(set(producidas) - {"data"}, _PRODUCIDAS_CON_TARGET)


# ─────────────────────────── el requisito por contexto y el DAG ───────────────────────────


def _cartera_con_binning() -> BayesRiskConfig:
    """F1 con target y partición nulos: ``binning`` y compañía no tienen qué modelar."""
    return BayesRiskConfig.model_validate(_cartera(standard_preset()["config"]))


def test_una_etapa_que_modela_se_detiene_antes_de_correr_con_el_mensaje_de_negocio() -> None:
    """El DAG la detiene y lo dice en palabras de negocio, no «active 'data'», que ya lo está."""
    veredicto = bayesrisk.check_pipeline(_cartera_con_binning())

    assert not veredicto.executable
    assert veredicto.message is not None
    assert "qué es un cliente malo" in veredicto.message
    assert "active 'data'" not in veredicto.message


def test_el_requisito_por_contexto_ancla_al_target() -> None:
    """El formulario lo ve antes de apretar Ejecutar, anclado al campo que lo arregla."""
    cfg = _cartera_con_binning()
    resultado = check_dataset(cfg, list(_columnas_del_dataset(standard_preset())))

    rutas = [m.path for m in resultado.mismatches if m.kind == "unmet_requirement"]
    assert "data.target" in rutas


def test_una_corrida_de_cartera_no_tiene_requisito_de_target() -> None:
    cfg = BayesRiskConfig.model_validate(_cartera(ifrs9_preset()["config"]))
    resultado = check_dataset(cfg, list(_columnas_del_dataset(ifrs9_preset())))

    assert [m for m in resultado.mismatches if m.path == "data.target"] == []
    assert columnas_producidas_por_seccion(cfg)["survival"] == ()


def _columnas_del_dataset(preset: dict[str, Any]) -> tuple[str, ...]:
    catalogo = {d["id"]: d for d in datasets.list_datasets()}
    return tuple(c["name"] for c in catalogo[preset["dataset_id"]]["columns"])


_REQUIRES_DE_ETIQUETAS = re.compile(
    r"\(\s*(?:\"data\"|_DATA_DOMAIN)\s*,\s*\"(?:labels|splits)\"\s*\)"
)


def test_la_lista_de_etapas_que_modelan_es_la_del_dag() -> None:
    """La lista del requisito y el ``requires`` real de cada paso no se separan en silencio.

    Bidireccional: un paso que declara las etiquetas o las muestras en su ``requires`` está en la
    lista, y uno de la lista las declara. ``provisioning_cmf`` las lee sólo con el mapeo por cortes
    de PD y no por ``requires`` (su propio error lo dice); no entra.
    """
    declaran = {
        ruta.parent.name
        for ruta in (_RAIZ / "src" / "bayesrisk").glob("*/step.py")
        if ruta.parent.name != "data"
        and _REQUIRES_DE_ETIQUETAS.search(ruta.read_text(encoding="utf-8"))
    }

    assert declaran == set(SECCIONES_QUE_MODELAN_EL_INCUMPLIMIENTO)


# ─────────────────────────── la corrida de punta a punta ───────────────────────────


def test_corrida_de_cartera_bit_a_bit_igual_a_f4_en_la_provision(tmp_path: Path) -> None:
    """La provisión no lee target ni partición: sin ellos, la misma cifra (D-ECL-2, §6-2)."""
    preset = ifrs9_preset()
    source = datasets.materialize(preset["dataset_id"], workdir=tmp_path)
    base = deepcopy(preset["config"])
    base["data"]["load"]["source"] = str(source)
    base["report"] = None

    f4 = bayesrisk.run(BayesRiskConfig.model_validate(base), run_dir=tmp_path / "f4")
    con_informe = _cartera(base)
    con_informe["report"] = {
        **deepcopy(preset["config"]["report"]),
        "output_dir": str(tmp_path / "informe"),
        "formats": ["md"],
    }
    cartera = bayesrisk.run(
        BayesRiskConfig.model_validate(con_informe), run_dir=tmp_path / "cartera"
    )

    assert f4.run_context.status == "done"
    assert cartera.run_context.status == "done", cartera.run_context.error
    for clave in ("summary", "detail", "ecl_term_structure", "staging"):
        pd.testing.assert_frame_equal(
            f4.artifacts.get("provisioning_ifrs9", clave),
            cartera.artifacts.get("provisioning_ifrs9", clave),
            check_exact=True,
        )
    # La curva es la misma; sólo la etiqueta `partition` que arrastra por fila queda vacía.
    curva_f4 = f4.artifacts.get("survival", "term_structure")
    curva = cartera.artifacts.get("survival", "term_structure")
    assert curva["partition"].isna().all()
    pd.testing.assert_frame_equal(
        curva_f4.drop(columns=["partition"]), curva.drop(columns=["partition"]), check_exact=True
    )
    assert not cartera.artifacts.has("data", "labels")
    assert not cartera.artifacts.has("data", "splits")
    card = cartera.artifacts.get("data", "data_card")
    assert card.target_col is None
    assert card.bad_rate is None
    assert card.class_counts == card.partition_sizes == card.partition_bad_rates == {}
    assert card.n_rows == f4.artifacts.get("data", "data_card").n_rows

    # El informe y el resumen dicen «no aplica»; no cuentan cero malos ni muestras vacías.
    informes = sorted((tmp_path / "informe").rglob("*.html"))
    assert informes, "la corrida de cartera no escribió el informe HTML"
    html = informes[0].read_text(encoding="utf-8")
    assert "Es una corrida de cartera" in html
    assert "Estados de la población" not in html
    assert "Particiones de modelamiento" not in html
    assert "Las tablas siguientes reproducen" not in html
    contexto = SummaryContext(
        project_dir=None,
        run_dir=None,
        source_label="cartera",
        partition_label=partition_label_from_config(cartera.config),
    )
    assert contexto.partition_label == ""
    resumen = build_stage_summary("data", cartera, contexto)
    assert not any("malos" in linea or "Muestras" in linea for linea in resumen.lines)
    # Desde la capa A (S30) la corrida de cartera habla con la familia IFRS 9: «Cartera».
    assert resumen.label == "Cartera"
    assert any("6.000 operaciones" in linea for linea in resumen.lines)

    # El serializer de resultados de la pantalla publica la ficha, con la card de datos en `null`.
    serializado = serialize_study(
        cartera, governance=GovernanceConfig(purpose="Provisión IFRS 9 de la cartera")
    )
    datos = serializado["model_card"]["data_description"]
    assert datos["target_col"] is None
    assert datos["bad_rate"] is None


def test_api_validate_acepta_la_corrida_de_cartera() -> None:
    """``/api/validate`` responde sin error de atributo; antes era un 500 (censo de S29)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from _ui_client import ui_client

    cfg = BayesRiskConfig.model_validate(_cartera(ifrs9_preset()["config"]))
    respuesta = ui_client().post(
        "/api/validate", json={"config": cfg.model_dump(mode="json", by_alias=True)}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["valid"] is True
    assert cuerpo["errors"] == []
    assert cuerpo["config_hash"] == config_hash(cfg)
    assert cuerpo["produced_columns_by_section"]["survival"] == []
