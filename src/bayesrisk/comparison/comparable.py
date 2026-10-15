"""El resumen comparable de una corrida terminada (SDD-34 §6.1, D-CMP-2).

Toda corrida **terminada** (``done``) de la familia scorecard que publicó ``performance``, y toda
de IFRS 9 que publicó su provisión, deja un resumen comparable: sólo agregados, en JSON —nunca
pickle—, con las huellas que dicen sobre qué cartera, qué muestra y qué modelo se midió, y el
riesgo y el desenlace de su muestra de evaluación en orden canónico, sin identificadores. Una sola
función lo arma desde el ``Study`` (:func:`armar`), para las tres puertas: ``Study.run`` lo arma al
cerrar —antes de ``run_end``, con el registro de auditoría todavía abierto (D-VIS)—, y
``bayesrisk.run`` lo escribe en su ``run_dir`` y la pantalla en ``runs/<id>/``.

Lo que la corrida no tiene va en nulo con su razón en ``missing``; armarlo nunca hace fallar la
corrida. La comparación (:mod:`bayesrisk.comparison.step`) lee estos archivos y nada más: no abre
carpetas con ``Study.load``.

**Estable (SemVer 2.x).** Desde la 2.16.0 (capa B del SDD-34).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from bayesrisk.comparison.exceptions import ComparisonDataError

if TYPE_CHECKING:
    from bayesrisk.core.study import Study

__all__ = [
    "COMPARABLE_FILENAME",
    "FAMILIAS",
    "RECETA_PSI_DE_FABRICA",
    "REGLA_SIN_RESUMEN",
    "SCHEMA_VERSION",
    "armar",
    "armar_al_cerrar",
    "bytes_canonicos",
    "escribir",
    "huella",
    "huella_computacional",
    "leer",
    "resumen_de",
    "validar",
]

#: La versión del formato. Un lector que no la conoce se detiene en vez de comparar a ciegas.
SCHEMA_VERSION: Final = 1
#: El nombre del archivo en el ``run_dir`` de ``bayesrisk.run`` y en ``runs/<id>/`` de la pantalla.
COMPARABLE_FILENAME: Final = "comparable.json"
#: Las dos familias comparables (§1): un scorecard y una provisión IFRS 9 no se comparan entre sí.
FAMILIAS: Final[tuple[str, ...]] = ("scorecard", "ifrs9")
#: La receta del PSI común de la frontera (D-CMP-7): los defaults de ``stability``. Un test la ata
#: a ``StabilityConfig``: si cambiara un default, la receta común no lo sigue sin una decisión.
RECETA_PSI_DE_FABRICA: Final[dict[str, Any]] = {
    "bins": 10,
    "smoothing": 1e-06,
    "thresholds": [0.10, 0.25],
}
#: La regla con que el registro de auditoría declara que la corrida terminó sin resumen (D-VIS).
REGLA_SIN_RESUMEN: Final = "resumen_comparable_no_disponible"

_MUESTRAS: Final[tuple[str, ...]] = ("desarrollo", "holdout", "oot")
_CLAVES_COMUNES: Final = frozenset(
    {
        "schema_version",
        "bayesrisk",
        "family",
        "name",
        "created_at",
        "config_hash",
        "data_hash",
        "portfolio_hash",
        "currency",
        "missing",
    }
)
_CLAVES_SCORECARD: Final = frozenset(
    {
        "model_hash",
        "psi_recipe",
        "samples",
        "evaluation_sample",
        "evaluation_scores",
        "score_psi",
        "score_psi_common",
        "grades",
        "variables",
        "validation",
    }
)
_CLAVES_IFRS9: Final = frozenset({"as_of", "scenarios", "amount_columns", "by_stage", "total"})

# ── La huella computacional del modelo (§3.3) ────────────────────────────────────────────────
#
# Una proyección CAMPO POR CAMPO del manifiesto de la tarjeta: entra lo que la aplicación consume
# para puntuar; sale la procedencia. `bundle_hash` no sirve —incluye el `config_hash` en su
# `fit_lineage`, y el mismo modelo con otro config da otra huella (§0.4-1)— y tampoco basta quitar
# ese bloque: la calibración guarda su procedencia en `anchor_source` (pasada 2 de Codex). Cada
# campo está clasificado; `tests/unit/test_comparison_comparable.py` ata estas tablas a las claves
# que `FittedScorecardBundle` exige, en los dos sentidos: un campo nuevo de la tarjeta no entra ni
# sale de la huella sin una decisión.
ENTRA: Final = "entra"
SALE: Final = "sale"
#: Las claves de la raíz del manifiesto (esquema 4, con la escala y su referencia de monitoreo).
CAMPOS_DEL_MANIFIESTO: Final[dict[str, str]] = {
    "schema_version": SALE,  # la versión del formato: la misma tarjeta en otro esquema
    "format": SALE,
    "input_schema": ENTRA,  # qué columnas y tipos acepta
    "row_identity": SALE,  # la columna de identidad
    "treatment_policy": ENTRA,
    "special_catalog": ENTRA,
    "model": ENTRA,  # campo por campo: CAMPOS_DEL_MODELO
    "fit_lineage": SALE,  # config_hash, data_hash, entorno y versiones
    "rules_sha256": ENTRA,  # los tramos y sus puntos
    "files": SALE,
    "bundle_hash": SALE,
    "unseen_reference": ENTRA,
    "master_scale": ENTRA,  # campo por campo: CAMPOS_DE_LA_ESCALA
    "monitoring_reference": SALE,  # agregados de Desarrollo para monitorear, no para puntuar
}
#: ``manifest.model``.
CAMPOS_DEL_MODELO: Final[dict[str, str]] = {
    "features": ENTRA,
    "woe_columns": ENTRA,
    "intercept": ENTRA,
    "beta": ENTRA,
    "score_column": SALE,  # el nombre de la columna de salida, no su valor
    "score_direction": ENTRA,
    "rounding_method": ENTRA,
    "min_score": ENTRA,
    "max_score": ENTRA,
    "clip": ENTRA,
    "calibration": ENTRA,  # campo por campo: CAMPOS_DE_LA_CALIBRACION
}
#: ``manifest.model.calibration`` (los campos de ``CalibrationParameters``): el método y sus
#: parámetros ajustados entran; el ancla, su fuente y los diagnósticos del ajuste salen.
CAMPOS_DE_LA_CALIBRACION: Final[dict[str, str]] = {
    "method": ENTRA,
    "offset": ENTRA,
    "slope": ENTRA,
    "intercept": ENTRA,
    "isotonic_knots": ENTRA,
    "post_offset": ENTRA,
    "target_pd": SALE,
    "anchor_kind": SALE,
    "anchor_source": SALE,
    "fit_partition": SALE,
    "target_tolerance": SALE,
    "achieved_mean_pd_dev": SALE,
    "raw_mean_pd_dev": SALE,
    "observed_default_rate_dev": SALE,
    "n_fit": SALE,
}
#: ``manifest.master_scale``: los cortes, la PD de cada tramo y el corte de aprobación entran; de
#: dónde salieron los cortes (formados o fijados por la institución), no.
CAMPOS_DE_LA_ESCALA: Final[dict[str, str]] = {
    "cuts": ENTRA,
    "grade_pd": ENTRA,
    "approval_cutoff": ENTRA,
    "source": SALE,
}
_ANIDADOS: Final[dict[str, dict[str, str]]] = {
    "model": CAMPOS_DEL_MODELO,
    "master_scale": CAMPOS_DE_LA_ESCALA,
}


class _CampoAusenteError(Exception):
    """Un campo que la corrida no tiene: va en nulo con esta razón en ``missing``."""


def _proyectar(valor: Mapping[str, Any], campos: Mapping[str, str], ruta: str) -> dict[str, Any]:
    salida: dict[str, Any] = {}
    for clave, contenido in valor.items():
        clase = campos.get(clave)
        if clase is None:
            raise ValueError(f"el campo {ruta}{clave} de la tarjeta no está clasificado")
        if clase == SALE:
            continue
        if ruta == "model." and clave == "calibration":
            salida[clave] = _proyectar(contenido, CAMPOS_DE_LA_CALIBRACION, "model.calibration.")
        else:
            salida[clave] = contenido
    return salida


def huella_computacional(manifest: Mapping[str, Any]) -> str:
    """La huella del modelo: SHA-256 de la proyección computacional del manifiesto (§3.3).

    Dos tarjetas con la misma huella puntúan, tramifican y calibran igual —son el mismo modelo—,
    lo diga o no su ``config_hash``. Un campo del manifiesto sin clasificar levanta ``ValueError``.
    """
    proyeccion: dict[str, Any] = {}
    for clave, contenido in manifest.items():
        clase = CAMPOS_DEL_MANIFIESTO.get(clave)
        if clase is None:
            raise ValueError(f"el campo {clave} de la tarjeta no está clasificado")
        if clase == SALE:
            continue
        anidado = _ANIDADOS.get(clave)
        proyeccion[clave] = (
            _proyectar(contenido, anidado, f"{clave}.") if anidado is not None else contenido
        )
    return hashlib.sha256(bytes_canonicos(proyeccion)).hexdigest()


# ── Serialización y huella del resumen ───────────────────────────────────────────────────────


def bytes_canonicos(valor: Any) -> bytes:
    """El JSON canónico: claves ordenadas, sin espacios, UTF-8 y sin números no finitos."""
    return json.dumps(
        valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def huella(resumen: Mapping[str, Any]) -> str:
    """La huella de un resumen: SHA-256 de su JSON canónico (§9).

    No depende de cómo se escribió el archivo: un resumen reformateado conserva su huella, uno con
    un valor cambiado no.
    """
    return hashlib.sha256(bytes_canonicos(resumen)).hexdigest()


def escribir(resumen: Mapping[str, Any], directorio: Path) -> Path:
    """Escribe ``comparable.json`` en ``directorio`` (JSON canónico) y devuelve la ruta."""
    destino = Path(directorio) / COMPARABLE_FILENAME
    destino.write_bytes(bytes_canonicos(resumen))
    return destino


# ── Leer ─────────────────────────────────────────────────────────────────────────────────────

_COMO_OBTENERLO: Final = (
    "Vuelve a correrla con esta versión de bayesrisk —mismo config, mismos resultados— o pasa el "
    "objeto vivo (un Scorecard, un Ecl o un Study ya corridos); si sólo queda la carpeta del "
    "estudio, cárgala con Study.load(ruta, trust=True) —la decisión de confianza es tuya— y pasa "
    "el Study."
)


def _ubicar(ruta: Path) -> Path:
    """El ``comparable.json`` de una ruta: el archivo, o el de una carpeta de corrida o proyecto."""
    if ruta.is_file():
        return ruta
    for candidato in (ruta / COMPARABLE_FILENAME, ruta / "run" / COMPARABLE_FILENAME):
        if candidato.is_file():
            return candidato
    if not ruta.exists():
        raise ComparisonDataError(f"La corrida {ruta} no existe.")
    es_corrida = any(
        (carpeta / marca).exists()
        for carpeta in (ruta, ruta / "run")
        for marca in ("study", "results.json", "audit_trail.jsonl")
    )
    if es_corrida:
        raise ComparisonDataError(
            f"La corrida {ruta} no tiene resumen comparable: se guardó con una versión anterior a "
            "la 2.15.0, no terminó, paró antes de medir su desempeño o su provisión, o no pudo "
            f"dejarlo (su registro de auditoría dice por qué). {_COMO_OBTENERLO}"
        )
    raise ComparisonDataError(
        f"{ruta} no es una corrida de bayesrisk ni un resumen comparable ({COMPARABLE_FILENAME})."
    )


def _no_finito(constante: str) -> Any:
    raise ValueError(f"trae el número no finito {constante}, que un resumen comparable no admite")


def leer(ruta: str | Path) -> tuple[dict[str, Any], Path]:
    """El resumen de ``ruta`` —el archivo o la carpeta de su corrida—, validado, y dónde estaba.

    Raises
    ------
    ComparisonDataError
        Si no hay resumen, no se puede leer o no es de un formato que esta versión conoce.
    """
    archivo = _ubicar(Path(ruta))
    try:
        # NaN e infinitos no son JSON canónico —el armado nunca los escribe—: un archivo editado
        # a mano que los traiga no es un resumen de esta versión (pasada 2 de Codex sobre la
        # capa B: llegaban a los gráficos).
        resumen = json.loads(archivo.read_text(encoding="utf-8"), parse_constant=_no_finito)
    except (OSError, ValueError) as exc:
        raise ComparisonDataError(
            f"No se pudo leer el resumen comparable {archivo}: {exc}"
        ) from exc
    return validar(resumen, origen=str(archivo)), archivo


def validar(resumen: Any, *, origen: str = "el resumen") -> dict[str, Any]:
    """El resumen si su forma es la de esta versión; si no, el error que dice qué le falta."""
    if not isinstance(resumen, dict):
        raise ComparisonDataError(f"{origen} no es un resumen comparable: no es un objeto JSON.")
    version = resumen.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ComparisonDataError(
            f"{origen} es un resumen comparable de esquema {version!r}; esta versión de bayesrisk "
            f"lee el {SCHEMA_VERSION}."
        )
    familia = resumen.get("family")
    if familia not in FAMILIAS:
        raise ComparisonDataError(f"{origen}: la familia {familia!r} no es comparable.")
    requeridas = _CLAVES_COMUNES | (_CLAVES_SCORECARD if familia == "scorecard" else _CLAVES_IFRS9)
    faltan = sorted(requeridas - set(resumen))
    sobran = sorted(set(resumen) - requeridas)
    if faltan or sobran:
        raise ComparisonDataError(
            f"{origen} no tiene la forma de un resumen comparable: faltan {faltan}, "
            f"sobran {sobran}."
        )
    from bayesrisk.comparison._schema import validar_forma

    validar_forma(resumen, origen=origen)
    return resumen


# ── Armar ────────────────────────────────────────────────────────────────────────────────────


def familia_comparable(study: Study) -> str | None:
    """``"scorecard"``, ``"ifrs9"`` o ``None`` si la corrida no deja resumen (§6.1)."""
    if study.run_context.status != "done":
        return None
    artefactos = study.artifacts
    if artefactos.has("performance", "discriminant_metrics"):
        return "scorecard"
    if artefactos.has("provisioning_ifrs9", "summary") and artefactos.has(
        "provisioning_ifrs9", "card"
    ):
        return "ifrs9"
    return None


def armar_al_cerrar(study: Study) -> dict[str, Any] | None:
    """Lo que ``Study.run`` llama al cerrar: el resumen, o ``None`` si la corrida no lo deja."""
    return armar(study)


def resumen_de(study: Study) -> dict[str, Any]:
    """El resumen de un objeto vivo: el que la corrida armó al cerrar, o uno armado ahora.

    Es determinista —``created_at`` es el de la corrida—, así que armarlo otra vez da el mismo
    resumen que quedó en disco.

    Raises
    ------
    ComparisonDataError
        Si la corrida no terminó o no es de una familia comparable.
    """
    resumen = getattr(study, "_resumen_comparable", None)
    if resumen is None:
        resumen = armar(study)
    if resumen is None:
        nombre = getattr(getattr(study, "config", None), "name", "la corrida")
        estado = study.run_context.status
        motivo = (
            f"no terminó (estado «{estado}»)"
            if estado != "done"
            else "no midió el desempeño de un scorecard ni provisionó IFRS 9"
        )
        raise ComparisonDataError(f"La corrida {nombre} no tiene resumen comparable: {motivo}.")
    return dict(resumen)


def armar(study: Study) -> dict[str, Any] | None:
    """El resumen comparable de una corrida, o ``None`` si no es elegible (§6.1).

    Cada campo que la corrida no tiene —o que algo inesperado impide calcular— va en nulo con su
    razón en ``missing``: un campo nunca tumba al resto.
    """
    import bayesrisk

    familia = familia_comparable(study)
    if familia is None:
        return None
    lineage = study.run_context.lineage
    faltantes: dict[str, str] = {}
    resumen: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bayesrisk": bayesrisk.__version__,
        "family": familia,
        "name": str(study.config.name),
        "created_at": lineage.created_at.isoformat() if lineage is not None else None,
        "config_hash": lineage.config_hash if lineage is not None else None,
        "data_hash": lineage.data_hash if lineage is not None else None,
        "portfolio_hash": _campo(faltantes, "portfolio_hash", lambda: _huella_de_cartera(study)),
        "currency": _moneda(study),
    }
    if familia == "scorecard":
        resumen.update(_scorecard(study, faltantes))
    else:
        resumen.update(_ifrs9(study, faltantes))
    resumen["missing"] = dict(sorted(faltantes.items()))
    # Escribirlo no puede fallar por su contenido: lo que no sea JSON canónico se detecta aquí,
    # donde la corrida todavía puede declararlo (D-VIS), y no al escribir la evidencia.
    bytes_canonicos(resumen)
    return resumen


def _campo(faltantes: dict[str, str], nombre: str, calcular: Callable[[], Any]) -> Any:
    """``calcular()``; si falta o algo inesperado lo impide, nulo con su razón."""
    try:
        return calcular()
    except _CampoAusenteError as falta:
        faltantes[nombre] = str(falta)
    except Exception as exc:  # D-VIS: un campo que no se puede calcular no tumba el resumen
        faltantes[nombre] = f"no se pudo calcular: {type(exc).__name__}: {exc}"
    return None


def _huella_de_cartera(study: Study) -> str:
    """La cartera antes de etiquetar y particionar, con el algoritmo de ``data_hash`` (§0.4-5)."""
    if not study.artifacts.has("data", "special"):
        raise _CampoAusenteError(
            "la corrida no cargó su cartera (los datos llegaron ya preparados)"
        )
    from bayesrisk.data.hashing import data_hash

    return data_hash(study.artifacts.get("data", "special").frame)


def _moneda(study: Study) -> str | None:
    """``report.currency`` (D-MON): nula si no se declaró o si la corrida no tiene informe."""
    report = getattr(study.config, "report", None)
    moneda = (
        report.get("currency") if isinstance(report, Mapping) else getattr(report, "currency", None)
    )
    return str(moneda) if moneda else None


def _float(valor: Any) -> float | None:
    """Un número finito como ``float`` nativo, o ``None`` (NaN, NA, vacío)."""
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _bool_o_nulo(valor: Any) -> bool | None:
    """Un booleano de una tabla, o ``None`` si viene vacío (None, NaN o NA)."""
    import pandas as pd

    if valor is None:
        return None
    try:
        if bool(pd.isna(valor)):
            return None
    except (TypeError, ValueError):
        pass
    return bool(valor)


def _int(valor: Any) -> int | None:
    numero = _float(valor)
    return int(numero) if numero is not None else None


# ── scorecard ────────────────────────────────────────────────────────────────────────────────


def _scorecard(study: Study, faltantes: dict[str, str]) -> dict[str, Any]:
    muestras = _muestras(study)
    evaluacion = _muestra_de_evaluacion(muestras)
    return {
        "model_hash": _campo(faltantes, "model_hash", lambda: _huella_del_modelo(study)),
        "psi_recipe": _campo(faltantes, "psi_recipe", lambda: _receta_psi(study)),
        "samples": muestras,
        "evaluation_sample": evaluacion,
        "evaluation_scores": _campo(
            faltantes, "evaluation_scores", lambda: _puntajes_de_evaluacion(study, evaluacion)
        ),
        "score_psi": _campo(faltantes, "score_psi", lambda: _psi_publicado(study)),
        "score_psi_common": _campo(
            faltantes, "score_psi_common", lambda: _psi_comun(study, evaluacion)
        ),
        "grades": _campo(faltantes, "grades", lambda: _tramos(study)),
        "variables": _campo(faltantes, "variables", lambda: _variables(study)),
        "validation": _campo(faltantes, "validation", lambda: _validacion(study)),
    }


def _muestras(study: Study) -> list[dict[str, Any]]:
    """AUC, Gini y KS por muestra, como ``performance`` los publicó."""
    tabla = study.artifacts.get("performance", "discriminant_metrics")
    filas = {str(fila["partition"]): fila for _, fila in tabla.iterrows()}
    salida: list[dict[str, Any]] = []
    for muestra in _MUESTRAS:
        fila = filas.get(muestra)
        if fila is None:
            continue
        salida.append(
            {
                "sample": muestra,
                "n": _int(fila.get("n_total")) or 0,
                "n_bad": _int(fila.get("n_bad")) or 0,
                "auc": _float(fila.get("auc")),
                "gini": _float(fila.get("gini")),
                "ks": _float(fila.get("ks")),
                "status": str(fila.get("status")),
            }
        )
    return salida


def _muestra_de_evaluacion(muestras: list[dict[str, Any]]) -> str:
    """La OOT si la corrida la tiene; si no, el Holdout; si no, Desarrollo (optimista, §3.2)."""
    con_filas = {m["sample"] for m in muestras if m["n"] > 0}
    for muestra in ("oot", "holdout"):
        if muestra in con_filas:
            return muestra
    return "desarrollo"


def _huella_del_modelo(study: Study) -> str:
    if not (study.artifacts.has("scorecard", "card") and study.artifacts.has("binning", "process")):
        raise _CampoAusenteError(
            "la corrida no tiene tarjeta: evaluó puntajes y PD que trajo de fuera, o no ajustó "
            "el scorecard"
        )
    from bayesrisk.scorecard.bundle import FittedScorecardBundle
    from bayesrisk.scorecard.exceptions import ScorecardBundleError

    try:
        tarjeta = FittedScorecardBundle.from_study(study)
    except ScorecardBundleError as exc:
        raise _CampoAusenteError(f"la tarjeta no se pudo congelar: {exc}") from exc
    return huella_computacional(tarjeta.manifest)


def _config_de_estabilidad(study: Study) -> Any:
    seccion = getattr(study.config, "stability", None)
    if seccion is None or not study.artifacts.has("stability", "stability_metrics"):
        raise _CampoAusenteError("la corrida no midió la estabilidad")
    from bayesrisk.stability.config import StabilityConfig

    if isinstance(seccion, StabilityConfig):
        return seccion
    return StabilityConfig.model_validate(seccion)


def _receta_psi(study: Study) -> dict[str, Any]:
    cfg = _config_de_estabilidad(study)
    return {
        "bins": int(cfg.psi_bins),
        "smoothing": float(cfg.smoothing),
        "thresholds": [float(cfg.psi_stable_threshold), float(cfg.psi_review_threshold)],
    }


def _psi_publicado(study: Study) -> list[dict[str, Any]]:
    """El PSI del puntaje de cada comparación, con la receta de la corrida."""
    if not study.artifacts.has("stability", "stability_metrics"):
        raise _CampoAusenteError("la corrida no midió la estabilidad")
    tabla = study.artifacts.get("stability", "stability_metrics")
    filas = tabla[tabla["metric"].astype(str) == "score_psi"]
    return [
        {
            "comparison": str(fila["comparison"]),
            "psi": _float(fila["value"]),
            "band": str(fila["band"]),
        }
        for _, fila in filas.iterrows()
    ]


def _psi_comun(study: Study, evaluacion: str) -> dict[str, Any]:
    """El PSI del puntaje Desarrollo → evaluación con la receta de fábrica (D-CMP-7, §3.5).

    Con las funciones de ``stability`` (:func:`~bayesrisk.stability.step.compute_stability`) sobre
    el mismo frame que la etapa leyó; con la receta de fábrica coincide con el publicado.
    """
    if evaluacion == "desarrollo":
        raise _CampoAusenteError(
            "la corrida no tiene muestra fuera de Desarrollo contra la que medir el PSI"
        )
    cfg = _config_de_estabilidad(study)
    from bayesrisk.stability.step import compute_stability

    comparacion = f"dev_vs_{evaluacion}"
    stable, review = RECETA_PSI_DE_FABRICA["thresholds"]
    receta = cfg.model_copy(
        update={
            "psi_bins": RECETA_PSI_DE_FABRICA["bins"],
            "smoothing": RECETA_PSI_DE_FABRICA["smoothing"],
            "psi_stable_threshold": stable,
            "psi_review_threshold": review,
            "comparisons": (comparacion,),
        }
    )
    tabla = compute_stability(study, receta).stability_metrics
    fila = tabla[
        (tabla["metric"].astype(str) == "score_psi")
        & (tabla["comparison"].astype(str) == comparacion)
    ]
    if fila.empty:
        raise _CampoAusenteError(f"la estabilidad no midió el puntaje en {comparacion}")
    return {
        "comparison": comparacion,
        "psi": _float(fila["value"].iloc[0]),
        "band": str(fila["band"].iloc[0]),
    }


def _orden_canonico(frame: Any) -> Any:
    """El frame ordenado por su índice; un índice de tipos mezclados, por su representación."""
    try:
        return frame.sort_index(kind="mergesort")
    except TypeError:
        claves = [f"{type(v).__name__}:{v!r}" for v in frame.index.tolist()]
        return frame.iloc[sorted(range(len(claves)), key=claves.__getitem__)]


def _huella_del_indice(indice: Any) -> str:
    resumen = hashlib.sha256()
    for valor in indice.tolist():
        resumen.update(f"{type(valor).__name__}:{valor!r}\x1f".encode())
    return resumen.hexdigest()


def _puntajes_de_evaluacion(study: Study, evaluacion: str) -> dict[str, Any]:
    """El riesgo y el desenlace de cada fila evaluada, en orden canónico y sin índice (§3.3)."""
    import numpy as np

    from bayesrisk.performance.step import riesgo_evaluado

    frame = riesgo_evaluado(study)
    muestra = _orden_canonico(frame[frame["partition"] == evaluacion])
    cfg = getattr(study.config, "performance", None)
    base = getattr(cfg, "evaluation_source", None) or (
        cfg.get("evaluation_source") if isinstance(cfg, Mapping) else None
    )
    desenlace = muestra["default"].to_numpy(dtype="int64")
    return {
        "order": "index",
        "basis": str(base or "pd_calibrated"),
        "rows_hash": _huella_del_indice(muestra.index),
        "default_hash": hashlib.sha256(np.asarray(desenlace, dtype="<i1").tobytes()).hexdigest(),
        "risk": [float(v) for v in muestra["risk"].to_numpy(dtype="float64")],
        "default": [int(v) for v in desenlace],
    }


def _tramos(study: Study) -> dict[str, Any]:
    """La participación de cada tramo de la escala maestra, por muestra (§3.4)."""
    if not study.artifacts.has("master_scale", "grade_table"):
        raise _CampoAusenteError("la corrida no formó escala maestra")
    tabla = study.artifacts.get("master_scale", "grade_table")
    k = int(tabla["grade"].max()) if not tabla.empty else 0
    participacion: dict[str, list[float]] = {}
    for muestra, grupo in tabla.groupby("sample", sort=False):
        por_tramo = {
            int(g): _float(s) or 0.0 for g, s in zip(grupo["grade"], grupo["share"], strict=True)
        }
        participacion[str(muestra)] = [por_tramo.get(g, 0.0) for g in range(1, k + 1)]
    return {"k": k, "share_by_sample": participacion}


def _variables(study: Study) -> list[dict[str, Any]]:
    """Por variable del modelo final: signo, si cumple el esperado, IV y CSI (§6.1)."""
    if not study.artifacts.has("model", "coefficients"):
        raise _CampoAusenteError("la corrida no tiene modelo: evaluó puntajes que trajo de fuera")
    coeficientes = study.artifacts.get("model", "coefficients")
    coeficientes = coeficientes[~coeficientes["feature"].astype(str).isin(["intercept", "const"])]
    iv_por_muestra: dict[str, dict[str, float | None]] = {}
    if study.artifacts.has("selection", "iv_by_partition"):
        for _, fila in study.artifacts.get("selection", "iv_by_partition").iterrows():
            iv_por_muestra.setdefault(str(fila["feature"]), {})[str(fila["partition"])] = _float(
                fila["iv"]
            )
    csi: dict[str, list[dict[str, Any]]] = {}
    if study.artifacts.has("stability", "stability_metrics"):
        tabla = study.artifacts.get("stability", "stability_metrics")
        for _, fila in tabla[tabla["metric"].astype(str) == "csi"].iterrows():
            variable = str(fila["feature"]).removesuffix("__points").removesuffix("__bin")
            csi.setdefault(variable, []).append(
                {
                    "comparison": str(fila["comparison"]),
                    "csi": _float(fila["value"]),
                    "band": str(fila["band"]),
                }
            )
    salida: list[dict[str, Any]] = []
    for _, fila in coeficientes.iterrows():
        variable = str(fila["feature"])
        salida.append(
            {
                "feature": variable,
                "beta": _float(fila.get("beta")),
                "expected_sign": None
                if fila.get("expected_sign") is None
                else str(fila.get("expected_sign")),
                "sign_ok": _bool_o_nulo(fila.get("sign_ok")),
                "iv_development": _float(fila.get("iv")),
                "iv_by_sample": iv_por_muestra.get(variable, {}),
                "csi": csi.get(variable, []),
            }
        )
    return salida


def _validacion(study: Study) -> dict[str, Any]:
    """El estado técnico de la validación y, si no pasa, qué lo decide en pocas palabras."""
    if not study.artifacts.has("validation", "card"):
        raise _CampoAusenteError("la corrida no corrió la validación formal")
    card = study.artifacts.get("validation", "card")
    estado = str(getattr(card, "overall_status", "") or "")
    motivo: str | None = None
    if estado != "pass":
        from bayesrisk.guided.summaries import _pruebas_decisivas

        decisivas = _pruebas_decisivas(study, breve=True)
        if decisivas:
            resto = len(decisivas) - 1
            motivo = decisivas[0] + (
                f" y {resto} {'prueba más' if resto == 1 else 'pruebas más'}" if resto else ""
            )
    return {"status": estado, "reason": motivo}


# ── IFRS 9 ───────────────────────────────────────────────────────────────────────────────────


def _ifrs9(study: Study, faltantes: dict[str, str]) -> dict[str, Any]:
    card = study.artifacts.get("provisioning_ifrs9", "card")
    por_etapa, total = _provision_por_etapa(study)
    return {
        "as_of": str(card.as_of_date),
        "scenarios": [
            {"name": str(nombre), "weight": _float(dict(card.scenario_weights).get(nombre))}
            for nombre in card.scenarios
        ],
        "amount_columns": _campo(faltantes, "amount_columns", lambda: _columnas_de_monto(study)),
        "by_stage": por_etapa,
        "total": total,
    }


def _columnas_de_monto(study: Study) -> dict[str, str]:
    """Las columnas de exposición, saldo y límite (la regla de la unidad de §3.7)."""
    seccion = getattr(study.config, "provisioning_ifrs9", None)
    ead = seccion.get("ead") if isinstance(seccion, Mapping) else getattr(seccion, "ead", None)
    if ead is None:
        raise _CampoAusenteError("la corrida no declara cómo mide su exposición")

    def columna(nombre: str) -> str:
        valor = ead.get(nombre) if isinstance(ead, Mapping) else getattr(ead, nombre)
        return str(valor)

    return {
        "exposure": columna("ead_col"),
        "balance": columna("drawn_col"),
        "limit": columna("limit_col"),
    }


def _provision_por_etapa(study: Study) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Operaciones, exposición, ECL y cobertura por etapa, sumadas sobre las carteras."""
    tabla = study.artifacts.get("provisioning_ifrs9", "summary")
    filas: list[dict[str, Any]] = []
    for etapa in (1, 2, 3):
        grupo = tabla[tabla["stage"].astype(int) == etapa]
        filas.append(_fila_de_provision(etapa, grupo))
    return filas, _fila_de_provision(None, tabla)


def _fila_de_provision(etapa: int | None, grupo: Any) -> dict[str, Any]:
    exposicion = float(grupo["total_ead"].astype(float).sum())
    ecl = float(grupo["total_ecl_reported"].astype(float).sum())
    fila: dict[str, Any] = {
        "n": int(grupo["n_rows"].astype(int).sum()),
        "exposure": exposicion,
        "ecl": ecl,
        "coverage": ecl / exposicion if exposicion > 0 else None,
    }
    return {"stage": etapa, **fila} if etapa is not None else fila
