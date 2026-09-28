"""El motivo de una decisión del motor, legible sin tocar el motor (CIFRAS-EN-PANTALLA, D-PAN-4).

Tres cosas: (1) el texto legible se **compone** de la observación y el umbral originales —nunca
parseando el ``detail``, que ya redondeó a seis cifras— y conserva el lado del corte; (2) el gate de
catálogo, en los dos sentidos: cada productor numérico del ``detail`` en ``selector.py`` y
``estimator.py`` tiene su composición y cada composición, su productor; (3) los tramos del EDA se
reescriben sólo en las columnas que el perfilador declaró numéricas.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from bayesrisk.core.tramos import rotulo_de_intervalo
from bayesrisk.eda.config import UnivariateConfig
from bayesrisk.eda.univariate import UnivariateProfiler
from bayesrisk.report.cifras import (
    CRITERIOS_CON_PVALOR,
    MOTIVOS_DE_SELECCION,
    PARTES_DEL_CRITERIO,
    PREFIJO_CONTRIBUCION_IV,
    frente_al_corte,
    motivo_legible,
    motivo_legible_stepwise,
    pvalor,
)

_RAIZ = Path(__file__).resolve().parents[2]
_SELECTOR = _RAIZ / "src" / "bayesrisk" / "selection" / "selector.py"
_ESTIMADOR = _RAIZ / "src" / "bayesrisk" / "model" / "estimator.py"

_UMBRALES = {"min_iv": 0.02, "max_iv": 0.5, "correlation.threshold": 0.9, "vif.threshold": 5}


# --- (1) la composición --------------------------------------------------------------------


def test_el_motivo_se_compone_de_los_valores_originales_no_del_detail() -> None:
    fila = {"reason": "low_iv", "detail": "iv=2.94993e-05 < min_iv=0.02", "iv": 2.949932e-05}
    assert motivo_legible(fila, _UMBRALES) == "IV 0,000029 < mínimo 0,02"
    fila = {
        "reason": "high_correlation",
        "detail": "|rho|=0.93122 > threshold=0.9",
        "max_abs_corr": 0.931224,
        "max_corr_with": "deuda_ingreso",
    }
    assert motivo_legible(fila, _UMBRALES) == "correlación 0,9312 > máximo 0,90 con deuda_ingreso"
    fila = {"reason": "high_vif", "detail": "vif=5.12346 > threshold=5", "vif": 5.1234567}
    assert motivo_legible(fila, _UMBRALES) == "VIF 5,1235 > máximo 5,00"


def test_un_corte_que_empata_a_seis_cifras_se_escribe_distinto_y_del_lado_correcto() -> None:
    """Pasada 3 de Codex sobre el diseño: con ``iv=0.2499402`` y ``min_iv=0.2499404`` el ``detail``
    dice ``iv=0.24994 < min_iv=0.24994``, una comparación imposible."""
    fila = {"reason": "low_iv", "detail": "iv=0.24994 < min_iv=0.24994", "iv": 0.2499402}
    texto = motivo_legible(fila, {"min_iv": 0.2499404})
    assert texto == "IV 0,2499 < mínimo 0,2499404"
    # Y cuando el redondeo de la observación caería sobre el corte, gana decimales.
    fila = {"reason": "low_iv", "detail": "iv=0.249958 < min_iv=0.24996", "iv": 0.249958}
    assert motivo_legible(fila, {"min_iv": 0.24996}) == "IV 0,249958 < mínimo 0,24996"


def test_frente_al_corte_conserva_el_orden() -> None:
    # 0.0499555 a cinco decimales es 0,04996: sobre un corte de 0,049956 que no alcanza.
    assert frente_al_corte("0,04996", 0.0499555, 0.049956) == "0,0499555"
    assert frente_al_corte(pvalor(0.2), 0.2, 0.05) == "0,200"
    assert frente_al_corte("1.234,57", 1234.567, 1234.5671) == "1.234,567"


@pytest.mark.parametrize(
    "fila",
    [
        # Una desplazada por force_include también es `high_correlation`, con otro texto.
        {
            "reason": "high_correlation",
            "detail": "desplazada por force_include",
            "max_abs_corr": 0.95,
        },
        {"reason": "low_auc", "detail": None, "auc": 0.51},
        {"reason": "low_iv", "detail": "iv=0.01 < min_iv=0.02", "iv": None},
    ],
)
def test_sin_composicion_o_sin_valores_no_se_inventa(fila: dict[str, object]) -> None:
    assert motivo_legible(fila, _UMBRALES) is None


def test_un_umbral_ausente_deja_el_detail_crudo() -> None:
    fila = {"reason": "high_vif", "detail": "vif=6 > threshold=5", "vif": 6.0}
    assert motivo_legible(fila, {}) is None


def test_el_stepwise_se_compone_de_su_p_valor_y_su_umbral() -> None:
    fila = {
        "criterion": "wald_pvalue",
        "detail": "wald_p=0.0123, lr_p=0.0200",
        "p_value": 0.0123,
        "lr_stat": 6.2,
        "threshold": 0.05,
    }
    assert motivo_legible_stepwise(fila) == (
        "p-valor 0,012 (Wald 0,012; razón de verosimilitud 0,020); umbral 0,05; "
        "estadístico LR 6,2000"
    )
    fila = {
        "criterion": "iv_contribution",
        "detail": "iv_contribution=0.00123456",
        "threshold": 0.001,
    }
    assert motivo_legible_stepwise(fila) == "contribución al IV 0,0012 > máximo 0,001"
    # Un p-valor bajo 0,001 frente a un corte menor no se escribe «< 0,001»: no diría el lado.
    fila = {"criterion": "lr_test", "detail": "x", "p_value": 0.0004, "threshold": 0.0005}
    assert motivo_legible_stepwise(fila) == "p-valor 0,00040; umbral 0,0005"
    assert motivo_legible_stepwise({"criterion": "sign", "detail": "sign_policy=fail"}) is None


# --- (2) el gate de catálogo -------------------------------------------------------------


def _prefijo(nodo: ast.JoinedStr) -> str:
    primero = nodo.values[0] if nodo.values else None
    return (
        primero.value
        if isinstance(primero, ast.Constant) and isinstance(primero.value, str)
        else ""
    )


def _productores(ruta: Path) -> tuple[set[tuple[str | None, str]], set[str]]:
    """Las f-strings que escriben un ``detail``: (motivo si se sabe, prefijo) y los prefijos que
    ``_criterion_detail`` agrega a su lista."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    pares: set[tuple[str | None, str]] = set()
    partes: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if kw.arg == "detail" and isinstance(kw.value, ast.JoinedStr):
                    motivo = next(
                        (
                            a.value
                            for a in nodo.args
                            if isinstance(a, ast.Constant) and isinstance(a.value, str)
                        ),
                        None,
                    )
                    pares.add((motivo, _prefijo(kw.value)))
        if (
            isinstance(nodo, ast.Assign)
            and isinstance(nodo.value, ast.JoinedStr)
            and any(isinstance(t, ast.Attribute) and t.attr == "detail" for t in nodo.targets)
        ):
            pares.add((None, _prefijo(nodo.value)))
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "_criterion_detail":
            for interno in ast.walk(nodo):
                # Las partes que agrega a su lista (no los `format_spec` anidados, que también son
                # `JoinedStr`).
                if (
                    isinstance(interno, ast.Call)
                    and isinstance(interno.func, ast.Attribute)
                    and interno.func.attr == "append"
                    and interno.args
                    and isinstance(interno.args[0], ast.JoinedStr)
                ):
                    partes.add(_prefijo(interno.args[0]))
    return pares, partes


def test_cada_productor_numerico_del_detail_tiene_su_composicion_y_al_reves() -> None:
    pares_seleccion, _ = _productores(_SELECTOR)
    pares_modelo, partes_modelo = _productores(_ESTIMADOR)

    prefijos_de_motivo = {
        motivo: prefijo for motivo, (_, _, _, prefijo) in MOTIVOS_DE_SELECCION.items()
    }
    # Cada `_exclude(state, "<motivo>", detail=f"…")` casa con la composición de su motivo.
    for motivo, prefijo in pares_seleccion:
        if motivo is not None:
            assert prefijos_de_motivo.get(motivo) == prefijo, (motivo, prefijo)
    # Todo prefijo que escribe el selector tiene composición, y toda composición tiene productor.
    assert {prefijo for _, prefijo in pares_seleccion} == set(prefijos_de_motivo.values())

    # El modelo: la contribución de IV y los p-valores de `_criterion_detail`.
    assert {prefijo for _, prefijo in pares_modelo} == {PREFIJO_CONTRIBUCION_IV}
    assert partes_modelo == set(PARTES_DEL_CRITERIO)
    assert frozenset({"wald_pvalue", "lr_test", "both"}) == CRITERIOS_CON_PVALOR


def test_el_gate_de_catalogo_caza_un_productor_nuevo(tmp_path: Path) -> None:
    fuente = _SELECTOR.read_text(encoding="utf-8") + (
        '\n\ndef _nuevo(state):\n    _exclude(state, "low_auc", detail=f"auc={state.auc:.6g}")\n'
    )
    falso = tmp_path / "selector.py"
    falso.write_text(fuente, encoding="utf-8")
    pares, _ = _productores(falso)
    assert ("low_auc", "auc=") in pares
    assert {p for _, p in pares} != {p for (_, _, _, p) in MOTIVOS_DE_SELECCION.values()}


# --- (3) los tramos del EDA, por procedencia ---------------------------------------------


def test_sólo_los_tramos_de_una_numerica_se_reescriben() -> None:
    frame = pd.DataFrame(
        {
            "monto": [0.5, 1.0, 1.25, 2.0, 3.0, 4.0, 5.0, 6.0] * 5,
            # Una categórica cuyo nivel literal tiene forma de intervalo.
            "segmento": ["(0.5, 1.25]", "B"] * 20,
            "bad": [0, 1, 0, 0, 1, 0, 0, 1] * 5,
        }
    )
    frame["bad"] = frame["bad"].astype("Int64")
    resultado = UnivariateProfiler(UnivariateConfig(n_quantile_bins=4)).profile(
        frame, target_col="bad", columns=("monto", "segmento")
    )
    assert resultado.numeric_profiles == ("monto",)
    tramo_numerico = str(resultado.profiles["monto"]["tramo"].iloc[0])
    assert rotulo_de_intervalo(tramo_numerico).startswith(">")
    assert "(0.5, 1.25]" in set(resultado.profiles["segmento"]["tramo"].astype(str))


# --- pasada 1 de Codex sobre el código ------------------------------------------------------


def test_en_la_igualdad_la_cifra_escrita_tambien_dice_el_corte() -> None:
    fila = {"reason": "high_iv", "detail": "iv=0.24994 >= max_iv=0.24994", "iv": 0.24994}
    assert motivo_legible(fila, {"max_iv": 0.24994}) == "IV 0,24994 ≥ máximo 0,24994"


def test_una_contribucion_de_iv_que_las_seis_cifras_no_ubican_no_se_compara() -> None:
    """El motor registra la contribución que SUPERA el corte; su valor exacto no viaja."""
    fila = {"criterion": "iv_contribution", "detail": "iv_contribution=0.24994"}
    assert motivo_legible_stepwise({**fila, "threshold": 0.2499403}) is None
    fila = {"criterion": "iv_contribution", "detail": "iv_contribution=0.31", "threshold": 0.25}
    assert motivo_legible_stepwise(fila) == "contribución al IV 0,3100 > máximo 0,25"


def test_los_resumenes_escriben_la_observacion_frente_a_su_corte() -> None:
    from bayesrisk.guided.summaries import _corte_pct, _frente, _pvalor_frente

    assert _frente(0.249962, 0.24996) == "0,249962"
    assert _frente(0.3, 0.25) == "0,3000"
    assert _frente(None, 0.25) == "No disponible"
    assert _pvalor_frente(0.0499555, 0.049956) == "0,0499555"
    assert _pvalor_frente(0.0004, 0.0005) == "0,00040"
    # Un corte que es proporción se escribe exacto, no redondeado a entero.
    assert _corte_pct(0.255) == "25,5 %"


def test_con_both_se_conservan_los_p_valores_de_cada_prueba() -> None:
    """Pasada 3 de Codex sobre el código: con `both`, `p_value` es el mayor y no dice cuál."""
    fila = {
        "criterion": "both",
        "detail": "wald_p=0.0123, lr_p=0.0456",
        "p_value": 0.0456,
        "lr_stat": 4.0,
        "threshold": 0.05,
    }
    texto = motivo_legible_stepwise(fila)
    assert texto is not None
    assert "Wald 0,012" in texto and "razón de verosimilitud 0,046" in texto
    # El que coincide con el p-valor del criterio se escribe con su exacto, frente al corte.
    fila = {
        "criterion": "both",
        # El motor escribe `:.6g`: 0.05000041 sale «0.0500004»; su exacto está en `p_value`.
        "detail": "wald_p=0.01, lr_p=0.0500004",
        "p_value": 0.05000041,
        "lr_stat": 4.0,
        "threshold": 0.05,
    }
    texto = motivo_legible_stepwise(fila)
    # La prueba que decidió y el p-valor del criterio se leen igual: los dos desde el exacto.
    assert texto is not None and texto.startswith("p-valor 0,0500004 (")
    assert "razón de verosimilitud 0,0500004)" in texto
    # Un `detail` que no es el de `_criterion_detail` no se adivina.
    fila = {"criterion": "wald_pvalue", "detail": "otro", "p_value": 0.01, "threshold": 0.05}
    assert motivo_legible_stepwise(fila) == "p-valor 0,010; umbral 0,05"
