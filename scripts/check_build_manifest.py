"""Genera o verifica el manifiesto canónico que ancla ``uv.lock`` dentro del paquete."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "uv.lock"
MANIFEST = ROOT / "src/bayesrisk/_build_manifest.json"

# La reconstrucción del lock bajo el nombre anterior vive en el paquete (una sola implementación
# para este script y para la verificación en tiempo de ejecución; enmienda RENOMBRE-BAYESRISK,
# D-REN-6 b). Se importa del árbol fuente, no de lo instalado.
sys.path.insert(0, str(ROOT / "src"))
from bayesrisk.core.build import lock_bajo_nombre_anterior  # noqa: E402


def expected_bytes() -> bytes:
    """Construye los bytes canónicos esperados desde el lock fuente."""
    lock = LOCK.read_bytes()
    payload = {
        "schema_version": 2,
        "uv_lock_name": "uv.lock",
        "uv_lock_sha256": hashlib.sha256(lock).hexdigest(),
        "uv_lock_sha256_nikodym": hashlib.sha256(lock_bajo_nombre_anterior(lock)).hexdigest(),
    }
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def main() -> int:
    """Verifica por defecto; ``--write`` actualiza sólo el recurso derivado."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = expected_bytes()
    if args.write:
        MANIFEST.write_bytes(expected)
        return 0
    if not MANIFEST.is_file() or MANIFEST.read_bytes() != expected:
        raise SystemExit(
            "_build_manifest.json no coincide con uv.lock; ejecute "
            "scripts/check_build_manifest.py --write y revise el diff."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
