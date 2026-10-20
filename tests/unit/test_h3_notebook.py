"""Cuaderno nuevo H3: flujo, salidas ejecutadas y ausencia de rutas privadas."""

import json
import re
from pathlib import Path

import pytest
from test_docs_notebook import _comparable, _ejecutar_como_un_kernel, _guardado

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "docs_site/notebooks/primera-provision-interna.ipynb"


@pytest.mark.parametrize("mode", ["provision", "lgd"])
def test_cuaderno_h3_ejecuta_y_sus_salidas_estan_vigentes(tmp_path, monkeypatch, mode):
    pytest.importorskip("openpyxl")
    pytest.importorskip("statsmodels")
    notebook_path = NOTEBOOK if mode == "provision" else NOTEBOOK.with_name("primera-lgd.ipynb")
    text = notebook_path.read_text(encoding="utf-8")
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
    assert f"../notebooks/{notebook_path.name}" in guide
    marker = "provision-guiada" if mode == "provision" else "lgd-guiada"
    block = guide.split(f"<!-- {marker}:start -->")[1].split("```python")[1].split("```")[0]
    assert all(line in code for line in block.splitlines() if line.strip())
    monkeypatch.chdir(tmp_path)
    scope = {"__name__": "__main__"}
    for cell in cells:
        assert cell["outputs"] and all(
            output["output_type"] != "error" for output in cell["outputs"]
        )
        stdout, value = _ejecutar_como_un_kernel(cell["source"], scope, str(NOTEBOOK))

        def compare(text):
            # Sólo identidades del ajuste: nunca se normalizan métricas, conteos o advertencias.
            text = re.sub(r"(Ajuste de origen: )[0-9a-f]{32}", r"\1<run_id>", text or "")
            text = re.sub(
                r"(Huella (?:del config|de los datos) de origen: )[0-9a-f]{64}", r"\1<sha256>", text
            )
            return _comparable(text, (tmp_path, tmp_path.resolve()))

        assert compare(stdout) == compare(_guardado(cell["outputs"], "stream"))
        assert compare(repr(value)) == compare(_guardado(cell["outputs"], "execute_result"))
        assert compare(value._repr_html_()) == compare(
            _guardado(cell["outputs"], "execute_result", "text/html")
        )
    assert scope["provision"].study.run_context.status == "done"
