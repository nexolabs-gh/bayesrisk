"""Presentación del benchmark: tablas anchas legibles sin cambiar sus celdas."""

from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def verify_word_layout(path: Path) -> int:
    """Detecta tablas anchas sin su página/tamaño declarado, incluso con celdas correctas."""
    from lxml import etree

    with zipfile.ZipFile(path) as source:
        tree = etree.fromstring(source.read("word/document.xml"))
    count = 0
    for table in tree.findall("w:body/w:tbl", NS):
        columns = len(table.findall("w:tblGrid/w:gridCol", NS))
        if columns <= 8:
            continue
        count += 1
        section = None
        following = table.getnext()
        while following is not None and etree.QName(following).localname == "p":
            section = following.find("w:pPr/w:sectPr", NS)
            if section is not None:
                break
            following = following.getnext()
        size = None if section is None else section.find("w:pgSz", NS)
        width, height = (23811, 16838) if columns > 15 else (16838, 11906)
        if size is None or any(
            size.get(f"{{{W}}}{key}") != value
            for key, value in (("orient", "landscape"), ("w", str(width)), ("h", str(height)))
        ):
            raise ValueError("tabla Word ancha sin página apaisada acreditada")
        if any(
            run.find("w:rPr/w:sz", NS) is None
            or run.find("w:rPr/w:sz", NS).get(f"{{{W}}}val") != "18"
            for run in table.findall(".//w:r", NS)
        ):
            raise ValueError("tabla Word ancha sin tamaño tipográfico declarado")
    return count


def layout_word(path: Path) -> int:
    """Dedica páginas apaisadas a tablas de más de ocho columnas; contenido intacto."""
    from lxml import etree

    original = path.read_bytes()
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "word/document.xml":
                tree = etree.fromstring(content)
                body = tree.find("w:body", NS)
                default = body.find("w:sectPr", NS)
                if default is None:
                    raise ValueError("Word sin sección base")
                if tree.xpath(".//w:bookmarkStart[@w:name='H10TablasApaisadas']", namespaces=NS):
                    return 0
                for table in list(body.findall("w:tbl", NS)):
                    columns = len(table.findall("w:tblGrid/w:gridCol", NS))
                    if columns <= 8:
                        continue
                    count += 1
                    # La sección anterior termina antes de la caption; ésta queda con la tabla.
                    first = table.getprevious()
                    if first is None or etree.QName(first).localname != "p":
                        first = table
                    before = etree.Element(f"{{{W}}}p")
                    before_properties = etree.SubElement(before, f"{{{W}}}pPr")
                    before_properties.append(copy.deepcopy(default))
                    body.insert(body.index(first), before)
                    # La sección apaisada termina después del aviso de truncado, si existe.
                    last = table
                    neighbor = table.getnext()
                    if neighbor is not None and "mostrando" in "".join(neighbor.itertext()).lower():
                        last = neighbor
                    after = etree.Element(f"{{{W}}}p")
                    properties = etree.SubElement(after, f"{{{W}}}pPr")
                    landscape = copy.deepcopy(default)
                    size = landscape.find("w:pgSz", NS)
                    width, height = (23811, 16838) if columns > 15 else (16838, 11906)
                    size.set(f"{{{W}}}w", str(width))
                    size.set(f"{{{W}}}h", str(height))
                    size.set(f"{{{W}}}orient", "landscape")
                    margins = landscape.find("w:pgMar", NS)
                    for side in ("left", "right", "top", "bottom"):
                        margins.set(f"{{{W}}}{side}", "936")
                    properties.append(landscape)
                    body.insert(body.index(last) + 1, after)
                    cell_width = (width - 1872) // columns
                    for column in table.findall("w:tblGrid/w:gridCol", NS):
                        column.set(f"{{{W}}}w", str(cell_width))
                    for cell in table.findall("w:tr/w:tc", NS):
                        cell_properties = cell.find("w:tcPr", NS)
                        cell_size = cell_properties.find("w:tcW", NS)
                        if cell_size is not None:
                            cell_size.set(f"{{{W}}}w", str(cell_width))
                        for run in cell.findall(".//w:r", NS):
                            run_properties = run.find("w:rPr", NS)
                            if run_properties is None:
                                run_properties = etree.Element(f"{{{W}}}rPr")
                                run.insert(0, run_properties)
                            for name in ("sz", "szCs"):
                                font_size = run_properties.find(f"w:{name}", NS)
                                if font_size is None:
                                    font_size = etree.SubElement(run_properties, f"{{{W}}}{name}")
                                font_size.set(f"{{{W}}}val", "18")
                if count:
                    marker = etree.SubElement(body.find("w:p", NS), f"{{{W}}}bookmarkStart")
                    marker.set(f"{{{W}}}id", "5400")
                    marker.set(f"{{{W}}}name", "H10TablasApaisadas")
                    end = etree.SubElement(marker.getparent(), f"{{{W}}}bookmarkEnd")
                    end.set(f"{{{W}}}id", "5400")
                content = etree.tostring(
                    tree, xml_declaration=True, encoding="UTF-8", standalone=True
                )
            target.writestr(info, content)
    path.write_bytes(buffer.getvalue())
    if verify_word_layout(path) != count:
        raise ValueError("censo de tablas apaisadas inconsistente")
    return count
