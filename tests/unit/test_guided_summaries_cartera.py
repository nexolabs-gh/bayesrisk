"""Los resúmenes de la familia IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-7; §3.8 y §6-7 de la enmienda).

Una corrida que provisiona IFRS 9 sin dominios del scorecard habla en palabras de provisiones
—«Cartera», «Curva de PD», «Provisión IFRS 9», «Informe y ficha»—, venga de ``bayesrisk.Ecl``, de
un YAML o de la pantalla (también la del preset F4, que conserva su target inerte), con **una sola
fuente** para la puerta, la pantalla y el informe. Gates:

- ningún resumen filtra identificadores del motor ni las palabras del scorecard («malos»,
  «Desarrollo», «Holdout», «validación formal»), en texto, HTML ni JSON;
- el resumen final dice sus **supuestos** —leídos del config y de los artefactos de ESA corrida,
  nunca del preset— y cinco cifras de la provisión;
- una corrida con Vasicek, escenarios ponderados, PD de originación, bajada de rating, override o
  backstop PIT no se describe como TTC, escenario único ni staging sólo por mora;
- el scorecard se serializa exactamente igual que antes de que existiera la familia.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import bayesrisk
from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.markers import DECLARED_MARKERS
from bayesrisk.guided import STAGE_LABELS_CARTERA, Ecl, FinalSummary, StageSummary
from bayesrisk.guided.summaries import (
    SummaryContext,
    build_final_summary,
    build_stage_summaries,
    family_of,
)
from bayesrisk.report.prose import _IFRS9_PIT_MODE_LABELS
from bayesrisk.ui import datasets
from bayesrisk.ui.presets import ifrs9_preset, standard_preset

#: Las palabras del molde del scorecard que una provisión no puede decir (§6-7).
_PALABRAS_DEL_SCORECARD = ("malos", "desarrollo", "holdout", "validación formal")
#: Identificadores del motor IFRS 9 y de la curva que tienen que llegar traducidos.
_SLUGS_IFRS9 = {
    "sicr_pd_ratio",
    "sicr_pd_pit_backstop",
    "notch_downgrade",
    "stage_override",
    "dpd_sicr_backstop",
    "dpd_default_backstop",
    *_IFRS9_PIT_MODE_LABELS,
    "term_structure",
    "discrete_hazard",
    "pd_source",
    "pd_cumulative",
    "pd_marginal",
    "time_value",
    "horizon_12m_periods",
    "total_ecl_reported",
    "coverage_ratio",
    "period_1",
}
_MARCAS = re.compile("|".join(re.escape(m) for m in DECLARED_MARKERS))


def _ofensores(texto: str) -> list[str]:
    encontrados = [
        s for s in _SLUGS_IFRS9 if re.search(rf"(?<![\w.]){re.escape(s)}(?![\w.])", texto)
    ]
    if _MARCAS.search(texto):
        encontrados.append("<marca de aviso declarado>")
    minusculas = texto.casefold()
    encontrados.extend(p for p in _PALABRAS_DEL_SCORECARD if p in minusculas)
    return sorted(encontrados)


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def datos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))


@pytest.fixture(scope="module")
def corrida(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    ecl = Ecl(
        datos,
        id="loan_id",
        as_of="as_of_date",
        portfolio="portfolio",
        exposure="ead",
        lgd="lgd",
        rate="eir",
        days_past_due="days_past_due",
        default="is_default",
        duration="duration",
        event="event",
        period="year",
        horizon=5,
        covariates=["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"],
        run_dir=tmp_path_factory.mktemp("ecl"),
    )
    ecl._echo = lambda _texto: None
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


@pytest.fixture(scope="module")
def f4(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Any:
    """El preset F4 por la puerta completa: conserva su target y su partición, inertes."""
    cfg = deepcopy(ifrs9_preset()["config"])
    cfg["data"]["load"]["source"] = str(datos)
    cfg["report"] = None
    study = bayesrisk.run(
        BayesRiskConfig.model_validate(cfg), run_dir=tmp_path_factory.mktemp("f4") / "run"
    )
    assert study.run_context.status == "done", study.run_context.error
    return study


def _textos(resumen: StageSummary) -> tuple[str, ...]:
    return (
        resumen.text(),
        resumen._repr_html_(),
        json.dumps(resumen.to_dict(), ensure_ascii=False),
    )


# ─────────────────────────── la familia la decide el pipeline ───────────────────────────


def test_la_familia_la_decide_el_pipeline_no_la_puerta() -> None:
    assert family_of(BayesRiskConfig.model_validate(ifrs9_preset()["config"])) == "cartera"
    assert family_of(BayesRiskConfig.model_validate(standard_preset()["config"])) == "scorecard"
    assert family_of(None) == "scorecard"


def test_cada_etapa_habla_en_palabras_de_provisiones(corrida: Ecl) -> None:
    assert list(corrida._stage_summaries) == list(STAGE_LABELS_CARTERA)
    for etapa, resumen in corrida._stage_summaries.items():
        assert resumen.label == STAGE_LABELS_CARTERA[etapa]
        assert 1 <= len(resumen.lines) <= 8, (etapa, resumen.lines)


@pytest.mark.parametrize("etapa", list(STAGE_LABELS_CARTERA))
def test_ningun_resumen_filtra_codigos_ni_palabras_del_scorecard(corrida: Ecl, etapa: str) -> None:
    resumen = corrida.summary(etapa)
    assert isinstance(resumen, StageSummary)
    for texto in _textos(resumen):
        assert _ofensores(texto) == [], (etapa, _ofensores(texto))


def test_el_resumen_final_tampoco(corrida: Ecl) -> None:
    final = corrida.summary()
    assert isinstance(final, FinalSummary)
    for texto in (
        final.text(),
        final._repr_html_(),
        json.dumps(final.to_dict(), ensure_ascii=False),
    ):
        assert _ofensores(texto) == [], _ofensores(texto)


@pytest.mark.parametrize("etapa", list(STAGE_LABELS_CARTERA))
def test_texto_y_html_salen_de_la_misma_fuente(corrida: Ecl, etapa: str) -> None:
    resumen = corrida.summary(etapa)
    pagina = resumen._repr_html_()
    for linea in (*resumen.lines, *resumen.alerts):
        assert html.escape(linea) in pagina, linea
    for titulo, tabla, _formatos in resumen.extra_tables:
        assert html.escape(titulo) in pagina
        assert f"{titulo}:" in resumen.text()
        assert all(html.escape(str(c)) in pagina for c in tabla.columns)


# ─────────────────────────── lo que dice cada etapa ───────────────────────────


def test_cartera_cuenta_operaciones_fecha_exposicion_y_carteras(corrida: Ecl) -> None:
    resumen = corrida.summary("data")
    assert (
        "6.000 operaciones · fecha de corte 2025-06-30 · 4 carteras · exposición total 114.325.315"
        in resumen.lines
    )
    tabla = corrida.results["data"]
    assert list(tabla.columns) == [
        "Cartera",
        "Operaciones",
        "Exposición",
        "Participación en la exposición",
    ]
    assert tabla["Operaciones"].sum() == 6000


def test_la_curva_dice_su_historia_su_forma_y_el_efecto_de_cada_covariable(corrida: Ecl) -> None:
    resumen = corrida.summary("survival")
    texto = "\n".join(resumen.lines)
    assert "1.502 incumplimientos" in texto
    assert "La curva llega a 5 años" in texto
    assert "antiguedad_meses: más alto, menos riesgo" in texto
    assert "PD media de las operaciones: a 12 meses" in texto
    assert "a lo largo del ciclo (TTC)" in texto
    assert list(corrida.results["survival"].columns) == [
        "Término",
        "Coeficiente",
        "Error estándar",
        "p-valor",
        "Efecto",
    ]
    ((titulo, curva, _formatos),) = resumen.extra_tables
    assert titulo.startswith("PD acumulada por período y cartera")
    assert list(curva.columns) == [
        "Período",
        "Plazo",
        "Comercial",
        "Consumo",
        "Hipotecario",
        "Tarjetas",
        "Toda la cartera",
    ]
    assert curva["Plazo"].tolist() == ["1 año", "2 años", "3 años", "4 años", "5 años"]


def test_la_provision_dice_etapas_gatillos_y_la_ead_declarada(corrida: Ecl) -> None:
    resumen = corrida.summary("provisioning_ifrs9")
    texto = "\n".join(resumen.lines)
    assert "ECL total 3.423.116 · cobertura 2,99 %" in texto
    assert "Qué llevó a Stage 2: mora de 30 días o más (477)" in texto
    assert (
        "Qué llevó a Stage 3: mora de 90 días o más (240) y la marca de incumplimiento (288)"
        in texto
    )
    assert "si la cartera amortiza, la ECL de por vida queda sobrestimada" in texto
    assert any("(TTC)" in alerta for alerta in resumen.alerts)
    assert any("sólo por la mora y la marca" in alerta for alerta in resumen.alerts)
    assert list(corrida.results["provisioning_ifrs9"].columns) == [
        "Cartera",
        "Etapa",
        "Operaciones",
        "Exposición",
        "ECL",
        "Cobertura",
    ]


def test_el_resumen_final_dice_supuestos_y_las_cinco_cifras(corrida: Ecl) -> None:
    final = corrida.summary()
    assert isinstance(final, FinalSummary)
    texto = final.text()
    assert texto.startswith("══ Resumen de la provisión IFRS 9 ══")
    assert "Validación técnica" not in texto
    assert texto.index("Ejecución: completada") < texto.index("Supuestos:")
    assert [rotulo for rotulo, _valor in final.figures] == [
        "ECL total",
        "Cobertura (ECL sobre la exposición)",
        "Exposición en Stage 2 y 3",
        "ECL de Stage 2 y 3",
        "PD a 12 meses media, ponderada por la exposición",
    ]
    assert dict(final.figures)["ECL total"] == "3.423.116"
    supuestos = "\n".join(final.assumptions)
    assert "a lo largo del ciclo (TTC)" in supuestos
    assert "Un escenario único" in supuestos
    assert "Los 12 meses del Stage 1 son 1 año de la curva" in supuestos
    assert "las presunciones de IFRS 9" in supuestos
    assert "si la cartera amortiza" in supuestos
    # «Qué revisar» repite el TTC (§3.6 (a): lo dice siempre).
    assert any("(TTC)" in alerta for alerta in final.review)
    assert final.headline() == ("Ejecución: completada", "ECL total: 3.423.116")


# ─────────────────────────── una sola fuente: YAML y pantalla ───────────────────────────


def test_el_preset_f4_por_la_puerta_completa_habla_igual(f4: Any) -> None:
    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="f4", partition_label="")
    etapas = build_stage_summaries(f4, contexto)
    assert [e.label for e in etapas] == ["Cartera", "Curva de PD", "Provisión IFRS 9"]
    for etapa in etapas:
        for texto in _textos(etapa):
            assert _ofensores(texto) == [], (etapa.stage, _ofensores(texto))
    final = build_final_summary(f4, etapas, contexto)
    assert final.family == "cartera" and final.assumptions


def test_la_pantalla_lee_la_misma_familia(f4: Any, tmp_path: Path) -> None:
    from bayesrisk.ui.summaries import serialize_summaries

    resumen = serialize_summaries(f4, source_label="f4", run_dir=tmp_path, trail_path=None)
    assert resumen["error"] is None
    assert [e["label"] for e in resumen["stages"]] == ["Cartera", "Curva de PD", "Provisión IFRS 9"]
    assert resumen["final"]["family"] == "cartera"
    assert resumen["final"]["title"] == "Resumen de la provisión IFRS 9"
    assert resumen["final"]["assumptions"]
    curva = next(e for e in resumen["stages"] if e["stage"] == "survival")
    assert curva["extra_tables"][0]["title"].startswith("PD acumulada")


def test_un_resumen_del_scorecard_se_serializa_como_antes() -> None:
    final = FinalSummary(
        execution="completada",
        validation="Aprobado",
        figures=(),
        review=(),
        decisions=(),
        files=(),
    )
    assert set(final.to_dict()) == {
        "execution",
        "validation",
        "figures",
        "review",
        "decisions",
        "files",
    }
    assert final.text().startswith("══ Resumen del scorecard ══")
    etapa = StageSummary(stage="data", label="Datos y muestras", lines=("x",))
    assert set(etapa.to_dict()) == {"stage", "label", "lines", "alerts", "table"}


# ───────────────── los supuestos son los de ESA corrida, no los del preset ─────────────────


class _Artefactos:
    def __init__(self, datos: dict[tuple[str, str], Any]) -> None:
        self._datos = datos

    def has(self, dominio: str, clave: str) -> bool:
        return (dominio, clave) in self._datos

    def get(self, dominio: str, clave: str) -> Any:
        return self._datos[(dominio, clave)]

    def keys(self) -> list[tuple[str, str]]:
        return list(self._datos)


def _estudio(cambios: dict[str, Any], card: dict[str, Any], columnas: tuple[str, ...]) -> Any:
    """Un estudio mínimo con el config F4 cambiado y la card que esa corrida publicaría."""
    cfg = deepcopy(ifrs9_preset()["config"])
    for ruta, valor in cambios.items():
        *camino, hoja = ruta.split(".")
        destino = cfg
        for parte in camino:
            destino = destino[parte]
        destino[hoja] = valor
    base_card = {
        "as_of_date": "2025-06-30",
        "term_structure_source": "survival",
        "pit_mode": cfg["provisioning_ifrs9"]["pd"]["pit_mode"],
        "n_rows": 2,
        "total_ead": 100.0,
        "total_ecl_reported": 3.0,
        "scenarios": ("base",),
        "scenario_weights": {"base": 1.0},
        "falta_dato": (),
    }
    base_card.update(card)
    frame = pd.DataFrame({c: [0.1, 0.2] for c in columnas})
    artefactos = {
        ("data", "frame"): frame,
        ("provisioning_ifrs9", "card"): base_card,
    }
    return SimpleNamespace(
        config=SimpleNamespace(**cfg),
        artifacts=_Artefactos(artefactos),
        run_context=SimpleNamespace(status="done", error=None),
        preamble=(),
    )


_COLUMNAS_F4 = ("days_past_due", "is_default", "ead")


@pytest.mark.parametrize(
    ("caso", "cambios", "card", "columnas"),
    [
        (
            "vasicek",
            {"provisioning_ifrs9.pd.pit_mode": "apply_vasicek"},
            {"pit_mode": "apply_vasicek"},
            _COLUMNAS_F4,
        ),
        (
            "escenarios ponderados",
            {"provisioning_ifrs9.scenarios.source": "forward"},
            {
                "scenarios": ("base", "adverso"),
                "scenario_weights": {"base": 0.6, "adverso": 0.4},
                "pit_mode": "consume_pit",
            },
            _COLUMNAS_F4,
        ),
        (
            "PD de originación",
            {"provisioning_ifrs9.staging.origination_pd_life_col": "pd_origen"},
            {},
            _COLUMNAS_F4,
        ),
        (
            "bajada de rating",
            {
                "provisioning_ifrs9.staging.notch_downgrade_threshold": 2,
                "provisioning_ifrs9.staging.rating_col": "rating",
                "provisioning_ifrs9.staging.origination_rating_col": "rating_origen",
            },
            {},
            _COLUMNAS_F4,
        ),
        (
            "override",
            {"provisioning_ifrs9.staging.stage_override_col": "override"},
            {},
            _COLUMNAS_F4,
        ),
        ("backstop PIT", {}, {}, (*_COLUMNAS_F4, "pd_pit_origination")),
    ],
)
def test_una_corrida_distinta_no_se_describe_con_los_supuestos_del_preset(
    caso: str, cambios: dict[str, Any], card: dict[str, Any], columnas: tuple[str, ...]
) -> None:
    study = _estudio(cambios, card, columnas)
    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="x", partition_label="")
    final = build_final_summary(study, (), contexto)
    from bayesrisk.guided.summaries import _resumen_provision

    provision = _resumen_provision(study, contexto)
    todo = "\n".join((*final.assumptions, *provision.alerts, *provision.lines))
    pit = card.get("pit_mode", "ttc_only")
    if pit != "ttc_only":
        assert "TTC" not in todo, (caso, todo)
    if len(card.get("scenarios", ("base",))) > 1:
        assert "escenario único" not in todo, (caso, todo)
        assert "Escenarios ponderados: base (60 %), adverso (40 %)" in todo
    if caso in {"PD de originación", "bajada de rating", "override", "backstop PIT"}:
        assert "sólo por la mora" not in todo, (caso, todo)


def test_sin_cambios_el_estudio_minimo_si_es_ttc_y_solo_por_mora() -> None:
    """La contracara: con el config F4 tal cual, las tres frases sí aparecen (gate no vacío)."""
    study = _estudio({}, {}, _COLUMNAS_F4)
    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="x", partition_label="")
    from bayesrisk.guided.summaries import _resumen_provision

    final = build_final_summary(study, (), contexto)
    provision = _resumen_provision(study, contexto)
    todo = "\n".join((*final.assumptions, *provision.alerts))
    assert "TTC" in todo and "Un escenario único" in todo and "sólo por la mora" in todo


def test_sin_marca_no_se_afirma_que_el_stage_3_sea_solo_por_mora_si_hay_override() -> None:
    """Pasada 1 de Codex: el override cualitativo también lleva a Stage 3 sin la marca."""
    from bayesrisk.guided.summaries import _resumen_provision

    study = _estudio(
        {
            "provisioning_ifrs9.staging.is_default_col": None,
            "provisioning_ifrs9.staging.stage_override_col": "override",
        },
        {},
        _COLUMNAS_F4,
    )
    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="x", partition_label="")
    texto = "\n".join(_resumen_provision(study, contexto).lines)
    assert "sólo por mora" not in texto
    assert "Sin marca de incumplimiento: al Stage 3 lo llevan la mora de 90 días o más" in texto
    assert "decisión cualitativa" in texto


def test_sin_covariables_no_se_afirma_que_solo_ordenen_la_mora_y_la_marca() -> None:
    from bayesrisk.guided.summaries import _resumen_curva

    study = _estudio(
        {
            "survival.input.covariate_cols": [],
            "provisioning_ifrs9.staging.stage_override_col": "override",
        },
        {},
        _COLUMNAS_F4,
    )
    study.artifacts._datos[("survival", "card")] = {"time_unit": "year", "n_periods": 5}
    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="x", partition_label="")
    resumen = _resumen_curva(study, contexto)
    assert resumen.alerts
    assert not any("sólo lo dan" in alerta for alerta in resumen.alerts)
