"""Ataduras del candidato H10: mismo wheel, ejecución externa y cobertura obligatoria."""

import ast
import importlib.util
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_h10_ci_candidato_y_cobertura_no_opcionales():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["h10"]
    assert job["needs"] == "build"
    assert job["timeout-minutes"] == 20
    assert not job.get("continue-on-error")
    steps = job["steps"]
    downloaded = [s for s in steps if s.get("uses", "").startswith("actions/download-artifact")]
    assert downloaded[0]["with"]["name"] == "candidate-distributions-with-evidence"
    scripts = "\n".join(s.get("run", "") for s in steps)
    assert scripts.index("--require-hashes") < scripts.index("--no-deps --reinstall")
    assert "unshare --net" in scripts
    assert "check_distribution_contents.py" not in scripts
    full = next(s for s in steps if s.get("id") == "full")
    assert "workflow_dispatch" in full["if"] and "tag" in full["if"]
    assert not full.get("continue-on-error")
    marker = workflow["jobs"]["h10-release"]
    assert marker["needs"] == "h10"
    assert marker["name"] == "H10 cobertura completa acreditada"
    assert marker["steps"][0]["run"] == 'test "$COVERAGE" = "28"'


def test_recibo_completo_se_emite_despues_de_metricas_y_artefactos():
    driver = (ROOT / "scripts/run_h10_ci.py").read_text(encoding="utf-8")
    assert driver.index("verify_metrics(work") < driver.index('output.write("coverage=28')
    assert driver.index("artifacts.append(verify_artifacts") < driver.index(
        'output.write("coverage=28'
    )
    calls = [
        node
        for node in ast.walk(ast.parse(driver))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_installed_wheel"
    ]
    assert len(calls) == 1 and ast.unparse(calls[0].args[0]) == "args.wheel"
    assert "socket.create_connection" in driver


def test_release_elige_candidato_con_h10_completo_del_mismo_run_y_ref():
    release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    step = next(s for s in release["jobs"]["promote"]["steps"] if s.get("id") == "ci")
    script = step["run"]
    assert '"$ref_run" = "$GITHUB_REF_NAME"' in script
    assert '$2 == "H10 cobertura completa acreditada"' in script
    assert "vistos == 1 && verdes == 1" in script
    assert '"$rid" -gt "$run_id"' in script
    assert script.index('if [ "$malos" -ne 0 ]') < script.index("run_id=0")
    assert script.index('if [ "$run_id" -eq 0 ]') < script.index('echo "run_id=$run_id"')


@pytest.mark.parametrize("defect", [None, "alterado", "ausente", "extra", "bytecode_extra"])
def test_candidato_compara_bytes_instalados_sin_depender_del_instalador(tmp_path, defect):
    spec = importlib.util.spec_from_file_location("h10_ci_driver", ROOT / "scripts/run_h10_ci.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    installed = tmp_path / "site-packages"
    package = installed / "bayesrisk"
    package.mkdir(parents=True)
    module = package / "__init__.py"
    module.write_bytes(b"__version__ = '2.16.0'\n")
    info = installed / "bayesrisk-2.16.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_bytes(b"Name: bayesrisk\nVersion: 2.16.0\n")
    (info / "RECORD").write_text("reescrito por el instalador")
    # uv puede registrar archive_info vacío; no sustituye el cotejo del payload.
    (info / "direct_url.json").write_text('{"archive_info": {}, "url": "file:///candidate.whl"}')
    wheel = tmp_path / "candidate.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        for p in (module, info / "METADATA"):
            z.writestr(p.relative_to(installed).as_posix(), p.read_bytes())
        z.writestr("bayesrisk-2.16.0.dist-info/RECORD", "registro original")
    if defect == "alterado":
        module.write_bytes(b"otro wheel")
    elif defect == "ausente":
        module.unlink()
    elif defect == "extra":
        (package / "otra.py").write_text("residuo")
    elif defect == "bytecode_extra":
        (package / "otra.pyc").write_bytes(b"residuo")
    from types import SimpleNamespace

    distribution = SimpleNamespace(locate_file=lambda name: installed / name)
    if defect:
        with pytest.raises(ValueError, match="instalad"):
            driver.verify_installed_wheel(wheel, distribution)
    else:
        assert driver.verify_installed_wheel(wheel, distribution) == 2
