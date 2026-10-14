"""Las tarjetas que la pantalla puede monitorear (SDD-33 §4.3, capa B).

El trabajo «Monitorear un modelo en uso» parte de una tarjeta guardada. En la pantalla llega por
dos caminos, y los dos terminan en una carpeta bajo el ``workdir`` cuya ruta se escribe en
``monitoring.bundle``:

- **De una corrida del scorecard hecha en la pantalla.** :func:`guardar_de_la_corrida` la escribe
  junto a la corrida (``runs/<run_id>/tarjeta/``) cuando se puede monitorear —terminada, con su
  escala maestra—, con una ficha pequeña al lado (``runs/<run_id>/tarjeta.json``) para listarla sin
  abrir el ``results.json``.
- **Subida como .zip** (la carpeta que guarda ``FittedScorecardBundle.save``, comprimida).
  :func:`subir_zip` la valida con la misma función que ``bayesrisk.Monitor`` —una tarjeta que la
  puerta guiada rechaza, la pantalla también, con el mismo motivo— y la deja en
  ``cards/tarjeta-<huella>/``.

La capa ``ui`` no importa dominios (D-HASH-5, ``test_ui_no_importa_modulos_de_dominio``): leer y
validar una tarjeta pasa por :mod:`bayesrisk.guided.monitor`, con import perezoso.
"""

from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from bayesrisk.ui.exceptions import UiCardError

if TYPE_CHECKING:
    from bayesrisk.core.study import Study

__all__ = ["CARDS_SUBDIR", "TARJETA_DIRNAME", "guardar_de_la_corrida", "listar", "subir_zip"]

#: La carpeta de la tarjeta dentro de una corrida de la pantalla, y su ficha al lado.
TARJETA_DIRNAME: Final = "tarjeta"
_FICHA: Final = "tarjeta.json"
#: Donde quedan las tarjetas subidas, cada una con su huella en el nombre.
CARDS_SUBDIR: Final = "cards"
#: Los únicos archivos de una tarjeta (``FittedScorecardBundle.save``).
_ARCHIVOS: Final = frozenset({"manifest.json", "bins.parquet"})


def guardar_de_la_corrida(study: Study, destino: Path) -> dict[str, Any] | None:
    """Escribe la tarjeta monitoreable de ``study`` en ``destino/tarjeta`` y su ficha al lado.

    Devuelve la ficha, o ``None`` si la corrida no tiene tarjeta que monitorear (no es un error:
    una corrida parcial, sin escala maestra o de otra familia). ``destino`` es el temporal de la
    corrida que :func:`bayesrisk.ui.runs.save` publica de una vez.
    """
    from bayesrisk.guided.monitor import tarjeta_de_la_corrida

    tarjeta = tarjeta_de_la_corrida(study)
    if tarjeta is None:
        return None
    tarjeta.save(destino / TARJETA_DIRNAME)
    linaje = study.run_context.lineage
    ficha = {
        "origin": "run",
        "run_id": study.run_context.run_id,
        "name": str(study.config.name),
        "created_at": linaje.created_at.isoformat() if linaje is not None else None,
        "bundle_hash": tarjeta.bundle_hash,
        "n_grades": len(tarjeta.manifest["master_scale"]["grade_pd"]),
    }
    (destino / _FICHA).write_text(json.dumps(ficha, ensure_ascii=False), encoding="utf-8")
    return ficha


def listar(workdir: Path) -> list[dict[str, Any]]:
    """Las tarjetas monitoreables del ``workdir``: las de las corridas y las subidas.

    Cada una con su ``path`` absoluto (lo que se escribe en ``monitoring.bundle``), su huella, su
    origen y su rótulo. Las de las corridas, de la más reciente a la más antigua; después, las
    subidas. Una ficha ilegible o una carpeta a medias no se lista.
    """
    raiz = Path(workdir).resolve()
    salida: list[dict[str, Any]] = []
    for ficha_path in sorted((raiz / "runs").glob(f"*/{_FICHA}")):
        carpeta = ficha_path.parent / TARJETA_DIRNAME
        try:
            ficha = json.loads(ficha_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(ficha, dict) or not _completa(carpeta):
            continue
        salida.append({**_ficha_publica(ficha), "path": str(carpeta)})
    salida.sort(key=lambda f: str(f.get("created_at") or ""), reverse=True)
    for manifiesto in sorted((raiz / CARDS_SUBDIR).glob("tarjeta-*/manifest.json")):
        try:
            datos = json.loads(manifiesto.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(datos, dict) or not _completa(manifiesto.parent):
            continue
        salida.append(
            {
                "origin": "upload",
                "run_id": None,
                "name": manifiesto.parent.name,
                "created_at": None,
                "bundle_hash": str(datos.get("bundle_hash", "")),
                "n_grades": len(_mapping(datos.get("master_scale")).get("grade_pd", ())),
                "path": str(manifiesto.parent),
            }
        )
    return salida


def subir_zip(content: bytes, filename: Any, *, workdir: Path, max_bytes: int) -> dict[str, Any]:
    """Valida una tarjeta subida como ``.zip`` y la deja en ``cards/tarjeta-<huella>/``.

    El ``.zip`` trae los dos archivos de la tarjeta, sueltos o dentro de una sola carpeta; nada
    más. Se comprueba antes de extraer: el nombre de cada entrada (sin rutas absolutas ni ``..``),
    que no haya otros archivos y que lo descomprimido no pase de ``max_bytes`` —el tope de las
    subidas—. Después, la misma lectura que ``bayesrisk.Monitor``: esquema 4 con la escala maestra.

    Raises
    ------
    UiCardError
        Si el archivo no es un ``.zip`` de tarjeta o la tarjeta no se puede monitorear (→ 422, con
        el motivo).
    """
    nombre = str(filename or "")
    if not nombre.lower().endswith(".zip"):
        raise UiCardError("La tarjeta se sube como .zip: la carpeta de la tarjeta, comprimida.")
    if len(content) > max_bytes:
        raise UiCardError(f"El .zip pesa más que el tope de subida ({max_bytes} bytes).")
    try:
        archivo = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise UiCardError("El archivo no es un .zip legible.") from exc
    with archivo:
        entradas = _entradas_de_la_tarjeta(archivo, max_bytes)
        raiz = Path(workdir).resolve() / CARDS_SUBDIR
        raiz.mkdir(parents=True, exist_ok=True)
        temporal = raiz / f".subida-{uuid.uuid4().hex[:12]}.tmp"
        temporal.mkdir()
        try:
            for archivo_destino, info in entradas.items():
                with archivo.open(info) as origen, (temporal / archivo_destino).open("wb") as sal:
                    shutil.copyfileobj(origen, sal)
            from bayesrisk.guided.monitor import MonitorInputError, leer_tarjeta_monitoreable

            try:
                tarjeta = leer_tarjeta_monitoreable(temporal)
            except MonitorInputError as exc:
                raise UiCardError(str(exc)) from exc
            destino = raiz / f"tarjeta-{tarjeta.bundle_hash[:16]}"
            _publicar(temporal, destino, tarjeta.bundle_hash)
        except BaseException:
            shutil.rmtree(temporal, ignore_errors=True)
            raise
    return {
        "origin": "upload",
        "run_id": None,
        "name": destino.name,
        "created_at": None,
        "bundle_hash": tarjeta.bundle_hash,
        "n_grades": len(tarjeta.manifest["master_scale"]["grade_pd"]),
        "path": str(destino),
    }


def _publicar(temporal: Path, destino: Path, huella: str) -> None:
    """Deja la tarjeta validada en ``destino``; una carpeta previa sólo se reutiliza si es íntegra.

    El nombre lleva la huella, pero no la demuestra: una carpeta a medias (sin ``bins.parquet``) o
    con otro contenido no se reutiliza, se reemplaza por la que se acaba de validar (pasada 1 de
    Codex sobre la capa B). Si otra subida de la misma tarjeta la publica entre tanto, se usa la
    suya cuando es íntegra.
    """
    if _integra(destino, huella):
        shutil.rmtree(temporal)
        return
    if destino.exists():
        apartado = destino.with_name(f".{destino.name}.rota-{uuid.uuid4().hex[:8]}")
        destino.rename(apartado)
        shutil.rmtree(apartado, ignore_errors=True)
    try:
        temporal.rename(destino)
    except OSError:
        if not _integra(destino, huella):
            raise
        shutil.rmtree(temporal)


def _integra(carpeta: Path, huella: str) -> bool:
    """Dice si ``carpeta`` es una tarjeta monitoreable con exactamente esta huella."""
    if not _completa(carpeta):
        return False
    from bayesrisk.guided.monitor import MonitorInputError, leer_tarjeta_monitoreable

    try:
        return leer_tarjeta_monitoreable(carpeta).bundle_hash == huella
    except (MonitorInputError, OSError):
        return False


def _completa(carpeta: Path) -> bool:
    """Los dos archivos de una tarjeta están (la lista no ofrece una carpeta a medias)."""
    return all((carpeta / nombre).is_file() for nombre in _ARCHIVOS)


def _entradas_de_la_tarjeta(archivo: zipfile.ZipFile, max_bytes: int) -> dict[str, Any]:
    """Los dos archivos de la tarjeta dentro del ``.zip``, comprobados antes de extraer nada."""
    entradas: dict[str, Any] = {}
    prefijos: set[str] = set()
    total = 0
    for info in archivo.infolist():
        if info.is_dir():
            continue
        ruta = PurePosixPath(info.filename.replace("\\", "/"))
        if ruta.is_absolute() or ".." in ruta.parts or len(ruta.parts) > 2:
            raise UiCardError(
                f"El .zip trae una entrada fuera de la tarjeta ({info.filename!r}): sólo puede "
                "traer manifest.json y bins.parquet, sueltos o dentro de una carpeta."
            )
        if ruta.name not in _ARCHIVOS or ruta.name in entradas:
            raise UiCardError(
                f"El .zip trae {info.filename!r}, que no es parte de una tarjeta: sólo puede traer "
                "manifest.json y bins.parquet."
            )
        prefijos.add("/".join(ruta.parts[:-1]))
        total += int(info.file_size)
        if total > max_bytes:
            raise UiCardError(
                f"La tarjeta descomprimida pasa el tope de subida ({max_bytes} bytes)."
            )
        entradas[ruta.name] = info
    if set(entradas) != _ARCHIVOS or len(prefijos) != 1:
        raise UiCardError(
            "El .zip no es una tarjeta: tiene que traer manifest.json y bins.parquet, juntos en la "
            "misma carpeta."
        )
    return entradas


def _ficha_publica(ficha: dict[str, Any]) -> dict[str, Any]:
    return {
        "origin": "run",
        "run_id": ficha.get("run_id"),
        "name": str(ficha.get("name") or ""),
        "created_at": ficha.get("created_at"),
        "bundle_hash": str(ficha.get("bundle_hash") or ""),
        "n_grades": int(ficha.get("n_grades") or 0),
    }


def _mapping(valor: Any) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}
