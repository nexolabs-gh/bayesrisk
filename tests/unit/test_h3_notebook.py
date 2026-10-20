"""Cuaderno nuevo H3: flujo, salidas ejecutadas y ausencia de rutas privadas."""

import json
from pathlib import Path

import pytest
from test_docs_notebook import _comparable, _ejecutar_como_un_kernel, _guardado

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "docs_site/notebooks/primera-provision-interna.ipynb"


def test_cuaderno_h3_ejecuta_y_sus_salidas_estan_vigentes(tmp_path, monkeypatch):
    pytest.importorskip("openpyxl")
    text = NOTEBOOK.read_text(encoding="utf-8")
    for private in ("Users", "AppData", "Proyectos", "OneDrive", "/tmp/", "/home/"):
        assert private not in text
    notebook = json.loads(text)
    assert notebook["nbformat"] == 4
    cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    code = "\n".join(cell["source"] for cell in cells)
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
    guide = (ROOT / "docs_site/guias/provision-guiada.md").read_text(encoding="utf-8")
    assert "../notebooks/primera-provision-interna.ipynb" in guide
    block = guide.split("```python")[1].split("```")[0]
    assert all(line in code for line in block.splitlines() if line.strip())
    monkeypatch.chdir(tmp_path)
    scope = {"__name__": "__main__"}
    for cell in cells:
        assert cell["outputs"] and all(
            output["output_type"] != "error" for output in cell["outputs"]
        )
        stdout, value = _ejecutar_como_un_kernel(cell["source"], scope, str(NOTEBOOK))

        def compare(text):
            return _comparable(text or "", (tmp_path, tmp_path.resolve()))

        assert compare(stdout) == compare(_guardado(cell["outputs"], "stream"))
        assert compare(repr(value)) == compare(_guardado(cell["outputs"], "execute_result"))
        assert compare(value._repr_html_()) == compare(
            _guardado(cell["outputs"], "execute_result", "text/html")
        )
    assert scope["provision"].study.run_context.status == "done"
