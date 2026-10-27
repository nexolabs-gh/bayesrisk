"""D-DOC-SC: significado, procedencia y conservación del snapshot editorial."""

from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from bayesrisk.report._documentary import (
    EditorialSnapshot,
    build_reading,
    iv_reading,
    trend_label,
)


def _model() -> dict:
    return {
        "final_features": ["ingreso"],
        "iv_contribution_flags": ["ingreso"],
        "thresholds": {"iv_contribution.threshold": 0.9},
    }


def _coefficients(value: float = 0.5143031291926708) -> pd.DataFrame:
    return pd.DataFrame({"feature": ["ingreso"], "iv_contribution": [value]})


def _event(**changes: object) -> dict:
    return {
        "regla": "model_iv_contribution",
        "umbral": 0.9,
        "valor": {"feature": "ingreso", "iteration": 2, "iv_contribution": 1.0, **changes},
        "accion": "flag",
    }


def test_iv_historico_no_se_convierte_en_alarma_final() -> None:
    before = _coefficients()
    facts = iv_reading(_model(), before, (_event(),))
    text = " ".join(f.text for f in facts)
    assert "durante la construcción" in text
    assert "iteración 2" in text and "100,00" in text
    assert "51,43" in text and "no supera" in text
    assert "Contribución final al IV superior" not in text
    pd.testing.assert_frame_equal(before, _coefficients(), check_exact=True)
    assert any(f.value == 0.5143031291926708 for f in facts)
    assert any(f.value == 1.0 and f.moment == "iteration:2" for f in facts)


@pytest.mark.parametrize("value,exceeds", [(0.9, False), (0.9000001, True)])
def test_iv_usa_mayor_estricto_sin_confundir_la_frontera_sospechosa(value, exceeds) -> None:
    text = " ".join(f.text for f in iv_reading(_model(), _coefficients(value), ()))
    assert ("Contribución final al IV superior al umbral" in text) is exceeds
    assert "momento no identificado" in text


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_iv_no_finito_no_se_declara_resuelto(value) -> None:
    text = " ".join(f.text for f in iv_reading(_model(), _coefficients(value), (_event(),)))
    assert "Comparación final no disponible" in text
    assert "no supera" not in text and "resuelta" not in text


def test_iv_sin_umbral_no_inventa_default_y_evento_sin_momento_no_duplica_historia() -> None:
    model = _model()
    model["thresholds"] = {}
    events = (_event(), {"regla": "model_iv_contribution", "valor": "ingreso"})
    facts = iv_reading(model, _coefficients(), events)
    assert sum(f.moment == "iteration:2" for f in facts) == 1
    text = " ".join(f.text for f in facts)
    assert "Comparación final no disponible" in text and "umbral" in text


def test_evento_de_variable_excluida_es_solo_historia() -> None:
    facts = iv_reading(_model(), _coefficients(), (_event(feature="excluida"),))
    text = " ".join(f.text for f in facts if "excluida" in f.id)
    assert "no quedó en el modelo final" in text
    assert "Contribución final" not in text


def test_tendencia_distingue_categorica_y_metadato_ausente() -> None:
    assert trend_label(None, "categorical") == "No aplica el diagnóstico de tendencia numérica"
    assert trend_label(None, None) == "No disponible"
    assert "descendente" in trend_label("descending", "numerical")


def _snapshot() -> EditorialSnapshot:
    return EditorialSnapshot(
        cards={
            "model": _model(),
            "data": {
                "n_rows": 10,
                "class_counts": {"bueno": 6, "malo": 2, "indeterminado": 2},
                "bad_rate": 0.25,
            },
            "stability": {
                "comparisons": ["dev_vs_holdout"],
                "max_psi_by_comparison": {"dev_vs_holdout": 0.0132},
                "psi_metric_by_comparison": {"dev_vs_holdout": "pd_psi"},
                "bands_by_comparison": {"dev_vs_holdout": "stable"},
                "stable_threshold": 0.1,
                "review_threshold": 0.25,
            },
            "performance": {
                "partitions": ["oot"],
                "thresholds": {},
                "max_metrics_by_partition": {"oot": {"auc": 0.6560957827097084}},
                "bands_by_partition": {"oot": "ok"},
            },
        },
        tables={
            "model.coefficients": _coefficients(),
            "master_scale.grade_table": pd.DataFrame(
                [
                    {
                        "sample": "oot",
                        "grade": 1,
                        "pd": 0.0477,
                        "bad_rate": 0.1185,
                        "traffic_light": "red",
                        "n": 100,
                    },
                    {
                        "sample": "holdout",
                        "grade": 1,
                        "pd": 0.0477,
                        "bad_rate": 0.09,
                        "traffic_light": "amber",
                        "n": 100,
                    },
                ]
            ),
            "binning.event_rate_by_partition": pd.DataFrame(
                [
                    {
                        "feature": "ingreso",
                        "partition": "oot",
                        "inverts": True,
                        "n": 40,
                        "event_rate": 0.2,
                    },
                ]
            ),
        },
        events=(_event(),),
        scope="run_end",
    )


def test_lectura_nombra_psi_muestras_cortes_sin_inferencia_global() -> None:
    snapshot = _snapshot()
    text = " ".join(build_reading(snapshot).lines("stability"))
    assert "PD" in text and "Holdout" in text and "Desarrollo" in text
    assert "0,0132" in text and "0,10" in text
    assert "no hay desplazamiento" not in text
    assert "no acredita" in text


def test_desempeno_sin_umbral_es_neutral_aunque_fuente_diga_ok() -> None:
    snap = _snapshot()
    before = copy.deepcopy(snap.cards)
    text = " ".join(build_reading(snap).lines("performance"))
    assert "Sin umbrales de alerta configurados" in text
    assert "0,656" in text
    assert snap.cards == before


def test_denominador_es_elegibles_no_tamano_del_archivo() -> None:
    reading = build_reading(_snapshot())
    text = " ".join(reading.lines("data"))
    assert "10 filas" in text and "8 elegibles" in text and "2 malos" in text
    assert "25,00" in text


def test_escala_incluye_rojo_y_ambar_sin_reclasificar_hl() -> None:
    reading = build_reading(_snapshot())
    text = " ".join(reading.review)
    assert "Escala maestra" in text and "Fuera de tiempo" in text and "Holdout" in text
    assert "11,85" in text and "4,77" in text and "Ámbar" in text
    assert "no son grupos HL" in text


def test_informe_temprano_no_adopta_resultados_de_etapas_pendientes() -> None:
    snapshot = _snapshot()
    snapshot.scope = "report"
    snapshot.pending_stages = ("validation", "master_scale")
    reading = build_reading(snapshot)
    text = " ".join(reading.review)
    assert "Validación pendiente de ejecución al emitir este informe" in text
    assert "11,85" not in text
    dto = reading.to_dict()
    assert dto["schema_version"] == 1 and dto["emission_scope"] == "report"
    assert dto["pending_stages"] == ["validation", "master_scale"]


def test_todos_los_hechos_tienen_fuente_y_destino_sin_mutacion() -> None:
    snap = _snapshot()
    before = copy.deepcopy(snap.cards)
    reading = build_reading(snap)
    dto = reading.to_dict()
    ids = {f["id"] for f in dto["facts"]}
    assert len(ids) == len(dto["facts"])
    assert ids == {d["fact_id"] for d in dto["evidence_index"]}
    assert all(
        f["source"]["domain"] and f["source"]["key"] and f["source"]["selector"]
        for f in dto["facts"]
    )
    assert build_reading(snap).to_dict() == dto
    assert snap.cards == before


def test_iv_source_apunta_al_evento_estructurado_y_reason_conserva_su_semantica() -> None:
    event = {**_event(), "run_id": "corrida-actual"}
    reading = build_reading(
        EditorialSnapshot(
            cards={"model": _model()},
            tables={"model.coefficients": _coefficients()},
            events=(event,),
        )
    )
    history = next(f for f in reading.to_dict()["facts"] if f["moment"] == "iteration:2")
    assert history["source"]["domain"] == "audit"
    assert history["source"]["key"] == "trail"
    assert json.loads(history["source"]["selector"])["run_id"] == "corrida-actual"
    assert history["reason"] is None
    assert all(d["section_id"] is None for d in reading.to_dict()["evidence_index"])


def test_flag_excluido_sin_historia_no_desaparece() -> None:
    model = _model()
    model["iv_contribution_flags"] = ["excluida"]
    facts = iv_reading(model, _coefficients())
    assert len(facts) == 1
    assert "momento no identificado" in facts[0].text
    assert "no quedó en el modelo final" in facts[0].text


def test_modelo_pendiente_no_filtra_eventos_futuros_al_snapshot() -> None:
    snap = _snapshot()
    snap.pending_stages = ("model",)
    assert not any(f.id.startswith("iv.") for f in build_reading(snap).facts)


def test_tasa_por_particion_conserva_el_denominador_original_y_vacio_no_es_cero() -> None:
    snap = EditorialSnapshot(
        cards={
            "data": {
                "partition_sizes": {"fuera_de_modelo": 10, "oot": 0},
                "partition_bad_rates": {"fuera_de_modelo": 0.2, "oot": 0},
            }
        }
    )
    text = " ".join(build_reading(snap).lines("data"))
    assert "20,00 % sobre las filas de la muestra" in text
    assert "elegibles" not in text and "malos 0,00 %" not in text
    assert "tasa no aplicable" in text


def test_umbrales_reservados_no_activan_alertas_de_discriminacion() -> None:
    snap = _snapshot()
    snap.cards["performance"]["thresholds"] = {"psi_max": 0.2, "csi_max": 0.3}
    assert "Sin umbrales de alerta configurados" in " ".join(build_reading(snap).review)


def test_umbral_iv_se_escribe_exacto_y_observacion_no_cruza_el_corte() -> None:
    card = _model()
    card["thresholds"] = {"iv_contribution.threshold": 0.90511}
    text = " ".join(f.text for f in iv_reading(card, _coefficients(0.9051101)))
    assert "90,511 %" in text and "90,51101 % > 90,511 %" in text


def test_eda_sin_denominador_lo_declara_no_disponible() -> None:
    snap = EditorialSnapshot(cards={"eda": {"n_periods": 0}})
    fact = build_reading(snap).facts[0]
    assert fact.availability == "unavailable" and fact.value is None
    assert fact.reason == "denominador temporal no disponible"
