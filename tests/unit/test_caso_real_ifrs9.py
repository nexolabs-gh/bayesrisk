"""El caso real de IFRS 9, capa A (enmienda CASO-REAL-IFRS9, D-CRE-5 y D-CRE-6).

D-CRE-1 (Stage 3 = LGD × EAD) vive en los goldens que ya fijaban la cifra —``test_ifrs9_engine``,
``test_ifrs9_config``, ``test_guided_ecl``, ``test_guided_summaries_cartera``—; aquí, las dos reglas
nuevas de la capa:

- **D-CRE-5 (§3.5).** Una fila sin exposición (EAD = 0) no es una operación de la cartera: se separa
  justo después de calcular la EAD y antes de validar y leer cualquier otro insumo, de buscar la PD
  y de estagear. Sólo alimenta la curva. La ECL no cambia (esas filas aportaban cero); los conteos,
  sí, y la card dice cuántas se separaron.
- **D-CRE-6 (§3.6).** Con ``survival.input.id_col``, la curva identifica cada operación por el valor
  de esa columna —única, con un error que nombra las repetidas— y la provisión la lee con
  ``row_id_col``; si no coinciden, la corrida se detiene antes de correr.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bayesrisk.provisioning.ifrs9 import IfrsProvisioningConfig, IfrsProvisioningEngine
from bayesrisk.provisioning.ifrs9.config import (
    IfrsEadConfig,
    IfrsLgdConfig,
    IfrsPdConfig,
    IfrsScenarioConfig,
    IfrsStagingConfig,
)
from bayesrisk.provisioning.ifrs9.exceptions import IfrsInputError, IfrsTermStructureError
from bayesrisk.provisioning.ifrs9.results import IfrsProvisionResult

# ─────────────────────────── D-CRE-5: el motor ───────────────────────────


def _cfg() -> IfrsProvisioningConfig:
    """EAD y LGD entregadas, curva de dos períodos anuales, horizonte de 12 meses = 1."""
    return IfrsProvisioningConfig(
        row_id_col=None,
        portfolio_col="portfolio",
        pd=IfrsPdConfig(
            term_structure_source="survival", pit_mode="ttc_only", horizon_12m_periods=1
        ),
        lgd=IfrsLgdConfig(method="provided"),
        ead=IfrsEadConfig(method="provided"),
        scenarios=IfrsScenarioConfig(source="single"),
        staging=IfrsStagingConfig(),
    )


def _cartera() -> pd.DataFrame:
    """Tres vivas —Stage 1, 2 y 3— y dos cerradas con EAD 0 e insumos que hoy abortarían."""
    return pd.DataFrame(
        {
            "portfolio": ["consumo", "consumo", "tarjetas", "consumo", "tarjetas"],
            "ead": [900.0, 0.0, 500.0, 0.0, 1_200.0],
            # La cerrada `h1` trae una LGD fuera de rango y la `h2` una tasa y una mora vacías:
            # dato de historia, no de la cartera viva.
            "lgd": [0.40, 1.50, 0.60, 0.30, 0.45],
            "eir": [0.10, 0.12, 0.08, np.nan, 0.15],
            "days_past_due": [0.0, 120.0, 45.0, np.nan, 95.0],
            "is_default": [False, True, False, False, False],
        },
        index=pd.Index(["v1", "h1", "v2", "h2", "v3"], name="loan_id"),
    )


def _curva(row_ids: list[str]) -> pd.DataFrame:
    filas = []
    for i, rid in enumerate(row_ids):
        marginal = [0.02 + 0.01 * i, 0.03 + 0.01 * i]
        acumulada = np.cumsum(marginal)
        for periodo in (1, 2):
            filas.append(
                {
                    "row_id": rid,
                    "period": periodo,
                    "time_value": float(periodo),
                    "time_unit": "year",
                    "pd_marginal": marginal[periodo - 1],
                    "pd_cumulative": float(acumulada[periodo - 1]),
                    "survival": 1.0 - float(acumulada[periodo - 1]),
                    "scenario": None,
                    "warning_codes": (),
                }
            )
    return pd.DataFrame(filas)


def _calcular(frame: pd.DataFrame, curva: pd.DataFrame) -> IfrsProvisionResult:
    return IfrsProvisioningEngine.from_config(_cfg()).calculate(
        frame, term_structure=curva, as_of_date="2026-03-31"
    )


def test_las_filas_sin_exposicion_no_son_operaciones_ni_se_validan() -> None:
    """D-CRE-5: la corrida termina, cuenta sólo las vivas y la ECL es la de las vivas."""
    frame = _cartera()
    resultado = _calcular(frame, _curva(list(frame.index)))

    vivas = ["v1", "v2", "v3"]
    assert resultado.detail["row_id"].tolist() == vivas
    assert resultado.staging["row_id"].tolist() == vivas
    assert set(resultado.ecl_term_structure["row_id"]) == set(vivas)
    assert resultado.detail["stage"].tolist() == [1, 2, 3]
    card = resultado.card
    assert (card.n_rows, card.n_stage1, card.n_stage2, card.n_stage3) == (3, 1, 1, 1)
    assert card.n_rows_without_exposure == 2
    assert int(resultado.summary["n_rows"].sum()) == 3
    assert card.total_ead == pytest.approx(2_600.0)

    # La ECL es la de las vivas solas, con la misma curva para cada una.
    solo_vivas = frame.loc[vivas]
    curva = _curva(list(frame.index))
    referencia = _calcular(solo_vivas, curva.loc[curva["row_id"].isin(vivas)])
    assert card.total_ecl_reported == pytest.approx(referencia.card.total_ecl_reported, rel=1e-12)
    assert referencia.card.n_rows_without_exposure == 0


def test_la_curva_no_necesita_cubrir_las_filas_sin_exposicion() -> None:
    """La cobertura se comprueba contra las operaciones activas (§3.5)."""
    frame = _cartera()
    resultado = _calcular(frame, _curva(["v1", "v2", "v3"]))
    assert resultado.card.n_rows == 3


def test_una_operacion_viva_sin_curva_sigue_deteniendo_la_corrida() -> None:
    frame = _cartera()
    with pytest.raises(IfrsTermStructureError, match="sin curva=\\['v2'\\]"):
        _calcular(frame, _curva(["v1", "h1", "h2", "v3"]))


def test_sin_ninguna_operacion_con_exposicion_la_corrida_se_detiene() -> None:
    frame = _cartera().assign(ead=0.0)
    with pytest.raises(IfrsInputError, match="exposición"):
        _calcular(frame, _curva(list(frame.index)))


def test_una_exposicion_invalida_en_cualquier_fila_sigue_deteniendo() -> None:
    """La EAD se calcula sobre todas las filas: es lo que decide cuáles son operaciones."""
    frame = _cartera()
    frame.loc["h1", "ead"] = -1.0
    with pytest.raises(Exception, match="no negativa"):
        _calcular(frame, _curva(list(frame.index)))


# ─────────────────────────── D-CRE-5: de punta a punta ───────────────────────────


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def paquete(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    from bayesrisk.ui import datasets

    ruta = datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))
    return pd.read_parquet(ruta)


def _argumentos(datos: Any, run_dir: Path, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "data": datos,
        "id": "loan_id",
        "as_of": "as_of_date",
        "portfolio": "portfolio",
        "exposure": "ead",
        "lgd": "lgd",
        "rate": "eir",
        "days_past_due": "days_past_due",
        "default": "is_default",
        "duration": "duration",
        "event": "event",
        "period": "year",
        "horizon": 5,
        "covariates": ["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"],
        "run_dir": run_dir,
    }
    base.update(cambios)
    return base


def _correr(datos: Any, run_dir: Path, **cambios: Any) -> Any:
    from bayesrisk.guided import Ecl

    ecl = Ecl(**_argumentos(datos, run_dir, **cambios))
    ecl._echo = lambda _texto: None
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


#: Las primeras 100 filas del paquete pasan a «cerradas»: EAD 0 y, una de ellas, LGD inválida.
_CERRADAS = 100


@pytest.fixture(scope="module")
def con_historia(
    paquete: pd.DataFrame, tmp_path_factory: pytest.TempPathFactory, _semilla: None
) -> tuple[Any, Any]:
    """La provisión del paquete tal cual y la misma con 100 filas cerradas (EAD 0)."""
    raiz = tmp_path_factory.mktemp("historia")
    base = _correr(paquete, raiz, name="base")
    cerrado = paquete.copy()
    cerrado.iloc[:_CERRADAS, cerrado.columns.get_loc("ead")] = 0.0
    cerrado.iloc[0, cerrado.columns.get_loc("lgd")] = 1.5
    return base, _correr(cerrado, raiz, name="con_historia")


def test_una_cartera_con_historia_cuenta_sus_operaciones_y_conserva_la_ecl(
    con_historia: tuple[Any, Any],
) -> None:
    """Gate 7 de la enmienda: conteos de §3.5 con una LGD inválida en una fila sin exposición."""
    base, ecl = con_historia
    card = ecl.study.artifacts.get("provisioning_ifrs9", "card")
    assert card.n_rows == 6_000 - _CERRADAS
    assert card.n_rows_without_exposure == _CERRADAS
    assert card.n_stage1 + card.n_stage2 + card.n_stage3 == card.n_rows
    # La curva se ajusta con el archivo completo, como antes: misma curva, misma ECL por operación.
    detalle_base = base.study.artifacts.get("provisioning_ifrs9", "detail")
    vivas = detalle_base.iloc[_CERRADAS:]
    assert float(card.total_ecl_reported) == pytest.approx(
        float(vivas["ecl_reported"].sum()), rel=1e-9
    )
    detalle = ecl.study.artifacts.get("provisioning_ifrs9", "detail")
    assert detalle["row_id"].tolist() == vivas["row_id"].tolist()


def test_cartera_dice_cuantas_filas_son_historia(con_historia: tuple[Any, Any]) -> None:
    """«Cartera» lo dice (§3.5): operaciones con exposición y filas que sólo son historia."""
    _base, ecl = con_historia
    resumen = ecl.summary("data")
    assert resumen.lines[1].startswith(
        "6.000 filas: 5.900 operaciones con exposición al corte; 100 sin exposición sólo aportan "
        "historia a la curva · fecha de corte 2025-06-30 · 4 carteras"
    ), resumen.lines[1]
    assert len(resumen.lines) <= 8
    assert int(ecl.results["data"]["Operaciones"].sum()) == 5_900


def test_sin_filas_de_historia_cartera_habla_como_antes(con_historia: tuple[Any, Any]) -> None:
    base, _ecl = con_historia
    lineas = base.summary("data").lines
    assert not any("sin exposición" in linea for linea in lineas)
    assert base.study.artifacts.get("provisioning_ifrs9", "card").n_rows_without_exposure == 0


# ───────────────────────── D-CRE-6: la curva identifica por la columna ─────────────────────────


def _historia_con_id() -> pd.DataFrame:
    """La historia de la curva con un identificador en COLUMNA, distinto del índice del archivo."""
    filas = []
    for posicion in range(120):
        if posicion < 12:
            duracion, evento = 1, 1
        elif posicion < 36:
            duracion, evento = 2, 1
        else:
            duracion, evento = 2, 0
        filas.append(
            {
                "operacion": f"OP-{1000 + posicion}",
                "duration": duracion,
                "event": evento,
                "mora": float(posicion % 4),
            }
        )
    return pd.DataFrame(filas)


def _survival_cfg(method: str, *, id_col: str | None = "operacion") -> Any:
    from bayesrisk.survival.config import (
        CoxAftConfig,
        SurvivalConfig,
        SurvivalInputConfig,
        SurvivalTimeGridConfig,
    )

    return SurvivalConfig(
        method=method,
        input=SurvivalInputConfig(
            duration_col="duration",
            event_col="event",
            pd_source="none",
            id_col=id_col,
            covariate_cols=() if method == "kaplan_meier" else ("mora",),
        ),
        time_grid=SurvivalTimeGridConfig(time_unit="year", horizon_periods=2),
        # Sin el test de Schoenfeld: su aviso de diagnóstico no es lo que aquí se mide.
        cox_aft=CoxAftConfig(ph_test_enabled=False),
        fail_on_falta_dato=False,
    )


def _curva_con_id(method: str, frame: pd.DataFrame, **cambios: Any) -> Any:
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.study import Study

    study = Study(BayesRiskConfig(survival=_survival_cfg(method, **cambios)))
    study.artifacts.set("data", "frame", frame)
    study.run(steps=["survival"])
    return study


@pytest.mark.parametrize("method", ["discrete_hazard", "cox_ph"])
def test_la_curva_publica_el_valor_de_la_columna_identificador(method: str) -> None:
    """D-CRE-6: con ``id_col``, cada artefacto por operación sale con el identificador del archivo,
    no con la posición de la fila (el índice), en todos los métodos que publican por operación."""
    frame = _historia_con_id()
    study = _curva_con_id(method, frame)
    esperados = set(frame["operacion"])
    for clave in ("term_structure", "survival_curves", "hazards"):
        tabla = study.artifacts.get("survival", clave)
        assert set(tabla["row_id"]) == esperados, clave
        primero = tabla.iloc[0]
        assert tabla.index[0] == f"{primero['row_id']}|{primero['period']}", clave


def test_sin_id_col_la_curva_sigue_identificando_por_el_indice() -> None:
    frame = _historia_con_id()
    study = _curva_con_id("discrete_hazard", frame, id_col=None)
    curva = study.artifacts.get("survival", "term_structure")
    assert set(curva["row_id"]) == {str(i) for i in frame.index}


def test_kaplan_meier_no_identifica_operaciones() -> None:
    """Kaplan-Meier publica una curva por segmento (``row_id`` vacío): no hay nada que traducir."""
    study = _curva_con_id("kaplan_meier", _historia_con_id())
    assert study.artifacts.get("survival", "term_structure")["row_id"].isna().all()


def test_un_identificador_repetido_se_nombra() -> None:
    from bayesrisk.survival.exceptions import SurvivalInputError

    frame = _historia_con_id()
    frame.loc[5, "operacion"] = "OP-1003"
    frame.loc[9, "operacion"] = "OP-1007"
    with pytest.raises(Exception) as excinfo:
        _curva_con_id("discrete_hazard", frame)
    causa: BaseException | None = excinfo.value
    while causa is not None and not isinstance(causa, SurvivalInputError):
        causa = causa.__cause__
    assert causa is not None, excinfo.value
    assert "OP-1003" in str(causa) and "OP-1007" in str(causa)


def _requisitos_de_identificador(survival_id: str | None, row_id_col: str | None) -> list[Any]:
    import bayesrisk
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.config.schema import cargar_configs_de_dominio
    from bayesrisk.ui.presets import ifrs9_preset

    cargar_configs_de_dominio()
    cfg = ifrs9_preset()["config"]
    cfg["survival"]["input"]["id_col"] = survival_id
    cfg["provisioning_ifrs9"]["row_id_col"] = row_id_col
    columnas = ["loan_id", "as_of_date", "portfolio", "ead", "lgd", "eir", "days_past_due"]
    columnas += ["is_default", "duration", "event", "utilizacion_linea", "deuda_ingreso"]
    columnas += ["antiguedad_meses", "target", "fecha_originacion"]
    resultado = bayesrisk.check_dataset(BayesRiskConfig.model_validate(cfg), columnas)
    return [
        m
        for m in resultado.mismatches
        if m.kind == "unmet_requirement" and m.path == "provisioning_ifrs9.row_id_col"
    ]


@pytest.mark.parametrize(
    ("survival_id", "row_id_col"),
    [("loan_id", None), (None, "loan_id"), ("loan_id", "operacion")],
)
def test_curva_y_provision_con_identificadores_distintos_se_detienen_antes_de_correr(
    survival_id: str | None, row_id_col: str | None
) -> None:
    """D-CRE-6: si una declara la columna y la otra no, o declaran distintas, no se encontrarían."""
    (aviso,) = _requisitos_de_identificador(survival_id, row_id_col)
    assert "identific" in aviso.message
    assert "row_id_col" not in aviso.message and "id_col" not in aviso.message


@pytest.mark.parametrize(("survival_id", "row_id_col"), [(None, None), ("loan_id", "loan_id")])
def test_curva_y_provision_con_el_mismo_identificador_no_avisan(
    survival_id: str | None, row_id_col: str | None
) -> None:
    assert _requisitos_de_identificador(survival_id, row_id_col) == []


def test_en_la_corrida_sin_preflight_el_desencuentro_se_explica() -> None:
    """Por código no pasa por el preflight: el motor dice por qué no se encuentran."""
    frame = _cartera()
    curva = _curva(["fila-0", "fila-1", "fila-2", "fila-3", "fila-4"])
    with pytest.raises(IfrsTermStructureError, match="identifican las operaciones"):
        _calcular(frame, curva)


def _intro_ifrs9(card: dict[str, Any]) -> str:
    from datetime import UTC, datetime

    from bayesrisk.core.lineage import LineageBundle
    from bayesrisk.report import prose
    from bayesrisk.report.results import ReportInputBundle

    lineage = LineageBundle(
        git_sha="abc123",
        git_dirty=False,
        data_hash="d" * 16,
        config_hash="c" * 16,
        root_seed=42,
        uv_lock_hash="uv123",
        library_versions={"bayesrisk": "0.1.0"},
        determinism_caveats=[],
        created_at=datetime(2026, 10, 6, tzinfo=UTC),
        schema_version="1.0.0",
    )
    bundle = ReportInputBundle(
        lineage=lineage,
        cards={"provisioning_ifrs9": card},
        tables={},
        figures={},
        sections=(),
    )
    return " ".join(prose.ifrs9_intro(bundle))


def test_el_capitulo_ifrs9_dice_las_filas_de_historia_solo_si_las_hay() -> None:
    """D-CRE-5 en el informe: el conteo es de operaciones; la historia se dice aparte."""
    base = {
        "total_ecl_reported": 10.0,
        "total_ead": 100.0,
        "n_rows": 3,
        "n_stage1": 1,
        "n_stage2": 1,
        "n_stage3": 1,
        "as_of_date": "2026-03-31",
    }
    sin_historia = _intro_ifrs9(base)
    assert "De las 3 operaciones de la cartera" in sin_historia
    assert "historia" not in sin_historia
    con_historia = _intro_ifrs9({**base, "n_rows_without_exposure": 2})
    assert (
        "Otras 2 filas del archivo, sin exposición al corte, sólo aportan historia a la curva "
        "de PD." in con_historia
    )
