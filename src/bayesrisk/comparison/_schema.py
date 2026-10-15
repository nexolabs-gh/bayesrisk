"""Forma anidada del comparable de esquema 1; valida sin transformar sus bytes ni su huella."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from bayesrisk.comparison.exceptions import ComparisonDataError


class _Objeto(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class _Muestra(_Objeto):
    sample: str
    n: int
    n_bad: int
    auc: float | None
    gini: float | None
    ks: float | None
    status: str


class _Receta(_Objeto):
    bins: int
    smoothing: float
    thresholds: list[float]


class _Puntajes(_Objeto):
    order: str
    basis: str
    rows_hash: str | None
    default_hash: str | None
    risk: list[float]
    default: list[int]

    @model_validator(mode="after")
    def _pares(self) -> Self:
        if len(self.risk) != len(self.default) or any(v not in (0, 1) for v in self.default):
            raise ValueError("riesgo y desenlace deben formar pares, con desenlace binario")
        return self


class _Psi(_Objeto):
    comparison: str
    psi: float | None
    band: str | None


class _Csi(_Objeto):
    comparison: str
    csi: float | None
    band: str | None


class _Tramos(_Objeto):
    k: int
    share_by_sample: dict[str, list[float]]


class _Variable(_Objeto):
    feature: str
    beta: float | None
    expected_sign: str | None
    sign_ok: bool | None
    iv_development: float | None
    iv_by_sample: dict[str, float | None]
    csi: list[_Csi]


class _Validacion(_Objeto):
    status: str
    reason: str | None


class _Comun(_Objeto):
    schema_version: int
    bayesrisk: str
    family: str
    name: str
    created_at: str | None
    config_hash: str | None
    data_hash: str | None
    portfolio_hash: str | None
    currency: str | None
    missing: dict[str, str]


class _Scorecard(_Comun):
    model_hash: str | None
    psi_recipe: _Receta | None
    samples: list[_Muestra]
    evaluation_sample: str
    evaluation_scores: _Puntajes | None
    score_psi: list[_Psi] | None
    score_psi_common: _Psi | None
    grades: _Tramos | None
    variables: list[_Variable] | None
    validation: _Validacion | None


class _Escenario(_Objeto):
    name: str
    weight: float | None


class _ColumnasDeMonto(_Objeto):
    exposure: str
    balance: str
    limit: str


class _Provision(_Objeto):
    n: int
    exposure: float
    ecl: float
    coverage: float | None


class _ProvisionPorEtapa(_Provision):
    stage: int


class _Ifrs9(_Comun):
    as_of: str
    scenarios: list[_Escenario]
    amount_columns: _ColumnasDeMonto | None
    by_stage: list[_ProvisionPorEtapa]
    total: _Provision

    @field_validator("by_stage")
    @classmethod
    def _tres_etapas(cls, filas: list[_ProvisionPorEtapa]) -> list[_ProvisionPorEtapa]:
        # El productor del esquema 1 siempre publica las tres, incluso con cero operaciones.
        if sorted(f.stage for f in filas) != [1, 2, 3]:
            raise ValueError("el desglose debe traer las etapas 1, 2 y 3 una vez cada una")
        return filas


def validar_forma(resumen: dict[str, Any], *, origen: str) -> None:
    """Comprueba campos y tipos; el lector devuelve el original, sin coerción ni defaults."""
    modelo = _Scorecard if resumen["family"] == "scorecard" else _Ifrs9
    try:
        modelo.model_validate(resumen)
    except ValidationError as exc:
        # La ruta ubica el defecto sin volcar puntajes, desenlaces ni el resto del archivo.
        error = exc.errors(include_input=False, include_url=False)[0]
        ruta = ".".join(str(p) for p in error["loc"])
        raise ComparisonDataError(
            f"{origen} no tiene la forma de un resumen comparable en {ruta}: "
            "revisa los campos y sus tipos."
        ) from exc
