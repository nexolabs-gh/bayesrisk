"""Config declarativo de la capa ``provisioning.ifrs9`` (SDD-16 §5).

:class:`IfrsProvisioningConfig` es la sección ``provisioning_ifrs9`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`: cálculo de la pérdida crediticia esperada contable
**IFRS 9 (ECL)** de tres etapas (PD 12m/lifetime + PIT/TTC Vasicek, LGD, EAD/CCF, staging/SICR y
motor ECL con descuento a EIR y multiescenario). Toda clase hereda de
:class:`~bayesrisk.core.config.BayesRiskBaseConfig` (``extra='forbid'`` y ``frozen=True``); cada
campo declara ``title``/``description`` y metadatos ``ui_*`` para que la UI (SDD-23) sea un editor
del mismo config. La sección es computacional (no infraestructura): cambiar la fuente de
term-structure, ``rho``, el enfoque LGD/EAD, los umbrales SICR, los pesos de escenario o la
convención de descuento **entra al ``config_hash`` global**.

Nomenclatura IFRS 9 (regla dura D-CONV-1): ``pd``/``lgd``/``ead``, nunca la nomenclatura CMF.

Frontera B16.1: aquí solo viven el schema y sus validaciones determinables sin datos. La *presencia*
de columnas de datos (p. ej. que exista una fuente CCF cuando ``ead.method='ccf'``) es un contrato
de runtime que valida el motor en bloques posteriores (§6/§8), de modo que el config por defecto
``IfrsProvisioningConfig()`` siga construyendo sin argumentos.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig, declara_esenciales
from bayesrisk.core.dataset_check import ContextoConfig, Requisito
from bayesrisk.provisioning.ifrs9.exceptions import IfrsConfigError
from bayesrisk.provisioning.lgd import (
    WORKOUT_COST_COLUMN,
    WORKOUT_EAD_COLUMN,
    WORKOUT_RATE_COLUMN,
    WORKOUT_TIME_COLUMN,
)

__all__ = [
    "IfrsEadConfig",
    "IfrsEclConfig",
    "IfrsLgdConfig",
    "IfrsPdConfig",
    "IfrsProvisioningConfig",
    "IfrsScenarioConfig",
    "IfrsStagingConfig",
]

#: Prefijo de la ruta de este dominio en ``BayesRiskConfig``, para anclar sus errores (D-EXI-5).
#:
#: ⚠️ En UN solo sitio y no repetido en cada ``raise``: la ruta que el error declara tiene que ser
#: **absoluta desde la raíz del config** —el ``except`` que la traduce vive en el endpoint y atrapa
#: la validación del ``BayesRiskConfig`` entero, así que ahí ya no se sabe qué sección la emitió—, y
#: eso ata al dominio con el nombre de su campo en la raíz. ⚠️ Ese nombre es ``provisioning_ifrs9``
#: y **no** se deduce del paquete (``ifrs9``): sale del registro de dominio.
_LOC_SECCION: tuple[str, ...] = ("provisioning_ifrs9",)

# Tolerancia absoluta para exigir que los pesos de escenario sumen 1 (SDD-16 §5).
_WEIGHT_SUM_TOL: float = 1e-9
# CASO-REAL-IFRS9 §3.2-7: el único método de survival que publica los incumplimientos por período,
# que la lectura desde la edad necesita para saber desde dónde extender la cola de la curva.
_METODO_POR_PERIODOS: str = "discrete_hazard"
# Nombres de escenario vetados por el guard anti escenario medio (espejo de SDD-20/forward:
# se ponderan outputs por escenario, nunca inputs macro promediados).
_RESERVED_SCENARIO_NAMES: frozenset[str] = frozenset({"mean", "average", "weighted_mean_input"})


def _require_non_empty_strings(values: dict[str, str], *, context: str) -> None:
    """Valida que los nombres de columnas/campos declarativos no sean vacíos.

    Sus errores van SIN ``loc`` (D-EXI-5), y no por olvido: el mensaje publica la **lista** de
    campos en blanco —seis de sus diez sitios de llamada le pasan más de un campo—, así que no hay
    un culpable único al que anclar. Y el ayudante recibe un ``context`` de prosa, no la ruta de
    quien lo llama, de modo que ni siquiera podría construirla sin cambiarle la firma.
    """
    empty = [name for name, value in values.items() if not value.strip()]
    if empty:
        raise IfrsConfigError(f"Los campos de {context} no pueden estar vacíos: {empty}.")


def _require_non_empty_if_set(values: dict[str, str | None], *, context: str) -> None:
    """Valida que las columnas opcionales, si se informan, no queden en blanco.

    Sin ``loc`` por la misma razón que su hermano de arriba: acusa una lista, no un campo.
    """
    empty = [name for name, value in values.items() if value is not None and not value.strip()]
    if empty:
        raise IfrsConfigError(
            f"Las columnas opcionales de {context} no pueden estar vacías: {empty}."
        )


class IfrsPdConfig(BayesRiskBaseConfig):
    """Configuración de la PD 12m/lifetime y su transformación PIT/TTC (Vasicek)."""

    term_structure_source: Literal["survival", "markov", "forward"] = Field(
        default="survival",
        title="Proveedor de term-structure lifetime",
        description=(
            "Origen de la term-structure de PD lifetime: survival es el estándar IFRS 9; markov "
            "y forward son alternativas."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "PD", "ui_order": 1},
    )
    base_pd_source: Literal["calibration", "term_structure"] = Field(
        default="term_structure",
        title="Fuente de PD 12m base",
        description=(
            "term_structure deriva la PD 12m de la misma curva lifetime; calibration la ancla a "
            "la PD calibrada transversal."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "PD", "ui_order": 2},
    )
    pit_mode: Literal["consume_pit", "apply_vasicek", "ttc_only"] = Field(
        default="consume_pit",
        title="Cómo obtener la PD PIT",
        description=(
            "consume_pit usa curvas PIT de forward; apply_vasicek transforma TTC con rho y Z; "
            "ttc_only usa la TTC sin ajuste (solo diagnóstico)."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "PD", "ui_order": 3},
    )
    rho: float | None = Field(
        default=None,
        ge=0.0,
        lt=1.0,
        title="Correlación de activos monofactorial",
        description=(
            "Correlación de activos (asset correlation) Vasicek; sin default "
            "(parámetro por cartera)."
        ),
        json_schema_extra={"ui_widget": "number_input", "ui_group": "PD", "ui_order": 4},
    )
    rho_col: str | None = Field(
        default=None,
        title="Columna de rho por fila (reservada)",
        # Sin backticks: el tooltip se pinta como texto plano y se veían literales en pantalla.
        description=("Reservada: la correlación por fila aún no está implementada."),
        json_schema_extra={
            "ui_help": (
                "Reservada: la correlación por fila aún no está implementada. El motor usa el "
                "escalar «rho» de PD por cartera y, si se informa esta columna, detiene la "
                "corrida con error en vez de aplicar el escalar en silencio."
            ),
            "ui_widget": "text_input",
            "ui_group": "PD",
            "ui_order": 5,
        },
    )
    # Se busca en la term-structure, no en el archivo del usuario.
    systemic_factor_col: str | None = Field(
        default=None,
        title="Columna del factor sistémico Z",
        description=(
            "Columna con el factor sistémico Z por escenario/período (orientación Z>0 = expansión)."
        ),
        json_schema_extra={
            "column_role": "derived",
            "ui_widget": "text_input",
            "ui_group": "PD",
            "ui_order": 6,
        },
    )
    horizon_12m_periods: int | None = Field(
        default=12,
        ge=1,
        title="Períodos que cubren 12 meses",
        description=(
            "Períodos de la term-structure que cubren 12 meses (mensual=12, trimestral=4, "
            "anual=1). En blanco, se infieren de la unidad de la curva."
        ),
        json_schema_extra={
            "ui_help": (
                "Cuántos períodos de la curva de PD forman los 12 meses del Stage 1. En blanco, el "
                "motor los infiere de la unidad de la curva —1 con años, 4 con trimestres, 12 con "
                "meses— con la misma regla que la puerta guiada, y lo deja en el registro de "
                "auditoría; si la curva no declara una unidad reconocida, la corrida se detiene y "
                "lo dice."
            ),
            "ui_null_label": "inferido de la unidad de la curva",
            "ui_widget": "number_input",
            "ui_group": "PD",
            "ui_order": 7,
        },
    )
    max_lifetime_periods: int | None = Field(
        default=None,
        ge=1,
        title="Tope de horizonte lifetime",
        description=(
            "Tope opcional del horizonte lifetime; en blanco usa todo el soporte de la curva."
        ),
        json_schema_extra={"ui_widget": "number_input", "ui_group": "PD", "ui_order": 8},
    )

    @model_validator(mode="after")
    def _check_pd(self) -> Self:
        """Valida las columnas opcionales de PD y rechaza fail-fast ``rho_col`` (diferida en v1).

        Guard fail-fast (mismo criterio que ``exposure_profile_col``): el motor v1 sólo consume
        ``pd.rho`` escalar; aceptar ``rho_col`` y calcular con el escalar sería una degradación
        silenciosa con etiqueta falsa. Se rechaza aquí, no se degrada en silencio. El campo se
        conserva por compatibilidad de schema/UI; su consumo real queda diferido (P0 roadmap).
        """
        _require_non_empty_if_set(
            {"rho_col": self.rho_col, "systemic_factor_col": self.systemic_factor_col},
            context="pd",
        )
        if self.rho_col is not None:
            raise IfrsConfigError(
                "pd.rho_col (correlación heterogénea por fila) no está consumida por el "
                "motor v1 y queda diferida: use pd.rho escalar por cartera. Honrar rho_col "
                "en silencio con el escalar sería una degradación con etiqueta falsa.",
                # D-EXI-5: el error se ANCLA a su campo, para que el formulario pueda llevar ahí al
                # usuario en vez de dejarle un mensaje sin control. La ruta va absoluta desde la
                # raíz del config, y un gate exige que resuelva contra `BayesRiskConfig`.
                loc=(*_LOC_SECCION, "pd", "rho_col"),
            )
        return self


class IfrsLgdConfig(BayesRiskBaseConfig):
    """Configuración de la LGD por los enfoques provided/beta/fractional/workout."""

    method: Literal["provided", "beta_regression", "fractional_response", "workout"] = Field(
        default="provided",
        title="Enfoque LGD",
        description=(
            "provided consume la LGD de la institución; beta/fractional/workout la modelan "
            "(nunca OLS plano, por bimodalidad)."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "LGD", "ui_order": 1},
    )
    lgd_col: str = Field(
        default="lgd",
        title="Columna LGD (provided)",
        description="Columna con la LGD entregada por la institución cuando method='provided'.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "LGD",
            "ui_order": 2,
            "ui_essential": True,
        },
    )
    recovery_col: str | None = Field(
        default=None,
        title="Columna recovery",
        description=(
            "Columna de recuperación para la identidad LGD=1-recovery y el enfoque workout."
        ),
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "LGD",
            "ui_order": 3,
        },
    )
    lgd_floor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        title="Piso LGD",
        description="Piso al que se acota la LGD estimada, dentro de [0, 1].",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "LGD", "ui_order": 4},
    )
    lgd_cap: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        title="Techo LGD",
        description="Techo al que se acota la LGD estimada, dentro de [0, 1].",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "LGD", "ui_order": 5},
    )
    covariate_cols: tuple[str, ...] = Field(
        default=(),
        title="Covariables para beta/fractional",
        description="Covariables del modelo LGD beta_regression/fractional_response.",
        json_schema_extra={
            "column_role": "input",
            # Pasa a `multiselect` con el rol: son columnas CRUDAS del archivo del usuario —no
            # variables WoE, pese a llamarse igual que las de survival—, así que ahora que el
            # front sabe de dónde sacar las opciones, ofrecerlas es mejor que pedirlas a ciegas.
            # Lo exige además el gate de `form-engine`: una lista `input` que se pinta como texto
            # obliga a escribir a mano lo que el front tiene delante.
            "ui_widget": "multiselect",
            "ui_group": "LGD",
            "ui_order": 6,
        },
    )
    workout_discount: Literal["eir", "contractual"] = Field(
        default="eir",
        title="Descuento de recuperos workout",
        description=(
            "Tasa para descontar los flujos de recupero del enfoque workout (EIR o contractual)."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "LGD", "ui_order": 7},
    )

    # ── Columnas del enfoque workout: PROPIEDADES, no campos (D-LGD-3) ──────────────────────────
    #
    # El motor dejó de leerlas por nombre fijo y ahora se las pide a su config, para que el método
    # interno —cuya exposición es configurable— pueda declarar las suyas. IFRS 9 conserva los
    # nombres convencionales de siempre, así que **su comportamiento no cambia en un solo caso**.
    #
    # 🔴 Van como `@property` y NO como campos a propósito: un campo entraría al `model_dump`, y con
    # él al `config_hash` — medido, cuatro campos nuevos aquí moverían la identidad del preset F4
    # (`013e69dc`), que está impresa dentro de la demo publicada. Una propiedad no serializa.
    #
    # ⚠️ Límite declarado y medido: `_declaraciones` (`core/dataset_check.py:576-587`) recorre
    # `model_fields`, y una propiedad no es un campo. O sea que estas cuatro columnas **siguen sin
    # cobertura de preflight en IFRS 9, exactamente igual que hoy**: la mejora vale sólo para la
    # rama del método interno, que sí las declara como campos con su `column_role`. Cerrarlo aquí
    # también exigiría convertirlas en campos, y eso movería `013e69dc`: queda fuera de alcance.

    @property
    def workout_ead_col(self) -> str:
        """Columna de exposición del enfoque workout (convención fija en IFRS 9)."""
        return WORKOUT_EAD_COLUMN

    @property
    def workout_cost_col(self) -> str:
        """Columna de costos de recuperación del enfoque workout (convención fija en IFRS 9)."""
        return WORKOUT_COST_COLUMN

    @property
    def workout_time_col(self) -> str:
        """Columna de tiempo de recupero en años del enfoque workout (convención fija)."""
        return WORKOUT_TIME_COLUMN

    @property
    def workout_rate_col(self) -> str:
        """Columna de tasa contractual del enfoque workout (convención fija en IFRS 9)."""
        return WORKOUT_RATE_COLUMN

    @model_validator(mode="after")
    def _check_lgd(self) -> Self:
        """Valida columnas, floor/cap y requisitos por enfoque LGD de SDD-16 §5."""
        _require_non_empty_strings({"lgd_col": self.lgd_col}, context="lgd")
        _require_non_empty_if_set({"recovery_col": self.recovery_col}, context="lgd")
        vacias = [idx for idx, col in enumerate(self.covariate_cols) if not col.strip()]
        if vacias:
            raise IfrsConfigError(
                f"lgd.covariate_cols no puede contener nombres vacíos: {vacias}.",
                loc=(*_LOC_SECCION, "lgd", "covariate_cols"),  # D-EXI-5
            )
        # Sin `loc` a propósito: el piso y el techo son DOS campos y el error nace de su relación,
        # así que no hay culpable único —se arregla bajando uno o subiendo el otro— y anclar en uno
        # mandaría al usuario al que no era.
        if self.lgd_floor > self.lgd_cap:
            raise IfrsConfigError("lgd.lgd_floor no puede exceder lgd.lgd_cap.")
        if self.method in ("beta_regression", "fractional_response") and not self.covariate_cols:
            raise IfrsConfigError(
                "lgd.method beta_regression/fractional_response exige covariate_cols no vacías.",
                # «X exige Y» ancla en Y: lo que falta y hay que escribir, no la elección que lo
                # exige. Mismo criterio que el precedente de `provisioning_internal`.
                loc=(*_LOC_SECCION, "lgd", "covariate_cols"),
            )
        if self.method == "workout" and self.recovery_col is None:
            raise IfrsConfigError(
                "lgd.method='workout' exige recovery_col para la identidad LGD=1-recovery.",
                loc=(*_LOC_SECCION, "lgd", "recovery_col"),
            )
        return self

    def columnas_inactivas(self) -> frozenset[str]:
        """Columnas que este enfoque de LGD no abre (D-RAM-1).

        Sólo la regresión lee covariables: ``_estimate_regression`` es la rama ``else`` del
        dispatch (`provisioning/lgd.py:195-201`), así que con el default ``provided`` —y con
        ``workout``— la lista está ahí pero el motor nunca la mira. ``recovery_col`` NO entra: las
        tres ramas la leen si viene.
        """
        inactivas = set()
        if self.method not in ("beta_regression", "fractional_response"):
            inactivas.add("covariate_cols")
        if self.recovery_col is not None:
            # 🔴 La condición de `lgd_col` NO es el `method`: dos de las tres ramas
            # (`_estimate_provided` en `provisioning/lgd.py:203-210` y `_regression_target` en
            # `:269-274`) lo
            # leen **sólo si `recovery_col is None`**, y la tercera (`workout`) no lo toca nunca —
            # y su validador ya exige `recovery_col`, así que `recovery_col is None` implica
            # `method != "workout"` y la condición se cierra en un solo predicado sobre un hermano.
            inactivas.add("lgd_col")
        return frozenset(inactivas)


class IfrsEadConfig(BayesRiskBaseConfig):
    """Configuración de la EAD/CCF y el perfil de exposición por período."""

    method: Literal["provided", "ccf"] = Field(
        default="ccf",
        title="Enfoque EAD",
        description="provided consume la EAD entregada; ccf calcula EAD=drawn+CCF·(límite-drawn).",
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "EAD", "ui_order": 1},
    )
    ead_col: str = Field(
        default="ead",
        title="Columna EAD (provided)",
        description="Columna con la EAD entregada por la institución cuando method='provided'.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 2,
            "ui_essential": True,
        },
    )
    drawn_col: str = Field(
        default="drawn",
        title="Saldo dispuesto",
        description="Columna con el saldo dispuesto (drawn) para el enfoque CCF.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 3,
        },
    )
    limit_col: str = Field(
        default="credit_limit",
        title="Límite de crédito",
        description="Columna con el límite de crédito para el enfoque CCF.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 4,
        },
    )
    ccf_col: str | None = Field(
        default=None,
        title="Columna CCF por fila",
        description="Columna con el factor de conversión (CCF) por fila; excluyente con ccf_value.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 5,
        },
    )
    ccf_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        title="CCF único de config",
        description="Factor de conversión (CCF) único de config en [0, 1]; excluyente con ccf_col.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "EAD", "ui_order": 6},
    )
    exposure_profile_col: str | None = Field(
        default=None,
        title="Perfil EAD(t) longitudinal (reservado)",
        description=(
            "Reservada: el perfil de exposición EAD(t) por período aún no está implementado."
        ),
        json_schema_extra={
            "ui_help": (
                "Reservada: el perfil de exposición EAD(t) por período aún no está "
                "implementado. Informar esta columna detiene la corrida con error, porque una "
                "columna escalar no puede representar la EAD período a período."
            ),
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 7,
        },
    )
    installment_col: str | None = Field(
        default=None,
        title="Cuota del contrato",
        description=(
            "Columna con la cuota mensual del contrato; con ella la exposición sigue la tabla de "
            "pagos hasta el vencimiento."
        ),
        json_schema_extra={
            "ui_help": (
                "Opcional; exige la fecha de vencimiento y la EAD entregada. La exposición de "
                "cada período es el saldo al inicio del período en la tabla de cuota fija que "
                "paga el saldo de hoy justo al vencimiento, con la tasa implícita en la cuota (no "
                "la tasa efectiva). Si la cuota no alcanza a pagar el saldo en el plazo, la "
                "exposición queda constante hasta el vencimiento y se cuenta en «Qué revisar». "
                "Una fila sin cuota conserva la exposición constante."
            ),
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "EAD",
            "ui_order": 8,
            "ui_essential": True,
            "ui_essential_group": "Si tienes las fechas y la cuota del contrato",
        },
    )

    @model_validator(mode="after")
    def _check_ead(self) -> Self:
        """Valida columnas, la exclusividad ccf_col/ccf_value y el guard EAD(t) de SDD-16 §5.

        La *presencia* de una fuente CCF cuando ``method='ccf'`` es un contrato de runtime (§6/§8);
        aquí solo se prohíbe informar **ambas** fuentes a la vez, para que el config por defecto
        siga construyendo sin argumentos.

        Guard CT-3 (fail-fast): informar ``exposure_profile_col`` levanta en construcción. El perfil
        EAD(t) longitudinal real (panel fila x período) está diferido a CT-3; una columna escalar no
        puede representarlo, y honrarla aplanándola a constante sin aviso sería una degradación
        silenciosa con etiqueta falsa. Se rechaza aquí, no se degrada en silencio.
        """
        _require_non_empty_strings(
            {"ead_col": self.ead_col, "drawn_col": self.drawn_col, "limit_col": self.limit_col},
            context="ead",
        )
        if self.exposure_profile_col is not None:
            raise IfrsConfigError(
                "exposure_profile_col (perfil EAD(t) longitudinal por período) está "
                "diferido a CT-3 y no se soporta en v1: una columna escalar no "
                "representa EAD(t) por período. Use method='provided'/'ccf' (EAD "
                "desplegada constante con aviso FALTA-DATO-IFRS-4) o espere CT-3.",
                loc=(*_LOC_SECCION, "ead", "exposure_profile_col"),  # D-EXI-5
            )
        _require_non_empty_if_set(
            {"ccf_col": self.ccf_col, "installment_col": self.installment_col}, context="ead"
        )
        # Sin `loc`: informar las DOS fuentes de CCF es una incompatibilidad entre campos, y se
        # arregla borrando cualquiera de las dos. No hay un campo que sea *el* equivocado.
        if self.method == "ccf" and self.ccf_col is not None and self.ccf_value is not None:
            raise IfrsConfigError("ead.method='ccf' admite ccf_col o ccf_value, no ambos a la vez.")
        return self

    def columnas_inactivas(self) -> frozenset[str]:
        """La columna de CCF sólo la abre el enfoque que estima la EAD desde el CCF (D-RAM-1).

        Es el caso con que se reprodujo el falso positivo: ``method='provided'`` toma la EAD tal
        cual y `_estimate_ccf` —el único lector de ``ccf_col``— ni se llama (`ead.py:131-135`).
        ⚠️ Y el validador de arriba no lo impide: sólo veta ``ccf_col`` **y** ``ccf_value`` juntos, y
        únicamente bajo ``method='ccf'``, así que el estado es perfectamente alcanzable.
        """
        inactivas = set()
        if self.method != "ccf":
            # `_estimate_ccf` es la rama `else` del dispatch: con `provided` ni se llama.
            inactivas |= {"ccf_col", "drawn_col", "limit_col"}
        if self.method != "provided":
            # Y el simétrico: `ead_col` sólo lo lee la rama `provided` (`ead.py:133`), mientras su
            # default es `"ead"` y el de `method` es `ccf`. Es el peor de los catorce, y el motivo
            # de que no se pudiera declarar el rol hasta que existió este mecanismo: con el config
            # de fábrica habría exigido una columna que el motor nunca abre.
            # La cuota (CASO-REAL-IFRS9 D-CRE-3) tampoco: la tabla parte de un saldo entregado, y
            # con CCF el requisito de la sección raíz lo avisa antes de correr.
            inactivas |= {"ead_col", "installment_col"}
        return frozenset(inactivas)


class IfrsStagingConfig(BayesRiskBaseConfig):
    """Configuración del staging IFRS 9 (SICR, backstops 30/90 dpd, exención de bajo riesgo)."""

    sicr_pd_ratio_threshold: float = Field(
        default=2.0,
        gt=1.0,
        title="Ratio PD lifetime actual/origen",
        description=("Umbral del ratio PD lifetime actual/origen que dispara el paso a Stage 2."),
        json_schema_extra={
            "ui_help": (
                "Umbral del ratio PD lifetime actual/origen que dispara el paso a Stage 2. "
                "El default 2,0 es el disparador de referencia; el motor admite cualquier "
                "valor mayor que 1, y moverlo cambia la población clasificada en Stage 2."
            ),
            "ui_widget": "number_input",
            "ui_group": "Staging",
            "ui_order": 1,
        },
    )
    sicr_pd_pit_backstop_multiple: float = Field(
        default=3.0,
        gt=1.0,
        title="Backstop PIT",
        description=(
            "Múltiplo del backstop PIT que dispara el paso a Stage 2. El default 3,0 es el "
            "múltiplo de referencia; el motor admite cualquier valor mayor que 1."
        ),
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Staging", "ui_order": 2},
    )
    dpd_sicr_backstop: int = Field(
        default=30,
        ge=0,
        title="Backstop dpd Stage 2",
        description=(
            "Días de mora que activan el backstop a Stage 2 (presunción rebatible IFRS 9 5.5.11)."
        ),
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Staging", "ui_order": 3},
    )
    dpd_default_backstop: int = Field(
        default=90,
        ge=0,
        title="Backstop dpd Stage 3",
        description=("Días de mora que presumen default a Stage 3 (presunción IFRS 9 B5.5.37)."),
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Staging", "ui_order": 4},
    )
    days_past_due_col: str = Field(
        default="days_past_due",
        title="Días de mora",
        description="Columna con los días de mora usados por los backstops 30/90 dpd.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 5,
            "ui_essential": True,
        },
    )
    is_default_col: str | None = Field(
        default="is_default",
        title="Columna que marca el incumplimiento",
        description="Columna booleana de default que fuerza Stage 3 con independencia de la mora.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 6,
            "ui_essential": True,
        },
    )
    origination_pd_life_col: str | None = Field(
        default=None,
        title="PD lifetime en origen",
        description="Columna con la PD lifetime en origen para el gatillo cuantitativo de SICR.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 7,
        },
    )
    rating_col: str | None = Field(
        default=None,
        title="Rating actual",
        description="Columna con el rating actual para el gatillo de downgrade por notches.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 8,
        },
    )
    origination_rating_col: str | None = Field(
        default=None,
        title="Rating en origen",
        description="Columna con el rating en origen para el gatillo de downgrade por notches.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 9,
        },
    )
    notch_downgrade_threshold: int | None = Field(
        default=None,
        ge=1,
        title="Downgrade por notches",
        description="Caída mínima de rating (en notches) respecto a origen que dispara Stage 2.",
        json_schema_extra={"ui_widget": "number_input", "ui_group": "Staging", "ui_order": 10},
    )
    stage_override_col: str | None = Field(
        default=None,
        title="Override cualitativo de stage",
        description=(
            "Columna con override cualitativo (watchlist, forbearance) que fuerza Stage 2/3."
        ),
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 11,
        },
    )
    low_credit_risk_exemption: bool = Field(
        default=False,
        title="Aplicar exención de bajo riesgo crediticio",
        description=(
            "Activa la exención IFRS 9 5.5.10. Por política conservadora del motor, las "
            "presunciones rebatibles de 30/90 días de mora prevalecen sobre la exención."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Staging", "ui_order": 12},
    )
    low_credit_risk_col: str | None = Field(
        default=None,
        title="Columna de bajo riesgo crediticio",
        description="Columna con el flag de bajo riesgo crediticio para la exención de Stage 1.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Staging",
            "ui_order": 13,
        },
    )

    @model_validator(mode="after")
    def _check_staging(self) -> Self:
        """Valida backstops dpd y columnas de rating del gatillo de notches de SDD-16 §5."""
        _require_non_empty_strings({"days_past_due_col": self.days_past_due_col}, context="staging")
        _require_non_empty_if_set(
            {
                "is_default_col": self.is_default_col,
                "origination_pd_life_col": self.origination_pd_life_col,
                "rating_col": self.rating_col,
                "origination_rating_col": self.origination_rating_col,
                "stage_override_col": self.stage_override_col,
                "low_credit_risk_col": self.low_credit_risk_col,
            },
            context="staging",
        )
        # Sin `loc`: es el orden entre DOS umbrales, y se arregla subiendo uno o bajando el otro.
        if self.dpd_default_backstop < self.dpd_sicr_backstop:
            raise IfrsConfigError(
                "staging.dpd_default_backstop debe ser >= staging.dpd_sicr_backstop."
            )
        # Sin `loc` aunque sea un «X exige Y», y ésta es la excepción que conviene tener escrita:
        # aquí las **Y son dos** y la condición es un `or`, así que cuál falta depende del estado y
        # el `raise` no lo distingue. Anclar fijo en una acertaría la mitad de las veces, y el `loc`
        # tiene que ser una tupla de literales para que el gate pueda resolverlo estáticamente —o
        # sea que tampoco cabe calcularlo aquí—. Vacío significa «no pertenece a un solo campo».
        if self.notch_downgrade_threshold is not None and (
            self.rating_col is None or self.origination_rating_col is None
        ):
            raise IfrsConfigError(
                "staging.notch_downgrade_threshold exige rating_col y origination_rating_col."
            )
        return self

    def columnas_inactivas(self) -> frozenset[str]:
        """Columnas de staging que el SICR no consulta con esta política (D-RAM-1).

        Dos gatillos opcionales, y los dos se apagan por un campo hermano:

        - Los ratings sólo los lee ``_fired_notch``, que **devuelve ceros sin mirarlos** cuando no
          hay umbral de bajada de escalones (`staging.py:189-190`). El validador de arriba cierra la
          implicación en un solo sentido —umbral ⇒ ratings—, así que declarar los ratings *sin*
          umbral construye sin problema y no se lee nada.
        - ``low_credit_risk_col`` sólo entra si la exención de bajo riesgo está encendida
          (`staging.py:221-228`), y su default es ``False``.
        """
        inactivas = set()
        if self.notch_downgrade_threshold is None:
            inactivas.update({"rating_col", "origination_rating_col"})
        if not self.low_credit_risk_exemption:
            inactivas.add("low_credit_risk_col")
        return frozenset(inactivas)


class IfrsScenarioConfig(BayesRiskBaseConfig):
    """Configuración de la fuente y los pesos de los escenarios macro."""

    source: Literal["forward", "config", "single"] = Field(
        default="forward",
        title="Fuente de escenarios/pesos",
        description=(
            "forward toma escenarios y pesos de la sección forward; config los fija aquí; "
            "single usa w=1."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "Escenarios", "ui_order": 1},
    )
    weights: dict[str, float] = Field(
        default_factory=dict,
        title="Pesos por escenario (source='config')",
        description=(
            "Pesos por escenario cuando source='config'; deben sumar 1 y ser todos positivos."
        ),
        json_schema_extra={"ui_widget": "kv_number", "ui_group": "Escenarios", "ui_order": 2},
    )
    forbid_mean_scenario: bool = Field(
        default=True,
        title="Prohibir promediar inputs macro",
        description=(
            "Guard anti escenario medio: se ponderan outputs por escenario, nunca inputs macro."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "Escenarios", "ui_order": 3},
    )

    @model_validator(mode="after")
    def _check_scenarios(self) -> Self:
        """Valida los pesos de escenario para ``source='config'`` de SDD-16 §5."""
        if self.source != "config":
            return self
        if not self.weights:
            raise IfrsConfigError(
                "scenarios.source='config' exige weights no vacíos.",
                loc=(*_LOC_SECCION, "scenarios", "weights"),  # D-EXI-5: «X exige Y» ancla en Y
            )
        vacias = [name for name in self.weights if not name.strip()]
        if vacias:
            raise IfrsConfigError(
                f"scenarios.weights no puede tener nombres de escenario vacíos: {vacias}.",
                loc=(*_LOC_SECCION, "scenarios", "weights"),
            )
        if self.forbid_mean_scenario:
            reservados = sorted(
                name for name in self.weights if name.lower() in _RESERVED_SCENARIO_NAMES
            )
            if reservados:
                raise IfrsConfigError(
                    "scenarios.forbid_mean_scenario=True veta escenarios medios reservados "
                    f"en weights: {reservados} (se ponderan outputs por escenario, nunca "
                    "inputs macro promediados).",
                    # El mensaje nombra dos campos y el ancla va en `weights`: apagar el guard es
                    # renunciar a la regla de método que lo justifica, no corregir el config. Lo
                    # que hay que arreglar es el escenario reservado que está en la lista.
                    loc=(*_LOC_SECCION, "scenarios", "weights"),
                )
        no_finitos = [name for name, value in self.weights.items() if not math.isfinite(value)]
        if no_finitos:
            raise IfrsConfigError(
                f"scenarios.weights debe contener pesos finitos: {no_finitos}.",
                loc=(*_LOC_SECCION, "scenarios", "weights"),
            )
        no_positivos = [name for name, value in self.weights.items() if value <= 0.0]
        if no_positivos:
            raise IfrsConfigError(
                f"scenarios.weights exige pesos estrictamente positivos: {no_positivos}.",
                loc=(*_LOC_SECCION, "scenarios", "weights"),
            )
        total = math.fsum(self.weights.values())
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_WEIGHT_SUM_TOL):
            # SÍ lleva ancla, y no es la «suma de fracciones» que se deja sin `loc`: los pesos no
            # son campos hermanos que haya que conciliar entre sí, son el contenido de UN campo.
            raise IfrsConfigError(
                f"scenarios.weights debe sumar 1; suma observada={total!r}.",
                loc=(*_LOC_SECCION, "scenarios", "weights"),
            )
        return self


class IfrsEclConfig(BayesRiskBaseConfig):
    """Configuración del motor ECL marginal (descuento a EIR, redondeo)."""

    eir_col: str = Field(
        default="eir",
        title="Tasa efectiva por instrumento",
        description=(
            "Columna con la tasa efectiva (EIR) por instrumento para el descuento de la ECL."
        ),
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "ECL",
            "ui_order": 1,
            "ui_essential": True,
        },
    )
    discount_convention: Literal["annual_eir_year_fraction", "period_eir"] = Field(
        default="annual_eir_year_fraction",
        title="Convención de descuento",
        description=(
            "annual_eir_year_fraction descuenta EIR anual por fracción de año; period_eir usa EIR "
            "por período."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "ECL", "ui_order": 2},
    )
    # CASO-REAL-IFRS9 D-CRE-1 (Cami, 2026-10-05, §8-2 (b)): activado de fábrica. Una operación en
    # Stage 3 ya incumplió (IFRS 9, Apéndice A; 5.5.3): su pérdida no depende de la probabilidad de
    # incumplir sino de cuánto se pierde (B5.5.33). Con la PD de la curva se provisionaba como una
    # sana: en la cartera del paquete, el 39 % de su LGD × EAD; medido +39,8 % y +98,0 % de ECL.
    stage3_direct: bool = Field(
        default=True,
        title="Stage 3 como EAD·LGD directo",
        description=(
            "Activado, Stage 3 provisiona la pérdida del incumplimiento ya ocurrido, EAD·LGD "
            "(PD = 1), en vez de la ECL lifetime con la PD de la curva."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "ECL", "ui_order": 3},
    )
    rounding: Literal["none", "currency_2dp", "integer_currency"] = Field(
        default="none",
        title="Redondeo de ECL",
        description=(
            "Política explícita de redondeo contable de la ECL; none publica el valor económico "
            "exacto."
        ),
        json_schema_extra={"ui_widget": "selectbox", "ui_group": "ECL", "ui_order": 4},
    )

    @model_validator(mode="after")
    def _check_ecl(self) -> Self:
        """Valida que la columna de EIR del motor ECL no esté vacía."""
        _require_non_empty_strings({"eir_col": self.eir_col}, context="ecl")
        return self


class IfrsProvisioningConfig(BayesRiskBaseConfig):
    """Calcula las provisiones contables IFRS 9: staging y pérdida esperada (ECL).

    Motor experimental: fuera de la garantía SemVer 2.x.
    """

    # Diez esenciales (FLUJO-GUIADO-IFRS9 D-ECL-6, §8-4: la única excepción al tope de 6; ampliada
    # de 7 a 10 por CASO-REAL-IFRS9 D-CRE-8, §8-3): las columnas de la entrada mínima —fecha de
    # corte, cartera, EAD, LGD, tasa, mora y la marca de incumplimiento— y, opcionales, las tres del
    # contrato —otorgamiento, vencimiento y cuota—, que son dato institucional y no perillas; el
    # resto, en «Avanzado».
    model_config = ConfigDict(json_schema_extra=declara_esenciales)

    schema_version: str = Field(
        default="1.0.0",
        title="Versión del sub-schema provisioning_ifrs9",
        description="Versión local del schema de provisiones IFRS 9 para migraciones futuras.",
        json_schema_extra={"ui_widget": "hidden", "ui_group": "General", "ui_order": 0},
    )
    type: Literal["standard"] = Field(
        default="standard",
        title="Tipo de sección provisioning_ifrs9",
        description="Variante de la sección de provisiones IFRS 9; hoy solo existe la estándar.",
        json_schema_extra={"ui_widget": "hidden", "ui_group": "General", "ui_order": 1},
    )
    as_of_date_col: str = Field(
        default="as_of_date",
        title="Fecha de cálculo",
        description="Columna con la fecha de cálculo o cierre contable de la provisión.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 1,
            "ui_essential": True,
        },
    )
    row_id_col: str | None = Field(
        default=None,
        title="Identificador de operación",
        description="Columna con el identificador de operación para trazar staging/ECL por fila.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 2,
        },
    )
    portfolio_col: str = Field(
        default="portfolio",
        title="Cartera",
        description="Columna con la cartera para agregar y parametrizar umbrales SICR por cartera.",
        json_schema_extra={
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 3,
            "ui_essential": True,
        },
    )
    portfolio_scheme: str | None = Field(
        default=None,
        title="Esquema de carteras",
        description=("Identificador de la taxonomía de carteras que usa la columna anterior."),
        json_schema_extra={
            "ui_help": (
                "Identificador de la taxonomía de carteras que usa la columna anterior. "
                "Declararlo permite comparar contra otro motor sin mapeo cuando ambos usan la "
                "misma taxonomía; si se omite, la comparación exige un mapeo explícito entre "
                "taxonomías."
            ),
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 22,
        },
    )
    # CASO-REAL-IFRS9 D-CRE-2 (§3.2): las fechas del contrato, opcionales y por fila. Con alguna de
    # las dos, la curva de PD se lee desde la edad de cada operación y se corta en su vencimiento.
    origination_date_col: str | None = Field(
        default=None,
        title="Fecha de otorgamiento",
        description=(
            "Columna con la fecha en que se otorgó cada operación; con ella la curva de PD se lee "
            "desde la antigüedad de la operación."
        ),
        json_schema_extra={
            "ui_help": (
                "Opcional. Con esta fecha, la curva de PD se lee desde la antigüedad de cada "
                "operación —los meses desde el otorgamiento, sin redondear— y no desde su primer "
                "período. Supone que la duración de la historia de la curva cuenta desde el "
                "otorgamiento. Una fila sin fecha se lee desde el primer período. Exige la curva "
                "de supervivencia por períodos discretos."
            ),
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 4,
            "ui_essential": True,
            "ui_essential_group": "Si tienes las fechas y la cuota del contrato",
        },
    )
    maturity_date_col: str | None = Field(
        default=None,
        title="Fecha de vencimiento",
        description=(
            "Columna con la fecha de vencimiento contractual; con ella la vida de cada operación "
            "termina en su vencimiento."
        ),
        json_schema_extra={
            "ui_help": (
                "Opcional. La vida de cada operación termina en su vencimiento contractual y el "
                "Stage 1 suma 12 meses o la vida, si es menor. Una operación ya vencida con saldo "
                "se provisiona con un período. Una fila sin fecha vive el horizonte de la curva. "
                "Más allá del último período de la curva con incumplimientos observados, el riesgo "
                "de cada operación se extiende con la media de sus tres últimos períodos con "
                "incumplimientos."
            ),
            "column_role": "input",
            "ui_widget": "text_input",
            "ui_group": "Columnas",
            "ui_order": 5,
            "ui_essential": True,
            "ui_essential_group": "Si tienes las fechas y la cuota del contrato",
        },
    )
    pd: IfrsPdConfig = Field(
        default_factory=IfrsPdConfig,
        title="PD 12m/lifetime + PIT",
        description="Configuración de PD 12m/lifetime y transformación PIT/TTC Vasicek.",
        json_schema_extra={"ui_widget": "section", "ui_group": "PD", "ui_order": 1},
    )
    lgd: IfrsLgdConfig = Field(
        default_factory=IfrsLgdConfig,
        title="LGD",
        description="Configuración de la LGD por los enfoques provided/beta/fractional/workout.",
        json_schema_extra={"ui_widget": "section", "ui_group": "LGD", "ui_order": 1},
    )
    ead: IfrsEadConfig = Field(
        default_factory=IfrsEadConfig,
        title="EAD/CCF",
        description="Configuración de la EAD/CCF y el perfil de exposición por período.",
        json_schema_extra={"ui_widget": "section", "ui_group": "EAD", "ui_order": 1},
    )
    staging: IfrsStagingConfig = Field(
        default_factory=IfrsStagingConfig,
        title="Staging/SICR",
        description="Configuración del staging IFRS 9 (SICR, backstops, exención de bajo riesgo).",
        json_schema_extra={"ui_widget": "section", "ui_group": "Staging", "ui_order": 1},
    )
    scenarios: IfrsScenarioConfig = Field(
        default_factory=IfrsScenarioConfig,
        title="Escenarios",
        description="Configuración de la fuente y los pesos de los escenarios macro.",
        json_schema_extra={"ui_widget": "section", "ui_group": "Escenarios", "ui_order": 1},
    )
    ecl: IfrsEclConfig = Field(
        default_factory=IfrsEclConfig,
        title="Motor ECL",
        description="Configuración del motor ECL marginal (descuento a EIR, redondeo).",
        json_schema_extra={"ui_widget": "section", "ui_group": "ECL", "ui_order": 1},
    )
    fail_on_falta_dato: bool = Field(
        default=True,
        title="Fallar ante falta de dato",
        description=(
            "Activado —que es como viene—, un aviso declarado que el motor emita durante el "
            "cálculo detiene "
            "la corrida en vez de quedar registrado y seguir. No cubre las limitaciones que esta "
            "capa arrastra en toda corrida, como el perfil de exposición constante por período: "
            "ésas quedan siempre anotadas en el resultado, porque no dependen de los datos que "
            "usted entregue."
        ),
        json_schema_extra={"ui_widget": "checkbox", "ui_group": "General", "ui_order": 2},
    )

    @model_validator(mode="after")
    def _check_ifrs_provisioning(self) -> Self:
        """Valida columnas raíz y la consistencia PIT (Vasicek ↔ rho/Z) de SDD-16 §5."""
        _require_non_empty_strings(
            {"as_of_date_col": self.as_of_date_col, "portfolio_col": self.portfolio_col},
            context="provisioning_ifrs9",
        )
        _require_non_empty_if_set(
            {
                "row_id_col": self.row_id_col,
                "origination_date_col": self.origination_date_col,
                "maturity_date_col": self.maturity_date_col,
            },
            context="provisioning_ifrs9",
        )
        # D-CRP6-3: el chequeo PIT es incondicional y no mira `fail_on_falta_dato`. Antes lo hacía,
        # pero `False` no abría ninguna ruta degradada —`_apply_vasicek` levanta igual—: su único
        # efecto era mover esta validación al medio del cálculo, que es lo que CRP-5 prohíbe. El
        # patrón es el de `cmf/engine.py:443`, que valida el dominio de cartera en la entrada.
        if self.pd.pit_mode == "apply_vasicek":
            if self.pd.rho is None:
                raise IfrsConfigError(
                    "pd.pit_mode='apply_vasicek' exige rho (escalar, por cartera) para la "
                    "transformación Vasicek.",
                    # El validador vive en la clase raíz, pero el campo que falta cuelga de la
                    # subsección: la ruta es la del formulario, no la del `raise`.
                    loc=(*_LOC_SECCION, "pd", "rho"),
                )
            if self.pd.systemic_factor_col is None:
                # Sin exención por scenarios.source='forward': forward no publica un factor
                # sistémico Z (sus curvas ya son PIT), así que ese Z implícito no existe.
                raise IfrsConfigError(
                    "pd.pit_mode='apply_vasicek' exige systemic_factor_col con el factor "
                    "sistémico Z explícito en la term-structure; forward no publica Z y "
                    "sus curvas ya son PIT (use pit_mode='consume_pit' para evitar el "
                    "doble ajuste macro).",
                    loc=(*_LOC_SECCION, "pd", "systemic_factor_col"),
                )
        return self

    def requisitos_incumplidos_por_contexto(
        self, contexto: ContextoConfig
    ) -> tuple[Requisito, ...]:
        """La curva y la provisión tienen que identificar las operaciones igual (D-CRE-6).

        Con ``survival.input.id_col`` la curva publica el valor de esa columna como ``row_id``; la
        provisión lo busca con ``row_id_col``. Si una declara la columna y la otra no, o declaran
        columnas distintas, ninguna operación se encuentra con su curva y la corrida muere en la
        provisión, después de ajustar la curva. Se avisa antes de correr. Sólo con la curva de
        ``survival``: la de ``forward`` hereda su ``row_id`` y la de ``markov`` tiene el suyo.

        Y las fechas del contrato (D-CRE-2, §3.2-7): leer la curva desde la edad de cada operación
        exige sus incumplimientos por período, que sólo publica ``discrete_hazard``; con otro
        método de ``survival``, la corrida se detiene antes de correr.
        """
        if self.pd.term_structure_source != "survival":
            return ()
        requisitos: list[Requisito] = []
        de_la_curva = contexto.identificadores.get("survival", self.row_id_col)
        if "survival" in contexto.identificadores and de_la_curva != self.row_id_col:

            def _por(columna: str | None) -> str:
                return "el índice del archivo" if columna is None else f"la columna «{columna}»"

            requisitos.append(
                Requisito(
                    path="row_id_col",
                    declared=self.row_id_col or "(índice del archivo)",
                    message=(
                        f"La curva de PD identifica cada operación por {_por(de_la_curva)} y la "
                        f"provisión, por {_por(self.row_id_col)}: no se encontrarían. Declara la "
                        "misma columna de identificador en las dos, o déjalas las dos vacías para "
                        "identificar por el índice del archivo."
                    ),
                )
            )
        metodo = contexto.metodos_de_ajuste.get("survival")
        campo = self._campo_de_fecha()
        if campo is not None and metodo is not None and metodo != _METODO_POR_PERIODOS:
            requisitos.append(
                Requisito(
                    path=campo,
                    declared=getattr(self, campo),
                    message=(
                        "Con las fechas del contrato, la curva de PD se lee desde la edad de cada "
                        "operación, y para eso la curva tiene que contar los incumplimientos de "
                        "cada período: sólo lo hace el ajuste por períodos discretos. Ajusta la "
                        "curva por períodos discretos, o quita las fechas."
                    ),
                )
            )
        return tuple(requisitos)

    def lee_fechas_del_contrato(self) -> bool:
        """Si la provisión lee la curva con las fechas de cada operación (D-CRE-2, §3.2)."""
        return self._campo_de_fecha() is not None

    def _campo_de_fecha(self) -> str | None:
        """La primera hoja de fecha declarada: donde se anclan los requisitos de la lectura."""
        if self.origination_date_col is not None:
            return "origination_date_col"
        if self.maturity_date_col is not None:
            return "maturity_date_col"
        return None

    def requisitos_incumplidos(self, columnas: frozenset[str] | None) -> tuple[Requisito, ...]:
        """Lo que esta sección se exige a sí misma y la corrida rechazará (D-INV-1).

        🔴 **El caso es el config DE FÁBRICA, y por eso importa tanto.** Medido: los tres defaults
        —curva de `survival`, modo «ya viene a condiciones actuales» y escenarios de `forward`—
        **construyen sin un solo error** y revientan al calcular, porque las dos columnas que esas
        dos elecciones exigen —la marca de curva ajustada al momento y el peso de escenario— las
        publica **únicamente** `forward`: cero apariciones en `survival/` y en `markov/`. Quien
        entra por el trabajo «Provisiones IFRS 9» recibe ese esqueleto; el preset F4 no lo sufre
        porque fija los tres a mano, o sea que el árbol ya sabía que los defaults no corren.

        Va aquí y no en cada sub-sección porque la condición cruza dos de ellas: `scenarios.source`
        no puede juzgarse sin mirar `pd.term_structure_source`, que vive en su hermana. Es el mismo
        criterio con que la invariante de `survival` vive en la clase que ve `method` y el flag.

        ⚠️ **No es un `model_validator`, y es deliberado.** Las tres combinaciones son alcanzables y
        legítimas para quien **inyecta su propia curva por código** con esas columnas puestas;
        cerrarlas al construir mataría ese uso. Aquí se avisa (D-PRE-5, D-INV-3) y el motor sigue
        siendo la autoridad sobre sí mismo.

        ``columnas`` no se usa: la exigencia es entre campos del config, no sobre el dataset.
        """
        del columnas  # no depende del dataset; precedente: `performance.partitions`
        requisitos: list[Requisito] = []
        desde_forward = self.pd.term_structure_source == "forward"
        if self.pd.pit_mode == "consume_pit" and not desde_forward:
            requisitos.append(
                Requisito(
                    path="pd.pit_mode",
                    declared=self.pd.pit_mode,
                    message=(
                        "Pediste usar las curvas tal cual, dando por hecho que ya vienen ajustadas "
                        "a las condiciones de hoy, pero el análisis del que las tomas no las marca "
                        "así: sólo el análisis prospectivo lo hace. Toma las curvas de ahí, o "
                        "elige dejarlas sin ajuste de ciclo."
                    ),
                )
            )
        if self.scenarios.source == "forward" and not desde_forward:
            requisitos.append(
                Requisito(
                    path="scenarios.source",
                    declared=self.scenarios.source,
                    message=(
                        "Pediste que los pesos de cada escenario vengan con las curvas, y el "
                        "análisis del que las tomas no los publica: sólo el prospectivo los trae. "
                        "Toma las curvas de ahí, pondera tú los escenarios, o calcula sobre uno "
                        "solo."
                    ),
                )
            )
        requisitos.extend(self._requisitos_del_contrato())
        return tuple(requisitos)

    def _requisitos_del_contrato(self) -> list[Requisito]:
        """Las fechas y la cuota del contrato (CASO-REAL-IFRS9 §3.2-7 y §3.3).

        Las fechas leen la curva de ``survival`` desde la edad de cada operación: con ``markov`` o
        ``forward`` —que ya parten del estado actual, o pueden venir de él— no se sabe qué
        significaría, y la PD a 12 meses de la calibración transversal no se puede leer desde la
        edad (pasada 3 de Codex sobre la enmienda). La cuota necesita el plazo que da el
        vencimiento y un saldo entregado, no un dispuesto más CCF. Los anclajes van a la hoja
        nueva, que es la elección que choca; ``declared`` no nombra la columna, para que el
        preflight no la confunda con una columna ausente.
        """
        requisitos: list[Requisito] = []
        campo = self._campo_de_fecha()
        if campo is not None and self.pd.term_structure_source != "survival":
            requisitos.append(
                Requisito(
                    path=campo,
                    declared=f"curva de {self.pd.term_structure_source}",
                    message=(
                        "Con las fechas del contrato, la curva de PD se lee desde la edad de cada "
                        "operación, y eso sólo se puede con la curva de supervivencia: las otras "
                        "fuentes ya parten del estado actual de cada operación. Toma la curva de "
                        "supervivencia, o quita las fechas."
                    ),
                )
            )
        if campo is not None and self.pd.base_pd_source == "calibration":
            requisitos.append(
                Requisito(
                    path=campo,
                    declared="PD a 12 meses de la calibración",
                    message=(
                        "Con las fechas del contrato, la curva de PD se lee desde la edad de cada "
                        "operación, y la PD a 12 meses tiene que salir de esa misma lectura: la "
                        "calibración la fija sin mirar la edad. Toma la PD a 12 meses de la curva, "
                        "o quita las fechas."
                    ),
                )
            )
        if campo is not None and self.pd.pit_mode != "ttc_only":
            # Pasada 3 de Codex: ajustar a las condiciones actuales la curva leída desde la edad no
            # está definido —qué factor sistémico corresponde a cada tramo es metodología PIT, que
            # la enmienda deja para otra fase (§3.2-7)—; se avisa en vez de inventarlo.
            requisitos.append(
                Requisito(
                    path=campo,
                    declared=f"PD ajustada ({self.pd.pit_mode})",
                    message=(
                        "Con las fechas del contrato, la curva de PD se lee desde la edad de cada "
                        "operación a lo largo del ciclo; ajustar esa lectura a las condiciones "
                        "actuales todavía no está disponible. Usa la PD a lo largo del ciclo, o "
                        "quita las fechas."
                    ),
                )
            )
        if self.ead.installment_col is not None and self.maturity_date_col is None:
            requisitos.append(
                Requisito(
                    path="ead.installment_col",
                    declared="(sin fecha de vencimiento)",
                    message=(
                        "La cuota arma la tabla de pagos hasta el vencimiento de cada operación, y "
                        "no declaraste la fecha de vencimiento: sin plazo no hay tabla. Declara la "
                        "columna del vencimiento, o quita la cuota."
                    ),
                )
            )
        if self.ead.installment_col is not None and self.ead.method != "provided":
            requisitos.append(
                Requisito(
                    path="ead.installment_col",
                    declared=f"EAD por {self.ead.method}",
                    message=(
                        "La tabla de pagos parte del saldo de hoy entregado en el archivo, y la "
                        "exposición se está calculando con el factor de conversión. Entrega la "
                        "exposición en una columna, o quita la cuota."
                    ),
                )
            )
        return requisitos
