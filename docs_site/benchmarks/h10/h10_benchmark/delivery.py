"""Descarga H10 autocontenida: inventario, huellas y extracción sin rutas ambiguas."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath

from .contract import sha256, verify_sources

MAX_FILES = 4000
MAX_FILE_BYTES = 128 * 1024**2
MAX_TOTAL_BYTES = 2 * 1024**3


def inspect_archive(archive: Path, envelope: dict) -> dict:
    """El manifiesto externo identifica todos los miembros, también los inesperados."""
    if sha256(archive) != envelope["archive_sha256"]:
        raise ValueError("huella de descarga diferente")
    actual, folded, total = {}, set(), 0
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if (
                not member.isfile()
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or ":" in member.name
                or str(path) != member.name
                or member.pax_headers
                or member.uname
                or member.gname
                or member.uid
                or member.gid
                or member.issparse()
            ):
                raise ValueError(f"miembro de descarga no admitido: {member.name}")
            if member.name.casefold() in folded:
                raise ValueError("miembro duplicado/ambiguo en descarga")
            folded.add(member.name.casefold())
            total += member.size
            if len(folded) > MAX_FILES or member.size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("descarga excede límites de inspección")
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("miembro sin contenido")
            actual[member.name] = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != envelope["files"]:
        raise ValueError("censo/huellas de miembros distinto al manifiesto externo")
    return {"files": len(actual), "bytes": total, "archive_sha256": envelope["archive_sha256"]}


def extract_archive(archive: Path, envelope_path: Path, destination: Path) -> dict:
    """Nunca sobrescribe una carpeta previa ni ejecuta auxiliares al extraer."""
    if destination.exists():
        raise ValueError("destino ya existe; conservar la reproducción previa")
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    result = inspect_archive(archive, envelope)
    destination.mkdir(parents=True)
    root = destination.resolve()
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            path = (root / member.name).resolve()
            if not path.is_relative_to(root):
                raise ValueError("ruta fuera del destino")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                source = tar.extractfile(member)
                if source is None:
                    raise ValueError("miembro sin contenido")
                for chunk in iter(lambda source=source: source.read(1024 * 1024), b""):
                    output.write(chunk)
    verify_sources(root)
    return result
