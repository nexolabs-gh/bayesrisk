"""Reproduce el protocolo completo en procesos independientes y secuenciales."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from h10_benchmark.contract import THREAD_ENV, verify_sources


def main() -> None:
    """Los destinos previos se conservan; cualquier fallo detiene la reproducción."""
    root = Path(__file__).resolve().parent
    verify_sources(root)
    destination = root / "reproduction"
    if destination.exists():
        raise SystemExit("reproduction ya existe; conserva su evidencia y usa otra extracción.")
    destination.mkdir()
    environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONPATH="")
    environment.update({name: "1" for name in THREAD_ENV})
    command = [sys.executable, "-m", "h10_benchmark"]
    subprocess.run(
        [*command, "prepare", "--cache", "cache", "--prepared", "reproduction/prepared"],
        cwd=root,
        env=environment,
        check=True,
    )
    for name in ("warmup", "run-1", "run-2", "run-3"):
        subprocess.run(
            [
                *command,
                "run",
                "--prepared",
                "reproduction/prepared",
                "--output",
                f"reproduction/{name}",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
    subprocess.run(
        [
            *command,
            "aggregate",
            "--prepared",
            "reproduction/prepared",
            "--output",
            "reproduction/aggregate",
            "--runs",
            "reproduction/run-1",
            "reproduction/run-2",
            "reproduction/run-3",
        ],
        cwd=root,
        env=environment,
        check=True,
    )


if __name__ == "__main__":
    main()
