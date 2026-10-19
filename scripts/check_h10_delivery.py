"""Inspecciona todos los miembros H10 y aplica los oráculos vigentes sin cambiar H9R."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import importlib.util
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs_site/benchmarks/h10/h10_benchmark"
PERSONAL = re.compile(
    r"(?i)(?:[a-z]:[\\/](?:users|proyectos)|/home/|/users/|appdata[\\/]|"
    r"onedrive|privado/|privado\\|access_token=|authorization: bearer)"
)
TEXT = {".py", ".md", ".html", ".json", ".jsonl", ".yaml", ".txt", ".in", ".csv"}


def public_prose(text):
    """Los códigos internos sólo caben en datos técnicos y anexos de auditoría."""
    from bayesrisk.core.markers import DECLARED_MARKERS

    if any(marker in html.unescape(text) for marker in DECLARED_MARKERS):
        raise ValueError("código interno en prosa pública")


def load_file(name, path):
    """Import explícito y trazable; nunca busca auxiliares por PYTHONPATH."""
    kwargs = (
        {"submodule_search_locations": [str(path.parent)]} if path.name == "__init__.py" else {}
    )
    spec = importlib.util.spec_from_file_location(name, path, **kwargs)
    if spec is None or spec.loader is None:
        raise ValueError("no se pudo cargar el oráculo declarado")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def strings(value):
    """Proyecta claves y valores decodificados, sin ocultar arrays de fragmentos."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            yield "".join(value)
        for item in value:
            yield from strings(item)


def parse_json(text):
    """Rechaza claves duplicadas que distintos lectores interpretarían de otro modo."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("clave JSON duplicada")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs)


def projections(path: Path):
    """Recorre cada formato efectivamente admitido en la entrega; lo opaco falla."""
    suffix = path.suffix.lower()
    if suffix in TEXT:
        raw = path.read_text(encoding="utf-8")
        if suffix == ".json":
            yield ".txt", "\n".join(strings(parse_json(raw)))
            if path.name.endswith("_summaries.json"):
                public_prose("\n".join(strings(parse_json(raw))))
        elif suffix == ".jsonl":
            yield (
                ".txt",
                "\n".join(text for line in raw.splitlines() for text in strings(parse_json(line))),
            )
        elif suffix == ".csv":
            import csv

            yield ".txt", "\n".join(cell for row in csv.reader(io.StringIO(raw)) for cell in row)
        elif suffix == ".md":
            public_prose(raw)
        elif suffix == ".html":
            from lxml import html as lhtml

            tree = lhtml.fromstring(raw)
            yield ".txt", tree.text_content()
            yield ".txt", "\n".join(str(v) for e in tree.iter() for v in e.attrib.values())
        yield suffix if suffix in {".py", ".md", ".html"} else ".txt", raw
    elif suffix == ".ipynb":
        notebook = parse_json(path.read_text(encoding="utf-8"))
        if notebook.get("nbformat") != 4:
            raise ValueError("notebook no admitido")
        yield ".txt", "\n".join(strings(notebook.get("metadata", {})))
        for cell in notebook["cells"]:
            if cell["cell_type"] not in {"code", "markdown"}:
                raise ValueError("celda opaca no admitida")
            source = cell["source"]
            if cell["cell_type"] == "markdown":
                public_prose("".join(source))
            yield ".py" if cell["cell_type"] == "code" else ".md", "".join(source)
            yield ".txt", "\n".join(strings(cell.get("metadata", {})))
            if cell.get("attachments"):
                raise ValueError("attachments no previstos por estos notebooks")
            for output in cell.get("outputs", []):
                if output.get("output_type") == "error":
                    raise ValueError("notebook publicado contiene ejecución fallida")
                if "text" in output:
                    public_prose("".join(output["text"]))
                    yield ".txt", "".join(output["text"])
                for mime, value in output.get("data", {}).items():
                    extension = {
                        "text/plain": ".txt",
                        "text/html": ".html",
                        "image/svg+xml": ".svg",
                        "application/json": ".txt",
                    }.get(mime)
                    if extension is None:
                        raise ValueError(f"MIME no admitido: {mime}")
                    public_prose("\n".join(strings(value)))
                    yield extension, "\n".join(strings(value))
                yield ".txt", "\n".join(strings(output.get("metadata", {})))
    elif suffix in {".docx", ".xlsx"}:
        from lxml import etree

        if suffix == ".docx" and path.name == "scorecard_report.docx":
            from h10_benchmark.presentation import verify_word_layout

            verify_word_layout(path)

        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise ValueError("miembro OOXML duplicado")
            for name in names:
                if ".." in Path(name).parts or "\\" in name or name.startswith("/"):
                    raise ValueError("ruta OOXML ambigua")
                content = archive.read(name)
                if name.endswith((".xml", ".rels")):
                    tree = etree.fromstring(
                        content, parser=etree.XMLParser(resolve_entities=False, no_network=True)
                    )
                    if tree.getroottree().docinfo.doctype:
                        raise ValueError("DTD OOXML no admitido")
                    if name == "word/document.xml":
                        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                        body = tree.find("w:body", ns)
                        appendix = False
                        if body is None:
                            raise ValueError("Word sin cuerpo")
                        for element in body:
                            text = "".join(element.itertext())
                            heading = element.find("w:pPr/w:pStyle", ns)
                            if (
                                heading is not None
                                and heading.get(f"{{{ns['w']}}}val") == "Heading1"
                                and text.startswith("Anexo A")
                            ):
                                appendix = True
                            if not appendix:
                                public_prose(text)
                        if not appendix:
                            raise ValueError("Word sin anexo de auditoría identificado")
                    yield ".txt", "\n".join(str(v) for e in tree.iter() for v in e.attrib.values())
                    yield (
                        ".txt",
                        "\n".join(
                            "".join(e.itertext())
                            for e in tree.iter()
                            if etree.QName(e).localname in {"p", "si", "is"}
                        ),
                    )
                    yield ".txt", "\n".join(tree.itertext())
                    if any(
                        etree.QName(e).localname in {"altChunk", "oleObject", "externalLink"}
                        for e in tree.iter()
                    ):
                        raise ValueError("contenido activo OOXML no admitido")
                    if name.endswith(".rels") and any(
                        e.get("TargetMode") == "External" for e in tree.iter()
                    ):
                        raise ValueError("relación externa OOXML no admitida")
                elif name.startswith(("word/media/", "docProps/")) and name.endswith(
                    (".png", ".jpeg")
                ):
                    from PIL import Image

                    with Image.open(io.BytesIO(content)) as picture:
                        picture.verify()
                        known_thumbnail = (
                            name == "docProps/thumbnail.jpeg"
                            and hashlib.sha256(content).hexdigest()
                            == "96367138dc44ce09bf2c8f0f8e49348a1478d2c5c0af69bbc2bbc38b63cdcead"
                        )
                        if not known_thumbnail and any(
                            isinstance(value, bytes) for value in picture.info.values()
                        ):
                            raise ValueError("metadata binaria de imagen no inspeccionada")
                        yield ".txt", "\n".join(strings(picture.info))
                else:
                    raise ValueError(f"miembro OOXML opaco: {name}")
    elif suffix == ".parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        footer = pq.read_metadata(path)
        for key, value in (footer.metadata or {}).items():
            if key == b"ARROW:schema":
                stream = pa.BufferReader(base64.b64decode(value, validate=True))
                decoded = pa.ipc.read_schema(stream)
                if stream.tell() != stream.size() or not decoded.equals(
                    table.schema, check_metadata=True
                ):
                    raise ValueError("schema Parquet opaco o distinto")
                yield ".txt", str(decoded)
            else:
                yield ".txt", key.decode() + "\n" + value.decode()
        yield ".txt", str(table.schema)
        for key, value in (table.schema.metadata or {}).items():
            if key == b"ARROW:schema":
                raise ValueError("schema redundante inesperado en metadata decodificada")
            yield ".txt", key.decode() + "\n" + value.decode()
        yield ".txt", str(pq.read_metadata(path).created_by)
        for field, column in zip(table.schema, table.columns, strict=True):
            if field.metadata:
                yield ".txt", "\n".join(k.decode() + v.decode() for k, v in field.metadata.items())
            if pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
                yield ".txt", "\n".join(value for value in column.to_pylist() if value is not None)
            elif not (
                pa.types.is_integer(field.type)
                or pa.types.is_floating(field.type)
                or pa.types.is_boolean(field.type)
                or pa.types.is_timestamp(field.type)
            ):
                raise ValueError(f"tipo Parquet no admitido: {field.type}")
    elif suffix == ".zip":
        from h10_benchmark.contract import SOURCES, sha256

        matches = [case for case, spec in SOURCES.items() if sha256(path) == spec["sha256"]]
        if len(matches) != 1:
            raise ValueError("ZIP ajeno a fuentes UCI exactas")
        with zipfile.ZipFile(path) as archive:
            if matches[0] == "german":
                if set(archive.namelist()) != {
                    "german.data",
                    "german.data-numeric",
                    "german.doc",
                    "Index",
                }:
                    raise ValueError("miembros German distintos")
                for name in archive.namelist():
                    yield ".txt", archive.read(name).decode("utf-8")
            else:
                import xlrd

                member = SOURCES["taiwan"]["member"]
                if archive.namelist() != [member]:
                    raise ValueError("miembros Taiwan distintos")
                book = xlrd.open_workbook(file_contents=archive.read(member))
                yield ".txt", str(book.user_name)
                yield ".txt", str(book.name_map)
                for sheet in book.sheets():
                    yield ".txt", sheet.name
                    yield (
                        ".txt",
                        "\n".join(
                            str(cell.value)
                            for row in sheet
                            for cell in row
                            if cell.ctype == xlrd.XL_CELL_TEXT
                        ),
                    )
    else:
        raise ValueError(f"formato de descarga no admitido: {path.name}")


def inspect_content(root: Path) -> dict:
    """Capacidad y privacidad en todas las proyecciones; copy HTML con el gate vigente."""
    oracle = load_file("h10_copy_oracle", ROOT / "scripts/readiness_h9r/copy_gate.py")
    reports = load_file("h10_report_oracle", ROOT / "scripts/check_demo_report_copy.py")
    count = 0
    with tempfile.TemporaryDirectory(prefix="h10-projections-") as directory:
        projected = []
        mapping = {}
        for source in sorted(root.rglob("*")):
            if not source.is_file():
                continue
            if "__pycache__" in source.parts:
                raise ValueError("cache opaco en descarga")
            if PERSONAL.search(source.relative_to(root).as_posix()):
                raise ValueError("ruta personal en nombre de miembro")
            for number, (suffix, text) in enumerate(projections(source)):
                if PERSONAL.search(html.unescape(text).replace("\\\\", "\\")):
                    raise ValueError(
                        f"ruta personal/privada en {source.relative_to(root)} proyección {number}"
                    )
                destination = Path(directory) / f"projection-{count}{suffix}"
                destination.write_text(text, encoding="utf-8")
                projected.append(destination)
                mapping[str(destination)] = f"{source.relative_to(root)}:{number}"
                count += 1
            if source.name == "scorecard_report.html":
                failures = reports._fallos_html(source)
                if failures:
                    raise ValueError(str(failures))
        failures = oracle.scan_capacity_claims(projected)
        if failures:
            for failure in failures:
                failure["path"] = mapping.get(str(failure["path"]), failure["path"])
            raise ValueError(str(failures))
    return {"projections": count, "capacity_findings": 0, "privacy_findings": 0}


def main() -> None:
    """Verifica el archivo y luego su contenido, fuera del checkout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("envelope", type=Path)
    args = parser.parse_args()
    load_file("h10_benchmark", PACKAGE / "__init__.py")
    from h10_benchmark.delivery import extract_archive

    with tempfile.TemporaryDirectory(prefix="h10-inspection-") as directory:
        destination = Path(directory) / "delivery"
        result = extract_archive(args.archive, args.envelope, destination)
        from h10_benchmark.contract import sha256

        for source in PACKAGE.parent.rglob("*"):
            if (
                source.is_file()
                and "__pycache__" not in source.parts
                and source.name != "delivery.json"
            ):
                published = destination / source.relative_to(PACKAGE.parent)
                if not published.is_file() or sha256(source) != sha256(published):
                    raise ValueError(f"auxiliar descargado difiere del checkout: {source.name}")
        result.update(inspect_content(destination))
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
