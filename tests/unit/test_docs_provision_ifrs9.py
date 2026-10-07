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


def _bloque(nombre: str, anclas: tuple[str, ...]) -> str:
    texto = _GUIA.read_text(encoding="utf-8")
    inicio = f"<!-- {nombre}:start -->\n```python\n"
    fin = f"\n```\n<!-- {nombre}:end -->"
    assert texto.count(inicio) == 1 and texto.count(fin) == 1, (
        f"el bloque ejecutable {nombre!r} de la guía perdió sus delimitadores"
    )
    codigo = texto.split(inicio, maxsplit=1)[1].split(fin, maxsplit=1)[0]
    for ancla in anclas:
        assert ancla in codigo, f"el código de la guía perdió {ancla!r}: el gate quedaría vacuo"
    return codigo


def test_el_bloque_del_contrato_lee_la_curva_con_fechas_y_cuota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CASO-REAL-IFRS9 §13: las tres columnas en un bloque de la guía, sobre un archivo sintético
    pequeño y determinista generado en el propio bloque. Se comprueba lo que la guía afirma."""
    pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")
    codigo = _bloque(
        "provision-ifrs9-contrato",
        ("origination=", "maturity=", "installment=", "contrato.run()"),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    espacio: dict[str, Any] = {"__name__": "__main__"}
    exec(compile(codigo, str(_GUIA), "exec"), espacio)

    ecl = espacio["contrato"]
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    card = ecl.study.artifacts.get("provisioning_ifrs9", "card")
    assert card.contract_dates is True
    # «la de los préstamos a 48 meses que pasan del período 14»: la cola empieza en el 15.
    assert card.tail_from_period == 15
    assert card.ead_beyond_observed_curve and card.ead_beyond_observed_curve > 0
    # Cuotas de una tabla exacta: todas pagan su saldo en el plazo.
    assert card.n_amortizing == card.n_rows
    assert "FALTA-DATO-IFRS-4" not in card.falta_dato
    lineas = ecl.summary("provisioning_ifrs9").lines
    assert any(linea.startswith("Con las fechas del contrato") for linea in lineas), lineas
    assert any("tabla de pagos" in linea for linea in lineas), lineas


def test_el_bloque_de_escenarios_recupera_la_sensibilidad_y_pondera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IFRS9-FIRMABLE §3.10 y §13: el bloque genera una historia sintética con una sensibilidad
    conocida (0,15 por punto) y tres escenarios, sobre la cartera del bloque anterior. Se comprueba
    lo que la guía afirma: el motor recupera la sensibilidad dentro de su error, la ECL es la
    ponderada de los escenarios —y reconcilia sin redondear—, la de desplazamiento cero es la del
    bloque sin escenarios, y los resúmenes cuentan la sensibilidad, el ancla y los supuestos."""
    pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")
    codigo = (
        _bloque(
            "provision-ifrs9-contrato",
            ("origination=", "maturity=", "installment=", "contrato.run()"),
        )
        + "\n"
        + _bloque(
            "provision-ifrs9-escenarios",
            ("history=historia", "scenarios=escenarios", "con_escenarios.run()", "0.15 *"),
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    espacio: dict[str, Any] = {"__name__": "__main__"}
    exec(compile(codigo, str(_GUIA), "exec"), espacio)

    ecl = espacio["con_escenarios"]
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    modelo = ecl.study.artifacts.get("forward", "cycle_model")
    assert abs(modelo.coefficients["desempleo"] - 0.15) < 3 * modelo.std_errors["desempleo"]
    card = ecl.study.artifacts.get("provisioning_ifrs9", "card")
    secciones = card.metric_sections
    por_escenario = secciones["ecl_reported_by_scenario"]
    assert set(por_escenario) == {"base", "adverso", "severo"}
    assert por_escenario["base"] < por_escenario["adverso"] < por_escenario["severo"]
    total = float(
        ecl.study.artifacts.get("provisioning_ifrs9", "detail")["ecl_reported_unrounded"].sum()
    )
    pesos = {"base": 0.6, "adverso": 0.3, "severo": 0.1}
    assert sum(pesos[k] * v for k, v in por_escenario.items()) == pytest.approx(total, rel=1e-12)
    sin_escenarios = espacio["contrato"].study.artifacts.get("provisioning_ifrs9", "detail")
    assert secciones["ecl_reported_ttc"] == float(sin_escenarios["ecl_reported_unrounded"].sum())
    assert secciones["cycle"]["anchor"] == "curve_history"
    assert ecl.study.artifacts.has("provisioning_ifrs9", "cycle_by_period")
    escenarios = ecl.summary("forward")
    assert any("Sensibilidad a «desempleo»" in linea for linea in escenarios.lines)
    provision = ecl.summary("provisioning_ifrs9").lines
    assert any(
        linea.startswith("ECL ponderada por 3 escenarios") and "con desplazamiento cero" in linea
        for linea in provision
    )
    assert any(linea.startswith("Ancla: la macro media de la historia") for linea in provision)
    supuestos = ecl.summary().assumptions
    assert any("uno a uno" in s for s in supuestos), supuestos
    assert not any("a lo largo del ciclo (TTC)" in s for s in supuestos), supuestos


def test_el_bloque_de_la_pd_del_modelo_ancla_y_compara_por_tramo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IFRS9-FIRMABLE §3.10 y §13 (capa B): el bloque genera una PD de origen y una de hoy, peor en
    un 10 % de la cartera, sobre la cartera y las tablas de los dos bloques anteriores. Se
    comprueba lo que la guía afirma: la curva de cada operación se ancla a la PD de hoy, el resumen
    compara las dos medias, y las que pasan a Stage 2 por la PD de origen son las que empeoraron."""
    pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")
    codigo = "\n".join(
        (
            _bloque(
                "provision-ifrs9-contrato",
                ("origination=", "maturity=", "installment=", "contrato.run()"),
            ),
            _bloque(
                "provision-ifrs9-escenarios",
                ("history=historia", "scenarios=escenarios", "con_escenarios.run()"),
            ),
            _bloque(
                "provision-ifrs9-pd",
                ('pd="pd_hoy"', 'origination_pd="pd_origen"', "con_pd.run()", "deterioro"),
            ),
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    espacio: dict[str, Any] = {"__name__": "__main__"}
    exec(compile(codigo, str(_GUIA), "exec"), espacio)

    ecl = espacio["con_pd"]
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    card = ecl.study.artifacts.get("provisioning_ifrs9", "card")
    anclaje = card.metric_sections["pd_model_anchor"]
    assert anclaje["n_rows_anchored"] == card.n_rows
    assert anclaje["n_rows_without_pd"] == 0
    sicr = card.metric_sections["sicr_origination_12m"]
    assert sicr["with_scenarios"] is True
    assert sicr["n_rows_moved_to_stage2"] > 0
    staging = ecl.study.artifacts.get("provisioning_ifrs9", "staging")
    cartera = espacio["cartera"].set_index("loan_id")
    peores = cartera.loc[espacio["deterioro"] < 0].index
    movidas = staging.loc[
        staging["sicr_triggers"].map(lambda g: g == ("sicr_pd_origination_12m",)), "row_id"
    ]
    assert len(movidas) == sicr["n_rows_moved_to_stage2"]
    assert movidas.isin(peores).mean() >= 0.9
    lineas = ecl.summary("provisioning_ifrs9").lines
    assert any(ln.startswith("PD a 12 meses de tu modelo en") for ln in lineas), lineas
    assert any(
        ln.startswith("Aumento significativo del riesgo por la PD de origen") for ln in lineas
    )
    supuestos = ecl.summary().assumptions
    assert any("es la de tu modelo" in s for s in supuestos), supuestos
    assert any("mismo tramo de vida" in s for s in supuestos), supuestos


def test_la_guia_esta_en_la_navegacion_y_empezar_la_enlaza() -> None:
    nav = (_RAIZ / "mkdocs.yml").read_text(encoding="utf-8")
    assert "guias/provision-ifrs9.md" in nav
    empezar = (_RAIZ / "docs_site" / "getting-started.md").read_text(encoding="utf-8")
    assert "(guias/provision-ifrs9.md)" in empezar
