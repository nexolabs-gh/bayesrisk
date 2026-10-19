"""Verifica una descarga y el candidato instalado fuera del checkout, sin imports implícitos."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import socket
import sys
import time
import zipfile
from pathlib import Path


def verify_installed_wheel(wheel: Path, distribution) -> int:
    """Coteja el payload instalado; RECORD se reescribe y los metadatos de uv no dan hashes."""
    expected_package = set()
    count = 0
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = member.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("ruta no admitida en el wheel")
            if name.endswith(".dist-info/RECORD"):
                continue  # El instalador añade direct_url, INSTALLER y sus propios scripts.
            installed = Path(distribution.locate_file(name))
            if not installed.is_file() or installed.read_bytes() != archive.read(member):
                raise ValueError(f"archivo instalado distinto del candidato: {name}")
            count += 1
            if name.startswith("bayesrisk/"):
                expected_package.add(name)
    package = Path(distribution.locate_file("bayesrisk"))
    actual_package = {
        "bayesrisk/" + p.relative_to(package).as_posix()
        for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    if not expected_package or actual_package != expected_package:
        raise ValueError("censo instalado diferente del payload del candidato")
    return count


def main():
    """El recibo de cobertura completa sólo se escribe después de todos sus oráculos."""
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("minimum", "full"))
    parser.add_argument("root", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    root, work = args.root.resolve(), args.work.resolve()
    if work.exists():
        raise ValueError("destino existente")
    work.mkdir(parents=True)
    if root == work or root in work.parents:
        raise ValueError("la evidencia no debe modificar la descarga")
    os.chdir(work)
    # El archivo se copia fuera del checkout junto con el candidato y la descarga.
    sys.path[:] = [entry for entry in sys.path if entry not in ("", str(Path(__file__).parent))]
    import bayesrisk

    origin = Path(bayesrisk.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("bayesrisk no proviene del entorno instalado")
    digest = hashlib.sha256(args.wheel.read_bytes()).hexdigest()
    installed_files = verify_installed_wheel(
        args.wheel, importlib.metadata.distribution("bayesrisk")
    )
    spec = importlib.util.spec_from_file_location(
        "h10_benchmark",
        root / "h10_benchmark/__init__.py",
        submodule_search_locations=[str(root / "h10_benchmark")],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from h10_benchmark.contract import CASES, RECIPES, dump, verify_coverage, verify_sources
    from h10_benchmark.runner import execution_environment, read_prepared

    verify_sources(root)
    environment = execution_environment()
    for case in CASES:
        read_prepared(root / "prepared", case)
    started = time.monotonic()
    proof = {
        "wheel_sha256": digest,
        "installed_module": str(origin),
        "installed_payload_files": installed_files,
        "mode": args.mode,
        "environment": environment,
    }
    if args.mode == "minimum":
        # El namespace debe bloquear red externa, manteniendo loopback para Jupyter.
        try:
            connection = socket.create_connection(("1.1.1.1", 443), timeout=2)
        except OSError:
            proof["external_network_blocked"] = True
        else:
            connection.close()
            raise ValueError("la red externa no está bloqueada")
        import nbformat
        from nbclient import NotebookClient

        shutil.copytree(root / "prepared", work / "prepared")
        notebook = nbformat.read(root / "minimo.ipynb", as_version=4)
        client = NotebookClient(
            notebook, timeout=180, kernel_name="h10-ci", resources={"metadata": {"path": str(work)}}
        )
        client.execute()
        nbformat.write(notebook, work / "minimo-executed.ipynb")
        source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
        lines = [
            line
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(lines) > 25 or "h10_benchmark" in source:
            raise ValueError("mínimo excede contrato de simplicidad")
        import pandas as pd
        from h10_benchmark.metrics import measure

        labels = pd.Series([0, 0, 1, 1])
        metric = measure(labels, labels.astype(float), labels.astype(float))
        assert metric["auc"] == metric["gini"] == metric["ks"] == 1
        assert metric["brier"] == metric["psi"] == 0
        rows = json.loads((root / "results/results.json").read_text(encoding="utf-8"))
        assert verify_coverage(rows)["executed"] == 28
        proof["minimum_lines"] = len(lines)
    else:
        from h10_benchmark.aggregate import verify_metrics
        from h10_benchmark.artifacts import verify_artifacts
        from h10_benchmark.runner import prepare, run

        shutil.copytree(root / "cache", work / "cache")
        prepare(work / "cache", work / "prepared")
        rows = run(work / "prepared", work / "results")
        coverage = verify_coverage(rows)
        if coverage["executed"] != 28:
            raise ValueError(f"cobertura completa requerida: {coverage}")
        verify_metrics(work / "results", rows, work / "prepared")
        artifacts = []
        for case in CASES:
            for recipe, options in RECIPES.items():
                if options is not None:
                    stem = f"{case}_{recipe}"
                    expected = json.loads((work / "results" / f"{stem}_expected.json").read_text())
                    artifacts.append(verify_artifacts(work / "results/projects" / stem, expected))
        proof.update(coverage=coverage, artifacts=artifacts)
    proof["seconds"] = time.monotonic() - started
    dump(work / "receipt.json", proof)
    if args.mode == "full":
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("coverage=28\n")
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
