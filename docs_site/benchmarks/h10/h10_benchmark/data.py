"""Fuentes admitidas, índices originales y frontera exterior agrupada predeclarada."""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .contract import SEED, SOURCES, sha256


def verify_source(case: str, path: Path) -> None:
    """La admisión de datos no se hereda de la licencia del software."""
    if case not in SOURCES or SOURCES[case]["license"] != "CC BY 4.0":
        raise ValueError(f"permiso de redistribución no acreditado: {case}")
    if sha256(path) != SOURCES[case]["sha256"]:
        raise ValueError(f"huella de fuente distinta: {case}")


def obtain(case: str, cache: Path) -> Path:
    """Cache por hash; una copia corrupta o red caída es error, nunca PASS."""
    spec = SOURCES[case]
    path = cache / f"{spec['sha256']}.zip"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        url = f"https://archive.ics.uci.edu/static/public/{spec['id']}/{spec['slug']}.zip"
        with urllib.request.urlopen(url, timeout=40) as response:
            content = response.read()
        path.write_bytes(content)
    verify_source(case, path)
    return path


def load_case(case: str, cache: Path) -> tuple[pd.DataFrame, dict, pd.Series]:
    """Transformaciones declaradas; ninguna etiqueta, fila o fecha se inventa."""
    if case.startswith("consumo_"):
        from bayesrisk.ui.datasets import materialize

        frame = pd.read_parquet(materialize(case, workdir=cache / "synthetic"))
        kwargs = {
            "target": "bad_flag",
            "id": "loan_id",
            "cohort": "cohorte",
            "oot_cohorts": ["2024Q2"],
        }
        excluded = {"bad_flag", "loan_id", "cohorte"}
        features = [c for c in frame if c not in excluded]
        return frame, kwargs, exact_groups(frame[features])
    spec = SOURCES[case]
    with zipfile.ZipFile(obtain(case, cache)) as archive:
        content = archive.read(str(spec["member"]))
    if case == "german":
        frame = pd.read_csv(
            io.BytesIO(content),
            sep=r"\s+",
            header=None,
            names=[f"x{i}" for i in range(1, 21)] + ["target"],
        )
        if set(frame.target.unique()) != {1, 2}:
            raise ValueError("orientación German desconocida")
        frame["target"] = (frame.target == 2).astype("int64")
    else:
        frame = pd.read_excel(io.BytesIO(content), header=1, engine="xlrd")
        expected = [
            "ID",
            "LIMIT_BAL",
            "SEX",
            "EDUCATION",
            "MARRIAGE",
            "AGE",
            "PAY_0",
            *[f"PAY_{i}" for i in range(2, 7)],
            *[f"BILL_AMT{i}" for i in range(1, 7)],
            *[f"PAY_AMT{i}" for i in range(1, 7)],
            "default payment next month",
        ]
        if list(frame.columns) != expected or not frame.ID.is_unique:
            raise ValueError("esquema o ID Taiwan cambió")
        # El ID original permanece como procedencia, nunca como predictor/entidad inferida.
        source_ids = frame.pop("ID").tolist()
        frame = frame.rename(columns={"default payment next month": "target"})
        frame.attrs["source_ids"] = source_ids
        for column in ("SEX", "EDUCATION", "MARRIAGE"):
            frame[column] = frame[column].astype(str)
    if len(frame) != spec["rows"] or int(frame.target.sum()) != spec["events"]:
        raise ValueError("filas/eventos no concuerdan con fuente admitida")
    if set(frame.target.unique()) != {0, 1} or not frame.index.is_unique:
        raise ValueError("target o índice inválido")
    return (
        frame,
        {"target": "target", "partition": "random"},
        exact_groups(frame.drop(columns="target")),
    )


def exact_groups(features: pd.DataFrame, entities: pd.Series | None = None) -> pd.Series:
    """Componentes conexas por igualdad exacta de X o entidad acreditada; nunca por target."""
    if not features.index.is_unique or features.isna().any().any():
        raise ValueError("X debe tener índices únicos y faltantes explícitamente tratados")
    codes = pd.factorize(pd.MultiIndex.from_frame(features), sort=False)[0]
    parents = list(range(len(features)))

    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def connect(values) -> None:
        first = {}
        for i, value in enumerate(values):
            if value in first:
                parents[find(i)] = find(first[value])
            else:
                first[value] = i

    connect(codes)
    if entities is not None:
        if not entities.index.equals(features.index) or entities.isna().any():
            raise ValueError("entidades sin índice común o con ausentes")
        connect(entities.tolist())
    return pd.Series([find(i) for i in range(len(features))], index=features.index, name="group")


def outer_split(frame: pd.DataFrame, groups: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """25% de grupos, semilla fija; orden e índices de la fuente preservados."""
    if not groups.index.equals(frame.index):
        raise ValueError("índice de grupos desalineado")
    train, test = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED).split(frame, groups=groups)
    )
    return frame.iloc[np.sort(train)].copy(), frame.iloc[np.sort(test)].copy()


def verify_partition(
    universe: pd.Index, parts: dict[str, pd.Index], groups: pd.Series | None = None
) -> None:
    """Disjunción/exhaustividad/orden; en la frontera exterior, grupos completos."""
    if not universe.is_unique:
        raise ValueError("índices duplicados en universo")
    seen = set()
    seen_groups = set()
    for ids in parts.values():
        if not ids.is_unique or seen.intersection(ids):
            raise ValueError("solapamiento de IDs entre particiones")
        if not ids.equals(universe[universe.isin(ids)]):
            raise ValueError("orden o índice ajeno al universo")
        seen.update(ids)
        if groups is not None:
            current = set(groups.loc[ids])
            if seen_groups.intersection(current):
                raise ValueError("grupo partido entre input y evaluación")
            seen_groups.update(current)
    if seen != set(universe):
        raise ValueError("partición no exhaustiva")


def verify_classes(frame: pd.DataFrame, target: str, parts: dict[str, pd.Index]) -> None:
    """Puerta pre-fit fijada por H10; nunca buscar otra semilla."""
    for name, ids in parts.items():
        values = frame.loc[ids, target]
        if int(values.eq(1).sum()) < 30 or int(values.eq(0).sum()) < 1:
            raise ValueError(f"{name}: mínimo predeclarado de clases incumplido")
