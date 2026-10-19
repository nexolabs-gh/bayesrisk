"""Entrada del anexo; fija el entorno numérico ANTES de importar las recetas."""

import argparse
import os
from pathlib import Path

from .contract import THREAD_ENV


def main() -> None:
    """Ejecuta la acción documental explícita, sin elegir modelos automáticamente."""
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("Inicia Python con PYTHONHASHSEED=0; no se puede fijar retroactivamente.")
    for name in THREAD_ENV:
        os.environ[name] = "1"
    parser = argparse.ArgumentParser(description="Benchmark parcial H10 reproducible")
    parser.add_argument("action", choices=["prepare", "run", "aggregate"])
    parser.add_argument("--cache", type=Path, default=Path("cache"))
    parser.add_argument("--prepared", type=Path, default=Path("prepared"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--runs", type=Path, nargs=3)
    args = parser.parse_args()
    from .runner import prepare, run

    if args.action == "prepare":
        prepare(args.cache, args.prepared)
    elif args.action == "run":
        rows = run(args.prepared, args.output)
        if any(row["status"] != "ejecutado" for row in rows):
            raise SystemExit("Cobertura incompleta: errores preservados en results.json.")
    else:
        from .aggregate import aggregate

        if args.runs is None:
            parser.error("aggregate requiere --runs con tres directorios")
        aggregate(args.prepared, args.runs, args.output)


if __name__ == "__main__":
    main()
