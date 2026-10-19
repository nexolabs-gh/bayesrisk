"""Controles rojos con restauración exacta; sólo copias temporales o estados en memoria."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from .aggregate import verify_metrics
from .artifacts import verify_artifacts, verify_documents, verify_excel
from .contract import SOURCES, dump, sha256, verify_coverage
from .data import load_case, verify_partition, verify_source
from .isolation import FitAudit
from .metrics import measure


def negative_control(name, verify, mutate, restore, fingerprint) -> dict:
    """Un oráculo que no detecta el defecto o no restaura bytes falla el propio control."""
    verify()
    before = fingerprint()
    detected = None
    try:
        mutate()
        try:
            verify()
        except (ValueError, AssertionError, FileNotFoundError) as exc:
            detected = f"{type(exc).__name__}: {exc}"
    finally:
        restore()
    if before != fingerprint():
        raise AssertionError(f"{name}: restauración no exacta")
    if detected is None:
        raise AssertionError(f"{name}: el gate no detectó el defecto")
    verify()
    return {
        "name": name,
        "red": detected,
        "restored_exactly": True,
        "green": True,
        "before_after_sha256": hashlib.sha256(str(before).encode()).hexdigest(),
    }


def _fingerprint(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=lambda x: x.tolist())


def run_controls(prepared: Path, cache: Path, measured: Path, output: Path) -> list[dict]:
    """Ejercita las guardas con las muestras/artefactos reales ya medidos, sin otro fit."""
    reports = []
    rows = json.loads((measured / "results.json").read_text(encoding="utf-8"))
    original_rows = copy.deepcopy(rows)

    def restore_rows():
        rows[:] = copy.deepcopy(original_rows)

    for name, mutation in (
        ("censo falta receta", lambda: rows.pop()),
        ("censo sobra receta", lambda: rows.append(dict(rows[0], case="fantasma"))),
    ):
        reports.append(
            negative_control(
                name,
                lambda: verify_coverage(rows),
                mutation,
                restore_rows,
                lambda: _fingerprint(rows),
            )
        )

    def complete():
        counts = verify_coverage(rows)
        if counts["executed"] != counts["total"]:
            raise ValueError(f"cobertura ejecutada incompleta; denominador={counts['total']}")

    reports.append(
        negative_control(
            "import/timeout conserva fila fallida",
            complete,
            lambda: rows[0].update(status="falló", error="ImportError inyectado"),
            restore_rows,
            lambda: _fingerprint(rows),
        )
    )
    reports.append(
        negative_control(
            "métrica publicada alterada",
            lambda: verify_metrics(measured, rows, prepared),
            lambda: rows[0]["metrics"].update(auc=0.0),
            restore_rows,
            lambda: _fingerprint(rows),
        )
    )
    for case in ("german", "taiwan"):
        original_license = SOURCES[case]["license"]
        source = cache / f"{SOURCES[case]['sha256']}.zip"
        reports.append(
            negative_control(
                f"permiso {case}",
                lambda case=case, source=source: verify_source(case, source),
                lambda case=case: SOURCES[case].update(license="sin permiso"),
                lambda case=case, original_license=original_license: SOURCES[case].update(
                    license=original_license
                ),
                lambda: _fingerprint(SOURCES),
            )
        )
    frame = pd.read_parquet(prepared / "taiwan/source.parquet")
    groups = pd.read_parquet(prepared / "taiwan/groups.parquet").iloc[:, 0]
    test = pd.read_parquet(prepared / "taiwan/evaluation.parquet")
    parts = {"input": frame.index[~frame.index.isin(test.index)], "test": test.index}
    saved_parts = copy.deepcopy(parts)

    def restore_parts():
        parts.clear()
        parts.update(copy.deepcopy(saved_parts))

    reports.append(
        negative_control(
            "ID exterior en train",
            lambda: verify_partition(frame.index, parts, groups),
            lambda: parts.update(
                input=frame.index[frame.index.isin(parts["input"].append(test.index[:1]))]
            ),
            restore_parts,
            lambda: _fingerprint(parts),
        )
    )
    duplicate = next(ids.index for _, ids in groups.groupby(groups) if len(ids) > 1)
    member = duplicate[0]

    def break_group():
        source_name = "test" if member in parts["test"] else "input"
        destination_name = "input" if source_name == "test" else "test"
        parts[source_name] = parts[source_name][parts[source_name] != member]
        parts[destination_name] = frame.index[
            frame.index.isin(parts[destination_name].append(pd.Index([member])))
        ]

    reports.append(
        negative_control(
            "grupo X partido",
            lambda: verify_partition(frame.index, parts, groups),
            break_group,
            restore_parts,
            lambda: _fingerprint(parts),
        )
    )
    dev = frame.loc[original_rows[7]["dev_ids"]]
    audit = FitAudit(dev, "target")
    state = {"x": dev, "y": dev.target}
    reports.append(
        negative_control(
            "fit fuera de Desarrollo",
            lambda: audit.check("control", state["x"], state["y"]),
            lambda: state.update(x=frame.loc[state["x"].index[:-1].append(test.index[:1])]),
            lambda: state.update(x=dev),
            lambda: _fingerprint(state["x"].index),
        )
    )
    reports.append(
        negative_control(
            "labels desalineadas en fit",
            lambda: audit.check("control", dev, state["y"]),
            lambda: state.update(y=1 - dev.target),
            lambda: state.update(y=dev.target),
            lambda: _fingerprint(state["y"].tolist()),
        )
    )
    reports.append(
        negative_control(
            "refit durante apply",
            lambda: audit.check("control", dev, dev.target),
            lambda: setattr(audit, "applying", True),
            lambda: setattr(audit, "applying", False),
            lambda: audit.applying,
        )
    )
    expected = copy.deepcopy(original_rows[11]["isolation"])
    solver_audit = FitAudit(dev, "target")
    solver_audit.events.update(expected["effective_fit_calls"])
    solver_audit.solvers = copy.deepcopy(expected["solvers"])
    reports.append(
        negative_control(
            "solver FEASIBLE no es OPTIMAL",
            solver_audit.verify_solvers,
            lambda: solver_audit.solvers[0].update(status="FEASIBLE"),
            lambda: setattr(solver_audit, "solvers", copy.deepcopy(expected["solvers"])),
            lambda: _fingerprint(solver_audit.solvers),
        )
    )
    y = pd.Series([0, 0, 1, 1], index=[2, 4, 6, 8])
    prediction = {"p": y.astype(float)}

    def perfect():
        measured = measure(y, prediction["p"], y.astype(float))
        if (
            measured["auc"] != 1
            or measured["gini"] != 1
            or measured["brier"] != 0
            or measured["psi"] != 0
        ):
            raise ValueError("caso manual: orientación o fórmula incorrecta")

    for name, changed in (
        ("orientación PD invertida", 1 - y.astype(float)),
        ("índices PD desalineados", y.astype(float).iloc[::-1]),
    ):
        reports.append(
            negative_control(
                name,
                perfect,
                lambda changed=changed: prediction.update(p=changed),
                lambda: prediction.update(p=y.astype(float)),
                lambda: _fingerprint(prediction["p"].to_dict()),
            )
        )
    with tempfile.TemporaryDirectory(prefix="h10-control-") as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise ValueError("temporal fuera de la raíz esperada")
        for case in ("german", "taiwan"):
            target = root / f"{case}.zip"
            original = (cache / f"{SOURCES[case]['sha256']}.zip").read_bytes()
            target.write_bytes(original)
            reports.append(
                negative_control(
                    f"byte fuente {case}",
                    lambda case=case, target=target: verify_source(case, target),
                    lambda target=target, original=original: target.write_bytes(
                        original[:-1] + bytes([original[-1] ^ 1])
                    ),
                    lambda target=target, original=original: target.write_bytes(original),
                    lambda target=target: sha256(target),
                )
            )
        original_reader = pd.read_csv
        orientation = {"inverted": False}

        def changed_reader(*args, **kwargs):
            data = original_reader(*args, **kwargs)
            if orientation["inverted"]:
                data["target"] = 3 - data.target
            return data

        with patch.object(pd, "read_csv", changed_reader):
            reports.append(
                negative_control(
                    "orientación de fuente German",
                    lambda: load_case("german", cache),
                    lambda: orientation.update(inverted=True),
                    lambda: orientation.update(inverted=False),
                    lambda: _fingerprint(orientation),
                )
            )

        from . import runner

        failures = [
            ImportError("dependencia ausente inyectada"),
            TimeoutError("timeout inyectado"),
            ValueError("solver FEASIBLE inyectado"),
        ]
        counter = {"value": 0}

        def failed_fit(*args, **kwargs):
            failure = failures[counter["value"] % len(failures)]
            counter["value"] += 1
            raise failure

        originals = (runner.fit_bayesrisk, runner.fit_reference)
        with (
            patch.object(runner, "fit_bayesrisk", failed_fit),
            patch.object(runner, "fit_reference", failed_fit),
        ):
            failed_rows = runner.run(prepared, root / "forced-failures")
            counts = verify_coverage(failed_rows)
            if counts != {"total": 28, "executed": 0, "failed": 28, "pending": 0}:
                raise AssertionError("el runner omitió un fallo del denominador")
            if not all(
                any(kind in row["error"] for kind in ("ImportError", "TimeoutError", "FEASIBLE"))
                for row in failed_rows
            ):
                raise AssertionError("razón de fallo perdida")
        if originals != (runner.fit_bayesrisk, runner.fit_reference):
            raise AssertionError("funciones originales no restauradas")
        complete()
        reports.append(
            {
                "name": "fallos reales del runner sin omitir denominador",
                "red": counts,
                "errors": [row["error"] for row in failed_rows],
                "restored_exactly": True,
                "green": verify_coverage(rows),
            }
        )
        project = root / "project"
        source_project = measured / "projects/german_fabrica"
        for name in ("reports", "excel"):
            shutil.copytree(source_project / name, project / name)
        expected_path = measured / "german_fabrica_expected.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        report = project / "reports/scorecard_report.html"
        original = report.read_bytes()
        # Cambia el primer encabezado de una tabla identificada, conservando HTML válido.
        marker = b'data-table-key="data.states"'
        at = original.index(marker)
        head, tail = original[:at], original[at:]
        changed = head + tail.replace(b"Observaciones", b"Frontera alterada", 1)
        reports.append(
            negative_control(
                "celda HTML final alterada",
                lambda: verify_artifacts(project, expected),
                lambda: report.write_bytes(changed),
                lambda: report.write_bytes(original),
                lambda: sha256(report),
            )
        )
        word = project / "reports/scorecard_report.docx"
        word_original = word.read_bytes()

        def change_word():
            import io

            from lxml import etree

            buffer = io.BytesIO()
            with (
                zipfile.ZipFile(io.BytesIO(word_original)) as source,
                zipfile.ZipFile(buffer, "w") as result,
            ):
                for member in source.infolist():
                    content = source.read(member.filename)
                    if member.filename == "word/document.xml":
                        document = etree.fromstring(content)
                        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                        cell = document.find("w:body/w:tbl/w:tr/w:tc/w:p/w:r/w:t", ns)
                        if cell is None:
                            raise AssertionError("celda Word de control ausente")
                        cell.text = "Celda alterada"
                        content = etree.tostring(
                            document, xml_declaration=True, encoding="UTF-8", standalone=True
                        )
                    result.writestr(member, content)
            word.write_bytes(buffer.getvalue())

        reports.append(
            negative_control(
                "celda Word final alterada",
                lambda: verify_documents(
                    project / "reports", expected["document_tables"], expected["document"]
                ),
                change_word,
                lambda: word.write_bytes(word_original),
                lambda: sha256(word),
            )
        )
        excel = next((project / "excel").glob("*.xlsx"))
        excel_original = excel.read_bytes()

        def change_excel():
            import openpyxl

            book = openpyxl.load_workbook(excel)
            book.worksheets[0]["A1"] = "Celda alterada"
            book.save(excel)
            book.close()

        reports.append(
            negative_control(
                "celda Excel final alterada",
                lambda: verify_excel(project / "excel", expected["books"]),
                change_excel,
                lambda: excel.write_bytes(excel_original),
                lambda: sha256(excel),
            )
        )
    dump(output, reports)
    return reports
