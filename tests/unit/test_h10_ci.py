"""Ataduras del candidato H10: mismo wheel, ejecución externa y cobertura obligatoria."""

from pathlib import Path

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
    assert "direct_url.json" in driver and '["sha256"] != digest' in driver
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
