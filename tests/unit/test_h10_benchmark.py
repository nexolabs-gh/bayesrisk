"""Contrato del descargable H10: fuentes, grupos, métricas y cobertura sin red."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs_site/benchmarks/h10/h10_benchmark"


def _load():
    spec = importlib.util.spec_from_file_location(
        "h10_benchmark", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_descargable_completo_y_censo_bidireccional():
    module = _load()
    module.verify_sources(PACKAGE.parent)


def test_notebook_minimo_es_distinto_del_anexo_y_no_oculta_complejidad():
    minimum = json.loads((PACKAGE.parent / "minimo.ipynb").read_text(encoding="utf-8"))
    annex = json.loads((PACKAGE.parent / "anexo.ipynb").read_text(encoding="utf-8"))
    code = "\n".join("".join(c["source"]) for c in minimum["cells"] if c["cell_type"] == "code")
    useful = [s for s in code.splitlines() if s.strip() and not s.lstrip().startswith("#")]
    assert 0 < len(useful) <= 25
    assert "h10_benchmark" not in code
    assert minimum != annex
    assert "sc.run(" in code and "sc.summary(" in code and "sc.to_yaml(" in code


def test_grupos_no_dependen_de_target_ni_id_y_conectan_entidades():
    _load()
    from h10_benchmark.data import exact_groups, outer_split, verify_partition

    frame = pd.DataFrame({"x": [1, 1, 2, 3, 4, 5, 6, 7], "y": [0, 1] * 4})
    groups = exact_groups(frame[["x"]])
    assert groups.iloc[0] == groups.iloc[1]
    connected = exact_groups(frame[["x"]], pd.Series(["a", "b", "b", "c", "d", "e", "f", "g"]))
    assert connected.iloc[0] == connected.iloc[2]
    train, test = outer_split(frame, groups)
    verify_partition(frame.index, {"input": train.index, "test": test.index}, groups)
    with pytest.raises(ValueError, match=r"solapamiento|grupo"):
        verify_partition(frame.index, {"input": frame.index, "test": test.index}, groups)


def test_metricas_manual_orientacion_y_orden():
    _load()
    from h10_benchmark.metrics import measure

    y = pd.Series([0, 0, 1, 1], index=[3, 5, 7, 9])
    p = y.astype(float)
    good = measure(y, p, p)
    assert good["auc"] == good["gini"] == good["ks"] == 1
    assert good["brier"] == good["psi"] == 0
    bad = measure(y, 1 - p, p)
    assert bad["auc"] == 0 and bad["gini"] == -1
    with pytest.raises(ValueError, match=r"orden|índice"):
        measure(y, p.iloc[::-1], p)
    with pytest.raises(ValueError, match="degenerada"):
        measure(y, p, pd.Series(np.ones(4)))


def test_fuentes_no_aceptan_bytes_o_permiso_cambiados(tmp_path):
    _load()
    from h10_benchmark.data import verify_source

    path = tmp_path / "fuente"
    path.write_bytes(b"defecto")
    with pytest.raises(ValueError, match="huella"):
        verify_source("german", path)
    with pytest.raises(ValueError, match="permiso"):
        verify_source("lc", path)


def _delivery_gate():
    spec = importlib.util.spec_from_file_location(
        "h10_delivery_gate", ROOT / "scripts/check_h10_delivery.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_notebook_decodifica_fragmentos_y_no_admite_codigo_publico(tmp_path):
    gate = _delivery_gate()
    notebook = {"nbformat": 4, "cells": [{"cell_type": "markdown", "source": ["FALTA-", "DATO"]}]}
    (tmp_path / "a.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    with pytest.raises(ValueError, match="código interno"):
        gate.inspect_content(tmp_path)


def test_privacidad_html_decodifica_entidades(tmp_path):
    pytest.importorskip("lxml")
    gate = _delivery_gate()
    (tmp_path / "a.html").write_text("<p>C&#58;&#92;Users&#92;persona</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="personal"):
        gate.inspect_content(tmp_path)


def test_gate_rechaza_miembro_opaco_aunque_se_llame_cache(tmp_path):
    gate = _delivery_gate()
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "a.pyc").write_bytes(b"opaco")
    with pytest.raises(ValueError, match=r"opaco|cache"):
        gate.inspect_content(tmp_path)


def test_word_apaisado_preserva_celdas_y_detecta_regresion_de_layout(tmp_path):
    docx = pytest.importorskip("docx")
    import io
    import zipfile

    from lxml import etree

    _load()
    from h10_benchmark.presentation import layout_word, verify_word_layout

    path = tmp_path / "ancha.docx"
    document = docx.Document()
    document.add_paragraph("Portada")
    document.add_paragraph("Caption")
    table = document.add_table(rows=2, cols=20)
    for i, row in enumerate(table.rows):
        for j, cell in enumerate(row.cells):
            cell.text = f"Valor {i}/{j}"
    document.save(path)
    before = [[cell.text for cell in row.cells] for row in table.rows]
    with pytest.raises(ValueError, match="apaisada"):
        verify_word_layout(path)
    assert layout_word(path) == verify_word_layout(path) == 1
    after = docx.Document(path).tables[0]
    assert [[cell.text for cell in row.cells] for row in after.rows] == before
    original = path.read_bytes()
    assert layout_word(path) == 0 and path.read_bytes() == original
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "word/document.xml":
                tree = etree.fromstring(content)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                wide = tree.xpath(".//w:pgSz[@w:orient='landscape']", namespaces=ns)[0]
                wide.set(f"{{{ns['w']}}}orient", "portrait")
                content = etree.tostring(tree)
            target.writestr(info, content)
    path.write_bytes(buffer.getvalue())
    with pytest.raises(ValueError, match="apaisada"):
        verify_word_layout(path)
    path.write_bytes(original)
    assert verify_word_layout(path) == 1 and path.read_bytes() == original


def test_receta_fallida_permanece_en_denominador():
    _load()
    from h10_benchmark.contract import CASES, RECIPES, verify_coverage

    rows = [
        {"case": c, "recipe": r, "status": "falló", "error": "timeout"}
        for c in CASES
        for r in RECIPES
    ]
    assert verify_coverage(rows)["failed"] == 28
    with pytest.raises(ValueError, match="cobertura"):
        verify_coverage(rows[:-1])
    with pytest.raises(ValueError, match="cobertura"):
        verify_coverage([*rows, {"case": "fantasma", "recipe": "fabrica", "status": "ejecutado"}])


def test_repeticiones_no_ocultan_cambio_de_predicciones():
    _load()
    from h10_benchmark.aggregate import compare_runs

    row = {
        "case": "german",
        "recipe": "fabrica",
        "status": "ejecutado",
        "prediction_sha256": "a",
        "features": ["x"],
        "config_hash": "c",
        "data_hash": "d",
        "metrics": {"auc": 0.5},
    }
    compare_runs([row], [dict(row)])
    with pytest.raises(ValueError, match="reproducibilidad"):
        compare_runs([row], [dict(row, prediction_sha256="b")])


def test_control_negativo_exige_rojo_y_restauracion_exacta():
    _load()
    from h10_benchmark.controls import negative_control

    state = {"value": 1}

    def verify():
        if state["value"] != 1:
            raise ValueError("defecto inyectado")

    report = negative_control(
        "manual",
        verify,
        lambda: state.update(value=2),
        lambda: state.update(value=1),
        lambda: str(state),
    )
    assert report["red"] and report["restored_exactly"] and report["green"]
    with pytest.raises(AssertionError, match="no detectó"):
        negative_control("oráculo ciego", lambda: None, lambda: None, lambda: None, lambda: "a")


def test_preparacion_invalida_conserva_todas_las_recetas(tmp_path, monkeypatch):
    _load()
    from h10_benchmark import runner
    from h10_benchmark.contract import verify_coverage

    def invalid(*args, **kwargs):
        raise ValueError("fuente o partición inválida")

    monkeypatch.setattr(runner, "read_prepared", invalid)
    monkeypatch.setattr(runner, "execution_environment", lambda: {"test": "preflight failure"})
    rows = runner.run(tmp_path / "prepared", tmp_path / "failed")
    assert verify_coverage(rows) == {"total": 28, "executed": 0, "failed": 28, "pending": 0}
    assert all("fuente o partición inválida" in row["error"] for row in rows)


@pytest.mark.parametrize("name", ["../fuera", "/absoluto", "C:/fuera", "a\\b"])
def test_descarga_rechaza_rutas_ambiguas(tmp_path, name):
    import hashlib
    import io
    import tarfile

    _load()
    from h10_benchmark.delivery import inspect_archive

    archive = tmp_path / "h10.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo(name)
        member.size = 1
        tar.addfile(member, io.BytesIO(b"x"))
    envelope = {"archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": {}}
    with pytest.raises(ValueError, match="miembro"):
        inspect_archive(archive, envelope)
