"""Cuaderno nuevo H3: flujo, salidas ejecutadas y ausencia de rutas privadas."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from test_docs_notebook import _comparable, _ejecutar_como_un_kernel, _guardado

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "docs_site/notebooks/primera-provision-interna.ipynb"


def _comparar_html(actual: list[str], guardado: list[str]) -> None:
    """HTML exacto salvo residuos del sesgo medio de train dentro de tolerancia H3.

    BLAS cambia la última suma: -1,179e-15 frente a -1,284e-15, que el formato científico
    muestra como -1,2e-15/-1,3e-15. No se cambia ni redondea el dato o el cuaderno.
    D-H3 (§9) permite atol=1e-12 para medias: aquí se usa sólo alrededor de cero, sin rtol,
    en las dos filas de entrenamiento. Resto de métricas, conteos, estructura y copy exactos.
    """
    titulo = "<h3>Entrenamiento LGD</h3>"
    if not all(titulo in "\n".join(text) for text in (actual, guardado)):
        assert actual == guardado
        return
    fila = re.compile(
        r"(?P<inicio><tr>\s*<td>Entrenamiento</td>\s*"
        r"<td>(?:Modelo ajustado|Media de entrenamiento)</td>\s*"
        r"<td>[0-9]+</td>\s*<td>[^<]+</td>\s*<td>[^<]+</td>\s*<td>)"
        r"(?P<sesgo>[^<]+)(?P<fin></td>)"
    )

    def separar(text: list[str]) -> tuple[str, list[Decimal]]:
        sesgos = []

        def celda(match: re.Match[str]) -> str:
            valor = match["sesgo"]
            assert re.fullmatch(r"0|[-+]?[0-9]+(?:,[0-9]+)?e[-+][0-9]+", valor), valor
            sesgos.append(Decimal(valor.replace(",", ".")))
            return match["inicio"] + "<sesgo_train>" + match["fin"]

        texto = fila.sub(celda, "\n".join(text))
        assert len(sesgos) == 2
        return texto, sesgos

    texto_actual, sesgos_actuales = separar(actual)
    texto_guardado, sesgos_guardados = separar(guardado)
    assert texto_actual == texto_guardado
    tolerancia = Decimal("1e-12")
    for a, b in zip(sesgos_actuales, sesgos_guardados, strict=True):
        assert abs(a) <= tolerancia and abs(b) <= tolerancia
        assert abs(a - b) <= tolerancia


def _html_lgd_guardado() -> list[str]:
    notebook = json.loads(NOTEBOOK.with_name("primera-lgd.ipynb").read_text(encoding="utf-8"))
    cell = next(cell for cell in notebook["cells"] if cell["cell_type"] == "code")
    return _comparable(_guardado(cell["outputs"], "execute_result", "text/html"), ())


@pytest.mark.parametrize("sesgo", ["-1,1e-15", "-1,3e-15", "0", "1,2e-15"])
def test_oraculo_html_lgd_admite_redondeo_blas_solo_en_sesgo_nulo_de_train(sesgo):
    original = _html_lgd_guardado()
    distinto = [line.replace("-1,2e-15", sesgo) for line in original]
    assert distinto != original
    _comparar_html(distinto, original)


@pytest.mark.parametrize(
    ("antes", "despues"),
    [
        ("-1,2e-15", "-1,1e-12"),
        ("-1,2e-15", "NaN"),
        ("-1,2e-15", "inf"),
        ("-1,2e-15", "—"),
        ("0,4007", "0,4008"),
        ("0,1388", "0,1389"),
        ("0,0254", "0,0255"),
        ("300", "301"),
        ("80", "81"),
        ("Entrenamiento", "Evaluación"),
        ("Modelo ajustado", "Otro predictor"),
        ("<th>Sesgo medio</th>", "<th>Sesgo</th>"),
        ("No valida calidad ni transportabilidad", "Calidad validada"),
        ("</table>", "</table><p>Texto nuevo</p>"),
    ],
)
def test_oraculo_html_lgd_rechaza_cambios_de_cifras_estructura_y_advertencias(antes, despues):
    original = _html_lgd_guardado()
    distinto = [line.replace(antes, despues) for line in original]
    assert distinto != original, antes
    with pytest.raises(AssertionError):
        _comparar_html(distinto, original)


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
            # Sólo identidades; la comparación HTML trata el residuo numérico de train aparte.
            text = re.sub(r"(Ajuste de origen: )[0-9a-f]{32}", r"\1<run_id>", text or "")
            text = re.sub(
                r"(Huella (?:del config|de los datos) de origen: )[0-9a-f]{64}", r"\1<sha256>", text
            )
            return _comparable(text, (tmp_path, tmp_path.resolve()))

        assert compare(stdout) == compare(_guardado(cell["outputs"], "stream"))
        assert compare(repr(value)) == compare(_guardado(cell["outputs"], "execute_result"))
        _comparar_html(
            compare(value._repr_html_()),
            compare(_guardado(cell["outputs"], "execute_result", "text/html")),
        )
    assert scope["provision"].study.run_context.status == "done"
