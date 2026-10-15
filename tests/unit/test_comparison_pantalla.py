"""SDD-34 capa B: selección autenticada y comparación sin cargar una cartera."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_comparison_step import _provision, _resumen

from bayesrisk.comparison.comparable import bytes_canonicos


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(settings, runtime=build_test_runtime(settings.workdir)) as c:
        yield c


def _subir(cliente: Any, contenido: bytes, nombre: str = "comparable.json") -> Any:
    return cliente.post(
        "/api/comparables/upload", files={"file": (nombre, contenido, "application/json")}
    )


def test_subida_validada_y_lista_de_corridas_sin_exponer_observaciones(
    cliente: Any, tmp_path: Path
) -> None:
    resumen = _resumen("base")
    subida = _subir(cliente, bytes_canonicos(resumen))
    assert subida.status_code == 200, subida.text
    ficha = subida.json()
    assert ficha["name"] == "base" and ficha["family"] == "scorecard"
    assert "evaluation_scores" not in ficha
    assert json.loads(Path(ficha["path"]).read_text(encoding="utf-8")) == resumen
    repetida = _subir(cliente, json.dumps(resumen, indent=2).encode())
    assert repetida.json()["path"] == ficha["path"]
    corrida = tmp_path / "ui" / "runs" / "previa" / "comparable.json"
    corrida.parent.mkdir(parents=True)
    corrida.write_bytes(bytes_canonicos(_resumen("previa")))
    lista = cliente.post("/api/comparables/list", json={})
    assert lista.status_code == 200
    assert {f["name"] for f in lista.json()["comparables"]} == {"base", "previa"}


@pytest.mark.parametrize("contenido", [b"{}", b"no json", b'{"schema_version": NaN}'])
def test_un_resumen_invalido_no_se_publica(cliente: Any, tmp_path: Path, contenido: bytes) -> None:
    respuesta = _subir(cliente, contenido)
    assert respuesta.status_code == 422, respuesta.text
    assert not list((tmp_path / "ui" / "comparables").glob("*.json"))


def test_listado_y_subida_exigen_credenciales(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(
        settings, runtime=build_test_runtime(settings.workdir), con_credenciales=False
    ) as c:
        assert c.post("/api/comparables/list", json={}).status_code == 403
        assert _subir(c, b"{}").status_code == 403


def test_comparar_por_http_sin_dataset_con_los_mismos_graficos_y_tablas(
    cliente: Any, tmp_path: Path
) -> None:
    pytest.importorskip("matplotlib")
    rutas = [
        _subir(cliente, bytes_canonicos(_resumen(nombre, participacion=[0.4, 0.6]))).json()["path"]
        for nombre in ("base", "alternativa")
    ]
    config = {"name": "comparacion", "comparison": {"runs": rutas}}
    respuesta = cliente.post("/api/run", json={"config": config})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "done"
    resultados = cliente.get(f"/api/results/{respuesta.json()['run_id']}").json()
    etapa = next(e for e in resultados["summaries"]["stages"] if e["stage"] == "comparison")
    assert len(etapa["charts"]) == 2
    assert all("<svg" in g["svg"] for g in etapa["charts"])
    assert etapa["table"]
    assert not (resultados["summaries"]["error"])
    from bayesrisk.guided import Comparison

    comp = Comparison(rutas, name="comparacion", run_dir=tmp_path / "guiada")
    comp._echo = lambda _texto: None
    comp.run()
    resumen = comp.summary("comparison")
    assert etapa["charts"] == [{"title": t, "svg": svg} for t, svg in resumen.charts]
    assert {k: v for k, v in etapa.items() if k != "charts"} == resumen.to_dict()


def test_ifrs9_por_http_compara_las_etapas_sin_graficos(cliente: Any) -> None:
    rutas = [
        _subir(cliente, bytes_canonicos(_provision(nombre, "cartera", [10.0, 20.0, 30.0]))).json()[
            "path"
        ]
        for nombre in ("provision-a", "provision-b")
    ]
    respuesta = cliente.post("/api/run", json={"config": {"comparison": {"runs": rutas}}})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "done"
    resultados = cliente.get(f"/api/results/{respuesta.json()['run_id']}").json()
    etapa = next(e for e in resultados["summaries"]["stages"] if e["stage"] == "comparison")
    assert "charts" not in etapa
    assert any("etapa" in t["title"].lower() for t in etapa["extra_tables"])


def test_subida_respeta_tipo_y_tope_antes_de_publicar(tmp_path: Path) -> None:
    from bayesrisk.ui.comparables import subir
    from bayesrisk.ui.exceptions import UiComparableError

    contenido = bytes_canonicos(_resumen("subida"))
    for nombre, tope, motivo in (
        ("resumen.txt", len(contenido), "archivo .json"),
        ("comparable.json", 1, "tope de subida"),
    ):
        with pytest.raises(UiComparableError, match=motivo):
            subir(contenido, nombre, workdir=tmp_path, max_bytes=tope)
    assert not list(tmp_path.rglob("*.json"))


def test_comparacion_estable_en_las_tres_puertas() -> None:
    from bayesrisk.testing.stability import EXPERIMENTAL_SYMBOLS, STABLE_DOMAINS

    assert "comparison" in STABLE_DOMAINS
    assert "bayesrisk.guided.comparison.Comparison" not in EXPERIMENTAL_SYMBOLS


def test_catalogo_ofrece_comparacion_sin_data(cliente: Any) -> None:
    payload = cliente.get("/api/jobs").json()
    trabajo = next(j for j in payload["jobs"] if j["id"] == "comparar_modelos")
    assert trabajo["sections"] == ["comparison", "report", "governance"]
    assert trabajo["status"] == "available"
