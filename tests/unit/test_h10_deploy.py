"""La primera publicación y los cambios del benchmark exigen su CI completo exacto."""

import importlib
import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("check_h10_deploy")


def api(monkeypatch, gate, *, status="completed", conclusion="success", jobs=None, **changes):
    run = dict(
        id=41,
        head_sha=SHA,
        head_branch="main",
        event="workflow_dispatch",
        status=status,
        conclusion=conclusion,
        head_repository={"full_name": "o/r"},
    )
    run.update(changes)
    if jobs is None:
        jobs = [
            {
                "name": "H10 cobertura completa acreditada",
                "conclusion": "success",
                "status": "completed",
            }
        ]

    def response(request, **kwargs):
        body = (
            {"total_count": len(jobs), "jobs": jobs}
            if "/41/jobs" in request.full_url
            else {
                "workflow_runs": [
                    dict(run, id=40, event="push", status="completed", conclusion="success"),
                    run,
                ]
            }
        )
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(gate.urllib.request, "urlopen", response)


@pytest.mark.parametrize(
    "status,conclusion",
    [("in_progress", None), ("completed", "failure"), ("completed", "cancelled")],
)
def test_minimo_verde_no_suplanta_completo_pendiente_o_rojo(gate, monkeypatch, status, conclusion):
    api(monkeypatch, gate, status=status, conclusion=conclusion)
    with pytest.raises(ValueError, match="H10 completo"):
        gate.require_complete(SHA, "o/r", "token")


def test_completo_verde_mismo_sha_habilita(gate, monkeypatch):
    api(monkeypatch, gate)
    assert gate.require_complete(SHA, "o/r", "token") == 41


@pytest.mark.parametrize("conclusion,expected", [("failure", 1), (None, 1), ("success", 0)])
def test_entrada_del_workflow_bloquea_y_habilita(gate, monkeypatch, conclusion, expected):
    from types import SimpleNamespace

    monkeypatch.setenv("DEPLOY_SHA", SHA)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("FORZAR", raising=False)
    monkeypatch.setattr(gate, "leer_sello", lambda url: SimpleNamespace(sha="b" * 40))
    monkeypatch.setattr(gate, "changed", lambda *args: True)
    api(
        monkeypatch,
        gate,
        conclusion=conclusion,
        status="in_progress" if conclusion is None else "completed",
    )
    assert gate.main() == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"head_sha": "b" * 40},
        {"head_branch": "otra"},
        {"event": "push"},
        {"head_repository": {"full_name": "otro/r"}},
    ],
)
def test_verde_ajeno_no_habilita(gate, monkeypatch, changes):
    api(monkeypatch, gate, **changes)
    with pytest.raises(ValueError, match="H10 completo"):
        gate.require_complete(SHA, "o/r", "token")


@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled"])
def test_marcador_no_verde_no_habilita(gate, monkeypatch, conclusion):
    api(
        monkeypatch,
        gate,
        jobs=[
            {
                "name": "H10 cobertura completa acreditada",
                "status": "completed",
                "conclusion": conclusion,
            }
        ],
    )
    with pytest.raises(ValueError, match="H10 completo"):
        gate.require_complete(SHA, "o/r", "token")


def test_api_caida_no_habilita(gate, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("sin red")

    monkeypatch.setattr(gate.urllib.request, "urlopen", fail)
    with pytest.raises(OSError):
        gate.require_complete(SHA, "o/r", "token")
    with pytest.raises(ValueError, match="token"):
        gate.require_complete(SHA, "o/r", None)


def test_run_verde_con_otro_job_rojo_no_habilita(gate, monkeypatch):
    api(
        monkeypatch,
        gate,
        jobs=[
            {
                "name": "H10 cobertura completa acreditada",
                "status": "completed",
                "conclusion": "success",
            },
            {"name": "Otro gate", "status": "completed", "conclusion": "failure"},
        ],
    )
    with pytest.raises(ValueError, match="H10 completo"):
        gate.require_complete(SHA, "o/r", "token")


def test_compara_con_lo_publicado_no_con_padre_del_commit(gate, tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "README").write_text("base")
    git("add", ".")
    git("commit", "-qm", "base")
    published = git("rev-parse", "HEAD")
    delivery = tmp_path / "docs_site/downloads"
    delivery.mkdir(parents=True)
    (delivery / "h10-benchmark.json").write_text("primer benchmark")
    git("add", ".")
    git("commit", "-qm", "benchmark")
    benchmark = git("rev-parse", "HEAD")
    (tmp_path / "README").write_text("documentación posterior")
    git("add", ".")
    git("commit", "-qm", "docs")
    tip = git("rev-parse", "HEAD")
    assert gate.changed(tmp_path, published, tip)
    assert not gate.changed(tmp_path, benchmark, tip)
    with pytest.raises(ValueError, match="comparar"):
        gate.changed(tmp_path, "f" * 40, tip)


def test_workflow_comprueba_antes_del_build_y_antes_de_publicar():
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    gates = [
        i for i, s in enumerate(steps) if s.get("run") == "python3 scripts/check_h10_deploy.py"
    ]
    assert len(gates) == 2
    build = next(
        i for i, s in enumerate(steps) if s["name"] == "Construir el sitio de documentación"
    )
    publish = next(i for i, s in enumerate(steps) if s["name"] == "Publicar docs.bayesadvisory.cl")
    assert gates[0] < build < gates[1] < publish
    assert all("SALTAR" in steps[i]["if"] and "PREVIEW" in steps[i]["if"] for i in gates)
