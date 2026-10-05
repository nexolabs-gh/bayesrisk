"""Gates de la guía «La provisión IFRS 9 de punta a punta» (FLUJO-GUIADO-IFRS9 capa C, §3.15).

La guía cuenta un relato continuo por dos de las tres puertas —la guiada y la completa— y el
segundo bloque corre el ``config.yaml`` que dejó el primero. Se ejecutan juntos, tal como los
teclearía un usuario, y se comprueba lo que la guía afirma: que las dos puertas llegan a la misma
cifra y al mismo ``config_hash``, que la decisión humana quedó aplicada y que la evidencia y el
paquete existen donde la guía dice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_GUIA = _RAIZ / "docs_site" / "guias" / "provision-ifrs9.md"
#: Bloques ejecutables, en orden de lectura.
_BLOQUES = ("provision-ifrs9-guiada", "provision-ifrs9-completa")


def _codigo_publicado() -> str:
    texto = _GUIA.read_text(encoding="utf-8")
    partes: list[str] = []
    for nombre in _BLOQUES:
        inicio = f"<!-- {nombre}:start -->\n```python\n"
        fin = f"\n```\n<!-- {nombre}:end -->"
        assert texto.count(inicio) == 1 and texto.count(fin) == 1, (
            f"el bloque ejecutable {nombre!r} de la guía perdió sus delimitadores"
        )
        partes.append(texto.split(inicio, maxsplit=1)[1].split(fin, maxsplit=1)[0])
    codigo = "\n".join(partes)
    # Ancla anti-vacuidad: unos delimitadores que envuelvan la nada se leen como un ejemplo bueno.
    anclas = ("Ecl(", 'run(until="survival")', "ecl.exclude(", "ecl.resume()", "bayesrisk.run(")
    for ancla in anclas:
        assert ancla in codigo, f"el código de la guía perdió {ancla!r}: el gate quedaría vacuo"
    return codigo


def test_la_guia_corre_por_las_dos_puertas_y_llega_a_la_misma_cifra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")
    from bayesrisk.core.config.hashing import config_hash

    codigo = _codigo_publicado()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    espacio: dict[str, Any] = {"__name__": "__main__"}
    exec(compile(codigo, str(_GUIA), "exec"), espacio)

    ecl = espacio["ecl"]
    study = espacio["study"]
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    assert study.run_context.status == "done", study.run_context.error
    assert "antiguedad_meses" not in ecl.config.survival.input.covariate_cols
    guiada = ecl.study.artifacts.get("provisioning_ifrs9", "card")
    completa = study.artifacts.get("provisioning_ifrs9", "card")
    assert float(completa.total_ecl_reported) == float(guiada.total_ecl_reported)
    assert config_hash(study.config) == ecl.config_hash
    proyecto = tmp_path / "bayesrisk-runs" / "provision_2025_06"
    assert (proyecto / "config.yaml").is_file()
    assert (proyecto / "reports" / "ifrs9_ecl_report.html").is_file()
    assert Path(espacio["paquete"]).is_file()
    assert (tmp_path / "bayesrisk-runs" / "provision_por_yaml" / "audit_trail.jsonl").is_file()


def test_la_guia_esta_en_la_navegacion_y_empezar_la_enlaza() -> None:
    nav = (_RAIZ / "mkdocs.yml").read_text(encoding="utf-8")
    assert "guias/provision-ifrs9.md" in nav
    empezar = (_RAIZ / "docs_site" / "getting-started.md").read_text(encoding="utf-8")
    assert "(guias/provision-ifrs9.md)" in empezar
