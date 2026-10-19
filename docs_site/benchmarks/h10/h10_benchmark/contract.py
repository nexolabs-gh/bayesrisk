"""Universo predeclarado y censo bidireccional de la entrega parcial H10."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SEED = 20261016
CASES = ("german", "taiwan", "consumo_comportamiento", "consumo_drift")
RECIPES = {
    "fabrica": {},
    "sin_stepwise": {"stepwise": False},
    "cinco_bins": {"max_bins": 5},
    "monotonia_auto": {"monotonic": "auto"},
    "optbinning_mip": None,
    "scorecardpy": None,
    "skorecard_mip": None,
}
THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)
SOURCES = {
    "german": {
        "id": 144,
        "slug": "statlog+german+credit+data",
        "sha256": "e12d9d5def6845c0622634a1cd2ab87fa470668c4298f1ec52a4e403376a435b",
        "member": "german.data",
        "rows": 1000,
        "events": 300,
        "license": "CC BY 4.0",
        "author": "Hans Hofmann",
        "doi": "10.24432/C5NC77",
    },
    "taiwan": {
        "id": 350,
        "slug": "default+of+credit+card+clients",
        "sha256": "56c885f84457f6680f8438f02bfcdac9579323d8a94465ee5f26e32baa727602",
        "member": "default of credit card clients.xls",
        "rows": 30000,
        "events": 6636,
        "license": "CC BY 4.0",
        "author": "I-Cheng Yeh",
        "doi": "10.24432/C55S3H",
    },
}


def sha256(path: Path) -> str:
    """Huella de bytes, sin aceptar otra copia al cambiar la fuente."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: Any) -> None:
    """Publica JSON legible, sin serializar objetos opacos ni NaN silenciosamente."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Ninguna receta desaparece del denominador por error o dependencia ausente."""
    expected = {(case, recipe) for case in CASES for recipe in RECIPES}
    actual = [(row["case"], row["recipe"]) for row in rows]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("cobertura: faltan/sobran casos o hay duplicados")
    for row in rows:
        if row["status"] not in {"ejecutado", "falló", "pendiente"}:
            raise ValueError("cobertura: estado desconocido")
        if row["status"] != "ejecutado" and not row.get("error"):
            raise ValueError("cobertura: ausencia sin razón")
    return {
        "total": len(expected),
        "executed": sum(r["status"] == "ejecutado" for r in rows),
        "failed": sum(r["status"] == "falló" for r in rows),
        "pending": sum(r["status"] == "pendiente" for r in rows),
    }


def verify_sources(root: Path) -> None:
    """Confronta archivos entregados con un inventario externo al propio contenido."""
    manifest = json.loads((root / "delivery.json").read_text(encoding="utf-8"))
    expected = set(manifest["files"])
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p != root / "delivery.json"
    }
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("censo: no se admiten enlaces simbólicos")
    if actual != expected:
        raise ValueError(
            f"censo: faltan {sorted(expected - actual)}; sobran {sorted(actual - expected)}"
        )
    for name, digest in manifest["files"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"huella de auxiliar diferente: {name}")
    if tuple(manifest["cases"]) != CASES or tuple(manifest["recipes"]) != tuple(RECIPES):
        raise ValueError("censo de carteras/recetas distinto al predeclarado")
