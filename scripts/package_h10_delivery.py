"""Construye derivados portables del benchmark medido; nunca carga Studies o pickles."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

from check_h10_delivery import PACKAGE, load_file
from lxml import etree

load_file("h10_benchmark", PACKAGE / "__init__.py")
from h10_benchmark.contract import CASES, RECIPES, dump, sha256  # noqa: E402
from h10_benchmark.presentation import layout_word  # noqa: E402


def replace_strings(value, mapping):
    """Sólo reemplaza las rutas exactas declaradas; no altera cifras ni etiquetas."""
    if isinstance(value, str):
        if ":" not in value:
            return value
        for source, target in mapping:
            value = value.replace(source, target)
            value = value.replace(json.dumps(source)[1:-1], target)
        return value
    if isinstance(value, list):
        return [replace_strings(item, mapping) for item in value]
    if isinstance(value, dict):
        return {
            replace_strings(key, mapping): replace_strings(item, mapping)
            for key, item in value.items()
        }
    return value


def portable(source, destination, mapping):
    """Conserva datos; reescribe texto/OOXML sin perder runs, tablas ni relaciones."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".json":
        dump(destination, replace_strings(json.loads(source.read_text(encoding="utf-8")), mapping))
    elif source.suffix in {".html", ".txt", ".yaml", ".log", ".jsonl"}:
        text = replace_strings(source.read_text(encoding="utf-8"), mapping)
        # Las rutas de Windows también aparecen escapadas dentro de JSON embebido en HTML.
        for original, target in mapping:
            text = text.replace(json.dumps(original)[1:-1], target)
        destination.write_text(text, encoding="utf-8")
    elif source.suffix in {".docx", ".xlsx"}:
        with (
            zipfile.ZipFile(source) as before,
            zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as after,
        ):
            for info in before.infolist():
                content = before.read(info.filename)
                if info.filename.endswith((".xml", ".rels")):
                    tree = etree.fromstring(
                        content, parser=etree.XMLParser(resolve_entities=False, no_network=True)
                    )
                    for element in tree.iter():
                        if element.text:
                            element.text = replace_strings(element.text, mapping)
                        if element.tail:
                            element.tail = replace_strings(element.tail, mapping)
                        for key, value in element.attrib.items():
                            element.set(key, replace_strings(value, mapping))
                    content = etree.tostring(
                        tree, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                after.writestr(info, content)
    else:
        shutil.copyfile(source, destination)
    if source.suffix == ".docx":
        layout_word(destination)


def inventory(root):
    """Manifiesto no circular: el sobre externo incluye delivery.json."""
    return {
        p.relative_to(root).as_posix(): sha256(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "delivery.json" and "__pycache__" not in p.parts
    }


def manifest(root):
    """Registra el inventario completo sin incluirse circularmente."""
    dump(
        root / "delivery.json",
        {"cases": list(CASES), "recipes": list(RECIPES), "files": inventory(root)},
    )


def prepare(raw: Path, destination: Path):
    """Proyecta la primera repetición y evidencia de las tres, con huellas de procedencia."""
    if destination.exists():
        raise ValueError("destino existente; conservar la entrega anterior")
    destination.mkdir(parents=True)
    provenance = []
    mapping = []
    for case in CASES:
        for recipe, options in RECIPES.items():
            if options is None:
                continue
            stem = f"{case}_{recipe}"
            config = json.loads(
                (raw / "repetition-1" / f"{stem}_config.json").read_text(encoding="utf-8")
            )
            mapping.append((config["data"]["load"]["source"], f"prepared/{case}/input.parquet"))
            mapping.append((config["report"]["output_dir"], f"artifacts/{stem}/reports"))
    # Todos son prefijos de esta ejecución suministrada explícitamente, no búsquedas genéricas.
    for path, target in (
        (raw.parent / "venv", "environment/benchmark"),
        (raw.parent / "viewer", "environment/notebook"),
        (raw, "measurement"),
        (raw.parent, "evidence"),
    ):
        mapping.extend([(str(path.resolve()), target), (path.resolve().as_posix(), target)])
    mapping.sort(key=lambda item: len(item[0]), reverse=True)

    def copy(source, name):
        target = destination / name
        portable(source, target, mapping)
        provenance.append(
            {
                "source": source.relative_to(raw).as_posix(),
                "published": name,
                "original_sha256": sha256(source),
                "published_sha256": sha256(target),
            }
        )

    for source in PACKAGE.parent.rglob("*"):
        if (
            source.is_file()
            and "__pycache__" not in source.parts
            and source.name != "delivery.json"
        ):
            target = destination / source.relative_to(PACKAGE.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for case in CASES:
        for source in (raw / "prepared-v2" / case).iterdir():
            if source.is_file():
                copy(source, f"prepared/{case}/{source.name}")
    copy(raw / "prepared-v2/predeclared.json", "prepared/predeclared.json")
    for source in (raw / "cache").glob("*.zip"):
        copy(source, f"cache/{source.name}")
    for source in (raw / "aggregate-v2").iterdir():
        if source.is_file():
            copy(source, f"aggregate/{source.name}")
    for source in (raw / "repetition-1").rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(raw / "repetition-1")
        if "projects" in relative.parts or source.name.endswith("_expected.json"):
            continue
        copy(
            source,
            "results/"
            + relative.as_posix().removesuffix(".log")
            + (".txt" if source.suffix == ".log" else ""),
        )
    for number, name in enumerate(("repetition-1", "repetition-2b", "repetition-3"), 1):
        for source in (raw / name).iterdir():
            if source.name in {
                "results.json",
                "environment.json",
                "execution.json",
                "coverage.json",
            } or source.name.endswith(("_canonical.json", "_master_scale.json")):
                copy(source, f"repetitions/{number}/{source.name}")
    for case in CASES:
        for recipe, options in RECIPES.items():
            if options is None:
                continue
            stem = f"{case}_{recipe}"
            for directory in ("reports", "excel"):
                for source in (raw / "repetition-1/projects" / stem / directory).iterdir():
                    if source.is_file():
                        copy(source, f"artifacts/{stem}/{directory}/{source.name}")
            copy(raw / "reconciliation" / f"{stem}_expected.json", f"expected/{stem}.json")
            copy(
                raw / "repetition-1/projects" / stem / "run/audit_trail.jsonl",
                f"artifacts/{stem}/run/audit_trail.jsonl",
            )
    for source, target in (
        ("negative-controls.json", "verification/negative-controls.json"),
        ("reconciliation/artifacts.json", "verification/artifacts-original.json"),
        ("doors-v2/verification-all.json", "verification/doors.json"),
        ("sondas-finales.json", "verification/fit-instrumentation.json"),
    ):
        copy(raw / source, target)
    for case in CASES:
        copy(raw / "holdout" / case / "verification.json", f"verification/holdout-{case}.json")
    dump(
        destination / "provenance.json",
        {
            "method": (
                "Reemplazo exclusivo de rutas de entrada/informe/entorno por destinos relativos; "
                "cifras y etiquetas intactas. Originales preservados."
            ),
            "files": provenance,
        },
    )
    manifest(destination)


def pack(root: Path, archive: Path, envelope: Path):
    """Archivo determinista, sólo miembros regulares; el sobre ancla sus bytes."""
    manifest(root)
    files = {**inventory(root), "delivery.json": sha256(root / "delivery.json")}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with (
        archive.open("wb") as stream,
        gzip.GzipFile(fileobj=stream, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar,
    ):
        for name in sorted(files):
            content = (root / name).read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = 0o644
            tar.addfile(member, io.BytesIO(content))
    dump(envelope, {"archive_sha256": sha256(archive), "files": files})
    print(
        json.dumps(
            {"files": len(files), "bytes": archive.stat().st_size, "sha256": sha256(archive)}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "pack"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--envelope", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.source.resolve(), args.destination.resolve())
    else:
        if args.envelope is None:
            parser.error("pack exige --envelope")
        pack(args.source, args.destination, args.envelope)
