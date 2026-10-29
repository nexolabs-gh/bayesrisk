"""Composición interna D-DOC-SC; las tablas fuente nunca pasan por el formateo de lectura."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from bayesrisk.report.cifras import cifra, conteo, porcentaje
from bayesrisk.report.document import APPENDIX_TABLES_ID, ATTACHMENT_ONLY_TABLES, table_title


def scorecard_document(bundle: Any) -> bool:
    family = (bundle.summary or {}).get("family")
    if family:
        return bool(family == "scorecard")
    return any(d in bundle.cards for d in ("binning", "model", "scorecard", "performance"))


def support_id(key: str) -> str:
    return "evidence-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def exact_cell(value: Any) -> str:
    """Representación de soporte, sin redondeos ni confusión entre ausencia y cero."""
    if value is None:
        return "None (ausente)"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if getattr(value, "ndim", 0) > 0 and hasattr(value, "tolist"):
        value = value.tolist()
    elif hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN (no disponible)"
        if math.isinf(value):
            return "-inf" if value < 0 else "+inf"
        return repr(value)
    if isinstance(value, Mapping | list | tuple):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return str(value)


def _split_columns(table: dict[str, Any]) -> list[dict[str, Any]]:
    """Bloques de hasta seis columnas; fila fuente e identificador repetidos al continuar."""
    columns = table["columns"]
    if len(columns) <= 6:
        return [table]
    fixed = [0]
    if len(columns) > 1:
        fixed.append(1)
    remaining = list(range(2, len(columns)))
    chunks = [remaining[i : i + 4] for i in range(0, len(remaining), 4)]
    blocks = []
    for i, chunk in enumerate(chunks):
        positions = fixed + chunk
        blocks.append(
            {
                **table,
                "html_id": table["html_id"] + (f"-block-{i + 1}" if i else ""),
                "title": f"{table['title']} · bloque {i + 1}/{len(chunks)}",
                "columns": [columns[p] for p in positions],
                "numeric": [table["numeric"][p] for p in positions],
                "rows": [tuple(row[p] for p in positions) for row in table["rows"]],
                "source_columns": [
                    table.get("source_columns", list(range(len(columns))))[p] for p in positions
                ],
            }
        )
    return blocks


def support_tables(key: str, frame: Any, ordinal: int) -> list[dict[str, Any]]:
    """Todos los índices, columnas y valores, incluso vacíos y columnas homónimas."""
    if not all(hasattr(frame, attribute) for attribute in ("index", "columns", "itertuples")):
        from bayesrisk.report.exceptions import ReportRenderError

        raise ReportRenderError(f"Tabla no renderizable: {key}")
    index_names = list(frame.index.names)
    columns = [
        "Fila fuente",
        *(f"Índice: {n or i + 1}" for i, n in enumerate(index_names)),
        *(str(c) for c in frame.columns),
    ]
    source_columns = [
        "row",
        *(f"index:{i}" for i in range(len(index_names))),
        *(f"column:{i}" for i in range(len(frame.columns))),
    ]
    rows = []
    for position, (index, values) in enumerate(
        zip(frame.index, frame.itertuples(index=False, name=None), strict=True)
    ):
        indices = index if len(index_names) > 1 else (index,)
        rows.append(
            (str(position + 1), *(exact_cell(v) for v in indices), *(exact_cell(v) for v in values))
        )
    numeric = [
        True,
        *([False] * len(index_names)),
        *[bool(frame.iloc[:, i].dtype.kind in "iuf") for i in range(len(frame.columns))],
    ]
    title = table_title(key).removesuffix(": soporte íntegro")
    table = {
        "key": key,
        "title": f"E{ordinal:03d} · {title} — soporte íntegro",
        "html_id": support_id(key),
        "columns": columns,
        "source_columns": source_columns,
        "numeric": numeric,
        "rows": rows,
        "support": True,
        "total_rows": len(frame),
        "shown_rows": len(frame),
        "truncated": False,
        "total_rows_label": conteo(len(frame)),
        "shown_rows_label": conteo(len(frame)),
        "links": [
            {"href": "#section-executive_summary", "label": "Volver a Resultados del scorecard"}
        ],
    }
    return _split_columns(table)


def compose_scorecard(document: dict[str, Any], bundle: Any, config: Any) -> dict[str, Any]:
    """Una entrada, soporte íntegro y referencias compatibles para todos los renderers."""
    from bayesrisk.guided.summaries import RESUMEN_FINAL_ROTULOS
    from bayesrisk.report._documentary import reading_from_bundle
    from bayesrisk.report._documentary_tables import DETAIL_SUMMARIES, reading_projection

    document["documentary"] = scorecard_document(bundle)
    if not document["documentary"]:
        return document
    missing_cover = [field["label"] for field in document["cover"] if not field["filled"]]
    document["cover"] = [field for field in document["cover"] if field["filled"]]
    document["cover_kicker"] = "Resultados del scorecard"
    views = document["sections"]
    entry = next((s for s in views if s["kind"] == "summary"), None)
    reading = reading_from_bundle(bundle)
    if entry is None:
        entry = {
            "id": "executive_summary",
            "html_id": "section-executive_summary",
            "kind": "summary",
            "level": 1,
            "number": "",
            "title": "Resultados del scorecard",
            "status": "included",
            "source": "snapshot",
            "body": [],
            "placeholder": None,
            "payload_items": [],
            "metric_items": [],
            "tables": [],
            "charts": [],
            "data_exports": None,
            "narration": None,
            "summary": {
                "labels": dict(RESUMEN_FINAL_ROTULOS),
                "sin_alertas": "Sin hallazgos disponibles",
                "sin_decisiones": "Sin decisiones registradas",
                "error": None,
                "assumptions": None,
                "final": {
                    "execution": "Estado de ejecución no disponible en este snapshot",
                    "validation": "Lectura limitada a las fuentes disponibles",
                    "figures": [
                        (metric["label"] + " · " + metric["scope"], metric["value"])
                        for metric in document["executive"]["metrics"]
                    ],
                    "review": list(reading.review),
                    "decisions": [],
                    "files": [],
                },
            },
        }
        views.insert(0, entry)
    entry["title"] = "Resultados del scorecard"
    entry["summary"] = copy.deepcopy(entry["summary"])
    entry["documentary"] = True
    entry["body"] = [
        "Estado al emitir el informe. Borrador automático para revisión institucional."
    ]
    final = entry["summary"].get("final")
    files = copy.deepcopy(final.get("files", [])) if isinstance(final, Mapping) else []
    if isinstance(final, dict):
        final["files"] = []
    entry["links"] = []
    appendix = next((s for s in views if s["id"] == APPENDIX_TABLES_ID), None)
    if appendix is None:
        appendix = {
            **entry,
            "id": APPENDIX_TABLES_ID,
            "html_id": "section-appendix_tables",
            "title": "Evidencia íntegra",
            "kind": "appendix",
            "number": "",
            "body": [],
            "summary": None,
            "links": [],
            "tables": [],
        }
        views.append(appendix)
    appendix["title"] = "Evidencia íntegra"
    appendix["body"] = [
        "Tablas originales completas. Los valores de soporte conservan su precisión y sus índices; "
        "cada bloque repite la fila fuente para unir sus columnas."
    ]
    source_tables = {k: v for k, v in bundle.tables.items() if k not in ATTACHMENT_ONLY_TABLES}
    supports = {
        key: support_tables(key, frame, i + 1)
        for i, (key, frame) in enumerate(sorted(source_tables.items()))
    }
    import pandas as pd

    def add_support(key: str, frame: Any, title: str) -> str:
        blocks = support_tables(key, frame, len(supports) + 1)
        for i, block in enumerate(blocks):
            block["title"] = title + (f" · bloque {i + 1}/{len(blocks)}" if len(blocks) > 1 else "")
        supports[key] = blocks
        return str(blocks[0]["html_id"])

    # Los payloads editoriales del anexo redondean. Este soporte toma los valores originales.
    card_targets = {
        domain: add_support(
            "documentary.card." + domain,
            pd.DataFrame(_scalar_rows(card), columns=("Campo fuente", "Valor"), dtype=object),
            f"Metadatos originales · {domain}",
        )
        for domain, card in sorted(bundle.cards.items())
    }
    interpretation_target = None
    if getattr(bundle, "validation_interpretation", None) is not None:
        interpretation_target = add_support(
            "documentary.validation_interpretation",
            pd.DataFrame(
                _scalar_rows(bundle.validation_interpretation),
                columns=("Campo fuente", "Valor"),
                dtype=object,
            ),
            "Soporte original de la interpretación contextual de validación",
        )
    raw = final.get("documentary_reading") if isinstance(final, Mapping) else None
    dto = (
        copy.deepcopy(dict(raw))
        if isinstance(raw, Mapping) and raw.get("schema_version") == 1
        else reading.to_dict()
    )
    fact_rows = [
        (
            f["id"],
            f["source"]["domain"] + "." + f["source"]["key"],
            f["source"]["selector"],
            f["value"],
            f["moment"],
            f["availability"],
            f.get("reason"),
            f.get("population"),
            f.get("unit"),
        )
        for f in dto["facts"]
    ]
    fact_target = add_support(
        "documentary.facts",
        pd.DataFrame(
            fact_rows,
            dtype=object,
            columns=(
                "Hecho",
                "Fuente",
                "Selector",
                "Valor registrado",
                "Momento",
                "Disponibilidad",
                "Causa",
                "Población",
                "Unidad",
            ),
        ),
        "Extracto de hechos de la lectura · no sustituye el registro de auditoría completo",
    )
    dto["evidence_index"] = []
    for fact in dto["facts"]:
        source = fact["source"]
        key = source["domain"] + "." + source["key"]
        table_key = "eda.default_rate.by_period" if key == "eda.default_rate" else key
        target = support_id(table_key) if table_key in source_tables else None
        if key == "validation.interpretation":
            target = interpretation_target
        if (
            target is None
            and source["domain"] in card_targets
            and source["key"]
            in {
                "card",
                "data_card",
                "eda_card",
                "binning_card",
                "model_card",
                "selection_card",
                "summary",
            }
        ):
            target = card_targets[source["domain"]]
        dto["evidence_index"].append(
            {
                "fact_id": fact["id"],
                "artifact_key": key,
                "section_id": target or fact_target,
                "local_path": None,
            }
        )
    document["documentary_reading"] = dto
    for section in views:
        section["documentary"] = True
        for chart in section["charts"]:
            chart["documentary"] = True
            key = chart.get("source_key")
            if key in supports:
                chart["links"] = [
                    {"href": "#" + support_id(key), "label": supports[key][0]["title"]}
                ]
                if chart.get("measure") == "WoE":
                    source = bundle.tables[key]
                    variable = key.removeprefix("binning.tables.")
                    labels = bundle.bin_labels.get(variable, [])
                    rows = binning_rows(source)
                    dictionary = {
                        "key": key,
                        "html_id": support_id(key) + "-dictionary",
                        "title": f"{variable} · diccionario local de tramos en Desarrollo",
                        "columns": [
                            "Tramo",
                            "Definición del tramo",
                            "Casos",
                            "Malos",
                            "Tasa de malos",
                            "WoE",
                        ],
                        "numeric": [False, False, True, True, True, True],
                        "rows": [
                            (
                                f"T{i + 1}",
                                labels[position]
                                if position < len(labels)
                                else str(row.get("Bin", "")),
                                *(
                                    "No observable (0 casos)"
                                    if c in {"Event rate", "WoE"} and row.get("Count") == 0
                                    else _reading_bin_cell(c, row.get(c))
                                    for c in ("Count", "Event", "Event rate", "WoE")
                                ),
                            )
                            for i, (position, row) in enumerate(rows)
                        ],
                        "links": chart["links"],
                        "truncated": False,
                        "total_rows": len(rows),
                        "shown_rows": len(rows),
                        "total_rows_label": conteo(len(rows)),
                        "shown_rows_label": conteo(len(rows)),
                    }
                    chart["local_tables"] = [dictionary]
        section["links"] = (
            []
            if section is entry
            else [
                {"href": "#section-executive_summary", "label": "Volver a Resultados del scorecard"}
            ]
        )
        if section is appendix:
            section["tables"] = [block for blocks in supports.values() for block in blocks]
            continue
        tables = []
        for table in section["tables"]:
            key = table["key"]
            if key in supports:
                table["links"] = [
                    {"href": "#" + support_id(key), "label": supports[key][0]["title"]}
                ]
            # Mantener también los destinos de los bloques anteriores al compactar o trasladar.
            previous = _split_columns(
                {
                    **table,
                    "columns": ["Fila de lectura", *table["columns"]],
                    "numeric": [True, *table["numeric"]],
                    "rows": [(str(i + 1), *row) for i, row in enumerate(table["rows"])],
                }
            )
            if (
                key in DETAIL_SUMMARIES
                and key in supports
                and DETAIL_SUMMARIES[key] in source_tables
            ):
                supports[key][0].setdefault("aliases", []).extend(t["html_id"] for t in previous)
                supports[key][0]["links"].append(
                    {"href": "#" + section["html_id"], "label": "Volver a " + section["title"]}
                )
                section["links"].extend(table["links"])
                continue
            projection = reading_projection(table, bundle.tables[key]) if key in supports else None
            if projection is not None:
                projection["aliases"] = [
                    t["html_id"] for t in previous if t["html_id"] != projection["html_id"]
                ]
                tables.append(projection)
            else:
                tables.extend(previous)
        section["tables"] = tables
    lineage = next((s for s in views if s["id"] == "appendix_lineage"), None)
    if lineage is None:
        lineage = {
            **appendix,
            "id": "appendix_lineage",
            "html_id": "section-appendix_lineage",
            "title": "Identidad y trazabilidad",
            "tables": [],
            "body": [],
            "links": [],
            "payload_items": [
                {"key": k, "value": str(v), "multiline": False}
                for k, v in document["lineage"].items()
            ],
        }
        views.append(lineage)
    if lineage is not None:
        lineage["payload_items"].extend(
            {"key": k, "value": str(v), "multiline": False} for k, v in files
        )
        lineage["body"].append(
            "Las rutas son las registradas al emitir el informe. Al mover la corrida, "
            "los archivos se buscan en su carpeta de destino."
        )
        entry["links"].append(
            {
                "href": "#" + lineage["html_id"],
                "label": "Identidad, archivos y trazabilidad de la corrida",
            }
        )
    entry["links"].append(
        {"href": "#" + appendix["html_id"], "label": "Evidencia íntegra: tablas y diccionarios"}
    )
    if bundle.governance is None:
        entry["body"].append("La ficha consolidada no fue solicitada.")
    else:
        governance_section = next((s for s in views if s["id"] == "model_card"), None)
        entry["body"].append(
            (
                "El capítulo «Ficha del modelo» contiene las declaraciones institucionales "
                "disponibles al emitir este informe. "
                if governance_section is not None
                else "La corrida tiene declaraciones institucionales de gobernanza. "
            )
            + "La ficha consolidada se emite al cierre de la corrida si se solicita "
            "persistencia o publicación en el inventario."
        )
        if governance_section is not None:
            entry["links"].append(
                {
                    "href": "#" + governance_section["html_id"],
                    "label": "Ficha del modelo: declaraciones institucionales",
                }
            )
    entry["links"].append(
        {"href": "#" + fact_target, "label": "Fuentes, selectores y momento de los hallazgos"}
    )
    # Un solo lugar para los campos institucionales; la política hide sigue siendo efectiva.
    pending = []
    for section in views:
        placeholder = section.get("placeholder")
        if placeholder:
            pending.append(placeholder["title"] + ": " + " ".join(placeholder["guidance"]))
            section["placeholder"] = None
    if config.document.placeholders != "hide" and (pending or missing_cover):
        guidance = (
            ["Identificación pendiente: " + ", ".join(missing_cover) + "."] if missing_cover else []
        ) + pending
        entry["placeholder"] = {
            "title": "Decisión y campos institucionales pendientes",
            "guidance": list(dict.fromkeys(guidance)),
        }
    document["toc"] = [e for e in document["toc"] if e["href"] != "#exec-summary"]
    for e in document["toc"]:
        if e["href"] == "#section-executive_summary":
            e["title"] = entry["title"]
        elif e["href"] == "#" + appendix["html_id"]:
            e["title"] = appendix["title"]
    if not any(e["href"] == "#section-executive_summary" for e in document["toc"]):
        document["toc"].insert(
            0,
            {
                "href": "#section-executive_summary",
                "title": entry["title"],
                "number": "",
                "level": 1,
            },
        )
    return document


def _reading_bin_cell(column: str, value: Any) -> str:
    import pandas as pd

    if value is None or pd.isna(value):
        return "—"
    if column in {"Count", "Event"}:
        return conteo(int(value)) if math.isfinite(value) else "—"
    return porcentaje(value) if column == "Event rate" else cifra(value)


def _scalar_rows(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Hojas escalares sin redondear; las tablas incrustadas tienen su soporte tabular propio."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    if hasattr(value, "columns") and hasattr(value, "itertuples"):
        return [(prefix, "Tabla incrustada; véase su soporte tabular completo")]
    if isinstance(value, Mapping) and value:
        return [
            row
            for key, child in value.items()
            for row in _scalar_rows(child, f"{prefix}.{key}".lstrip("."))
        ]
    if isinstance(value, (list, tuple)) and value:
        return [
            row for i, child in enumerate(value) for row in _scalar_rows(child, f"{prefix}[{i}]")
        ]
    return [(prefix or "valor", value)]


def binning_rows(table: Any) -> list[tuple[int, dict[str, Any]]]:
    """Filas de tramos con su posición original; Totals pertenece al soporte, no a la curva."""
    return [
        (i, row)
        for i, (index, row) in enumerate(zip(table.index, table.to_dict("records"), strict=True))
        if str(index).casefold() != "totals" and str(row.get("Bin", "")).casefold() != "totals"
    ]
