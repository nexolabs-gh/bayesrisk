"""El ejemplo publicado H3 es el mismo recorrido ejecutable que consume la persona."""

from pathlib import Path

import pytest


def test_quickstart_provision_ejecutable(tmp_path, monkeypatch):
    pytest.importorskip("openpyxl")
    path = Path(__file__).resolve().parents[2] / "docs_site/guias/provision-guiada.md"
    text = path.read_text(encoding="utf-8")
    source = text.split("<!-- provision-guiada:start -->")[1].split(
        "<!-- provision-guiada:end -->"
    )[0]
    code = source.split("```python")[1].split("```")[0].strip()
    assert (
        len(
            [
                line
                for line in code.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        )
        <= 25
    )
    assert "Provision(" in code and "provision.resume()" in code
    monkeypatch.chdir(tmp_path)
    scope = {}
    exec(compile(code, str(path), "exec"), scope)
    provision = scope["provision"]
    assert provision.study.run_context.status == "done", provision.study.run_context.error
    assert (tmp_path / "provision.zip").is_file()
    assert len(provision.study.artifacts.get("provisioning_internal", "detail")) == len(
        scope["cartera"]
    )
