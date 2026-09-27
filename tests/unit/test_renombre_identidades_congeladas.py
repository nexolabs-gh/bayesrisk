"""Identidades que el renombre nikodym → bayesrisk NO movió (enmienda RENOMBRE-BAYESRISK, D-REN-4).

Llevan la palabra «nikodym» pero son identidad de un cálculo o de un formato persistido: la
partición de cada fila, el ``data_hash``, los hashes y formatos del bundle y del lote, el hash del
prompt de IA, los de forward, los tags y nombres por defecto de MLflow y las versiones de esquema de
la evidencia de readiness. Cambiar una movería números, hashes publicados o la idempotencia de un
registro existente sin que ningún otro test lo notara: por eso se fijan literalmente aquí.

También fija la equivalencia del lock (D-REN-6 b): la fuente de bayesrisk, reconstruida con el
proyecto vuelto a llamar «nikodym», es byte a byte la de nikodym 1.20.0 (y 1.19.0).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAQUETE = RAIZ / "src" / "bayesrisk"

#: (archivo relativo a ``src/bayesrisk``, literal exacto que debe seguir en el código fuente).
IDENTIDADES_EN_FUENTE: tuple[tuple[str, str], ...] = (
    ("data/partition.py", '_HASH_PERSON: Final = b"nikodym"'),
    ("data/hashing.py", '_SCHEMA_HEADER_PREFIX: Final = "nikodym.data_hash.v1"'),
    ("forward/macro.py", 'digest.update(b"nikodym.forward.macro_hash.v1")'),
    ("forward/step.py", 'digest.update(b"nikodym.forward.step.logical_frame.v1")'),
    ("core/build.py", 'hashlib.sha256(b"nikodym.installed-distribution.v1\\0")'),
    ("report/charts.py", '"svg.hashsalt": "nikodym"'),
    ("report/ai.py", '_PROMPT_VERSION: Final = "nikodym.report.ai.prompt.v1"'),
    ("scorecard/bundle.py", '"format": "nikodym.scorecard.bundle"'),
    ("scorecard/bundle.py", 'value["format"] != "nikodym.scorecard.bundle"'),
    ("scorecard/bundle.py", '"format": "nikodym.scorecard.batch"'),
    ("scorecard/bundle.py", 'hashlib.sha256(b"nikodym.batch.input.v1\\0")'),
    ("scorecard/bundle.py", 'hashlib.sha256(b"nikodym.batch.output.v1\\0")'),
    ("scorecard/bundle.py", 'b"nikodym.scorecard.input-row.v1\\0"'),
    ("scorecard/bundle.py", 'b"nikodym.scorecard.treatment-trace.v1\\0"'),
    ("stress/engine.py", '"schema": "nikodym.stress.forward_hash.v2"'),
    # MLflow: prefijo de tags y nombres por defecto que la idempotencia busca en registros vivos.
    ("tracking/inventory.py", 'ref.tags.get("nikodym.config_hash") == config_hash'),
    ("tracking/recorder.py", '"nikodym.config_hash": config_hash(config)'),
    ("core/config/schema.py", 'default="nikodym-study"'),
    ("governance/config.py", 'default="nikodym-model"'),
)

#: Hash de ``uv.lock`` de nikodym 1.20.0 y 1.19.0 (medido el 2026-09-27 sobre los wheels de PyPI).
LOCK_NIKODYM_1_20 = "32c611ad4b1e061c14e1262548bf30346610d7529a6e4fb7bc52c68ec3540d24"


@pytest.mark.parametrize(("relativo", "literal"), IDENTIDADES_EN_FUENTE)
def test_la_identidad_sigue_literal(relativo: str, literal: str) -> None:
    fuente = (PAQUETE / relativo).read_text(encoding="utf-8")
    assert literal in fuente, (
        f"{relativo}: desapareció la identidad {literal!r}. Lleva la palabra «nikodym» pero es "
        "identidad de un cálculo o de un formato persistido (RENOMBRE-BAYESRISK, D-REN-4): "
        "renombrarla mueve números, hashes publicados o registros de MLflow."
    )


def test_la_particion_sigue_asignando_igual() -> None:
    """La personalización BLAKE2b de la partición, medida sobre su efecto y no sólo su texto."""
    from bayesrisk.data import partition

    assert partition._HASH_PERSON == b"nikodym"


def test_el_esquema_de_la_evidencia_de_readiness_no_cambia() -> None:
    fuente = (RAIZ / "scripts" / "readiness_h9r" / "contracts.py").read_text(encoding="utf-8")
    assert 'ATTEMPT_SCHEMA_VERSION: Final = "nikodym.readiness.h9r.calibration.v1"' in fuente
    # El arnés SÍ renombra la distribución que mide (D-REN-11).
    assert '"distribution": {"const": "bayesrisk"}' in fuente


def test_el_lock_reconstruido_es_el_de_nikodym_1_20() -> None:
    """Si falla porque cambió una dependencia: los bundles de nikodym ya no son aplicables.

    Es la regla de siempre (un bundle se aplica sólo con su fuente de dependencias). Re-anclar este
    valor exige decirlo en el CHANGELOG: desde esa versión, un bundle de nikodym ≤ 1.20 se rechaza.
    """
    from bayesrisk.core.build import lock_bajo_nombre_anterior

    reconstruido = lock_bajo_nombre_anterior((RAIZ / "uv.lock").read_bytes())
    assert hashlib.sha256(reconstruido).hexdigest() == LOCK_NIKODYM_1_20


def test_el_manifiesto_embebe_las_dos_fuentes_equivalentes() -> None:
    from bayesrisk.core.build import build_uv_lock_hash, build_uv_lock_hashes_equivalentes

    manifiesto = json.loads((PAQUETE / "_build_manifest.json").read_text(encoding="utf-8"))
    assert manifiesto["uv_lock_sha256_nikodym"] == LOCK_NIKODYM_1_20
    assert build_uv_lock_hashes_equivalentes() == {build_uv_lock_hash(), LOCK_NIKODYM_1_20}


def test_la_reconstruccion_devuelve_el_bloque_a_su_lugar_alfabetico() -> None:
    """Reponer sólo el nombre no basta: uv ordena los bloques (pasada 2 de Codex)."""
    from bayesrisk.core.build import lock_bajo_nombre_anterior

    lock = (
        b'version = 1\n\n[[package]]\nname = "alpha"\nversion = "1"\n\n'
        b'[[package]]\nname = "bayesrisk"\nsource = { editable = "." }\n\n'
        b'[[package]]\nname = "numpy"\nversion = "2"\n\n'
        b'[[package]]\nname = "zeta"\nversion = "3"\n'
    )
    esperado = (
        b'version = 1\n\n[[package]]\nname = "alpha"\nversion = "1"\n\n'
        b'[[package]]\nname = "nikodym"\nsource = { editable = "." }\n\n'
        b'[[package]]\nname = "numpy"\nversion = "2"\n\n'
        b'[[package]]\nname = "zeta"\nversion = "3"\n'
    )
    assert lock_bajo_nombre_anterior(lock) == esperado


def test_la_reconstruccion_rechaza_un_lock_ambiguo() -> None:
    from bayesrisk.core.build import lock_bajo_nombre_anterior
    from bayesrisk.core.exceptions import ReproducibilityError

    sin_proyecto = b'version = 1\n\n[[package]]\nname = "numpy"\nversion = "2"\n'
    with pytest.raises(ReproducibilityError, match="exactamente un bloque editable"):
        lock_bajo_nombre_anterior(sin_proyecto)
