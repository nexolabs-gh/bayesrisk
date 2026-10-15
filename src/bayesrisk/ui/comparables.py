"""Resúmenes comparables de corridas y subidas autenticadas (SDD-34 §4.3)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from bayesrisk.core.exceptions import BayesRiskError
from bayesrisk.ui.exceptions import UiComparableError


def _ficha(archivo: Path, *, origin: str) -> dict[str, Any]:
    from bayesrisk.guided.comparison import leer_resumen_comparable

    resumen, huella = leer_resumen_comparable(archivo)
    return {
        "path": str(archivo.resolve()),
        "origin": origin,
        "name": str(resumen["name"]),
        "family": resumen["family"],
        "created_at": resumen["created_at"],
        "comparison_hash": huella,
    }


def listar(workdir: Path) -> list[dict[str, Any]]:
    """Ofrece sólo resúmenes legibles dentro del workdir; nunca sus observaciones."""
    raiz = workdir.resolve()
    fichas = []
    for origin, rutas in (
        ("run", (raiz / "runs").glob("*/comparable.json")),
        ("upload", (raiz / "comparables").glob("*.json")),
    ):
        for archivo in sorted(rutas):
            if not archivo.resolve().is_relative_to(raiz):
                continue
            try:
                fichas.append(_ficha(archivo, origin=origin))
            except (BayesRiskError, OSError, ValueError, TypeError):
                continue
    return sorted(fichas, key=lambda f: str(f["created_at"] or ""), reverse=True)


def subir(content: bytes, filename: Any, *, workdir: Path, max_bytes: int) -> dict[str, Any]:
    """Valida antes de publicar; la huella completa identifica la subida, nunca su nombre."""
    if not str(filename or "").lower().endswith(".json"):
        raise UiComparableError("Sube el resumen comparable como archivo .json.")
    if len(content) > max_bytes:
        raise UiComparableError(f"El resumen pasa el tope de subida ({max_bytes} bytes).")
    carpeta = workdir.resolve() / "comparables"
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = carpeta / f".subida-{uuid.uuid4().hex}.tmp"
    try:
        temporal.write_bytes(content)
        ficha = _ficha(temporal, origin="upload")
        destino = carpeta / f"{ficha['comparison_hash']}.json"
        os.replace(temporal, destino)
        return {**ficha, "path": str(destino)}
    except (BayesRiskError, ValueError, TypeError) as exc:
        raise UiComparableError(str(exc)) from exc
    finally:
        temporal.unlink(missing_ok=True)
