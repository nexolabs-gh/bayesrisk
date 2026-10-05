# La provisión IFRS 9 de punta a punta

Esta guía lleva una cartera desde el archivo hasta la provisión IFRS 9 firmable —la cifra, su
informe y su evidencia— por las tres puertas de bayesrisk: la **guiada** (`bayesrisk.Ecl`, unas
veinte líneas), la **completa** (el config entero, en YAML o por código) y la **pantalla**
(`bayesrisk-ui`). Las tres corren el mismo config y llegan a la misma cifra.

!!! note "Qué garantiza"
    La firma de `bayesrisk.Ecl`, sus métodos y la forma de sus resúmenes son estables (SemVer
    2.x). Las cifras siguen la marca experimental de los motores de supervivencia y de
    provisiones, que pueden cambiar dentro de la 2.x. Necesita el extra `scoring`, que trae el
    ajuste de la curva.

## Qué calcula

La pérdida crediticia esperada (ECL) de cada operación en tres etapas: Stage 1 provisiona la
pérdida de los próximos 12 meses y Stage 2 y 3, la de toda la vida de la operación (IFRS 9
5.5.3 y 5.5.5). La probabilidad de incumplimiento de cada período sale de una **curva de PD**
que se ajusta sobre la historia de incumplimientos de tu propia cartera —un modelo de riesgo en
tiempo discreto con tus covariables—; la LGD y la exposición (EAD) vienen de tu archivo; cada
pérdida se descuenta a la tasa efectiva anual de la operación; y la etapa la deciden la mora
(30 y 90 días, las presunciones de la norma) y la marca de incumplimiento.

## Qué necesita de tus datos

Un archivo (`.csv`, `.parquet` o `.xlsx`) con una fila por operación y estas columnas, con el
nombre que tengan en tu archivo:

| Para qué | Columnas |
|---|---|
| La provisión | fecha de corte (un solo valor), cartera, exposición ya calculada, LGD, tasa efectiva **anual**, días de mora y, si la tienes, la marca de incumplimiento |
| La curva de PD | cuánto tiempo se observó cada operación (entero ≥ 1) y si incumplió (0/1); la unidad de ese tiempo (`"month"`, `"quarter"`, `"year"`…) y hasta cuántos períodos se proyecta la curva |
| Opcional | el identificador de la operación y las covariables que ordenan el riesgo |

Dos cosas que conviene saber antes de armar el archivo con datos reales:

- **La historia vive en las mismas filas que la cartera.** Los incumplimientos de tu historia
  suelen estar en operaciones que ya se cerraron —castigadas o pagadas—. Inclúyelas con
  exposición 0: alimentan la curva y no suman provisión. Los conteos por etapa del resumen las
  cuentan como operaciones.
- **El identificador puede ser una columna.** `id=` verifica que sea única; la curva, la provisión
  y el resumen identifican cada operación por su posición en el archivo, que la copia de la
  corrida conserva.

## La puerta guiada

`bayesrisk.Ecl` arma el config desde tus columnas, infiere y declara lo que no preguntó —cuántos
períodos son 12 meses, el esquema de las columnas, que es una corrida de cartera— y cuenta cada
etapa al correr. Aquí con la cartera de ejemplo del paquete: 6.000 operaciones al 30 de junio de
2025.

<!-- provision-ifrs9-guiada:start -->
```python
from pathlib import Path

from bayesrisk import Ecl
from bayesrisk.ui.datasets import materialize

datos = materialize("ifrs9_retail_latam", workdir=Path("bayesrisk-runs"))

ecl = Ecl(
    data=datos,
    id="loan_id",
    as_of="as_of_date",
    portfolio="portfolio",
    exposure="ead",
    lgd="lgd",
    rate="eir",                     # la tasa efectiva ANUAL
    days_past_due="days_past_due",
    default="is_default",
    duration="duration", event="event", period="year", horizon=5,
    covariates=["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"],
    name="provision_2025_06",
)

# Primero, sólo hasta la curva: mirar sus coeficientes antes de decidir.
ecl.run(until="survival")
print(ecl.results["survival"])      # los coeficientes de la curva

# Una decisión humana, con su motivo: la covariable no vendrá en los próximos cierres.
ecl.exclude("antiguedad_meses", reason="no viene en el archivo de cartera de los próximos cierres")
ecl.resume()                        # una corrida nueva y completa con la decisión

print(ecl.summary())                # el resumen final, con sus supuestos
paquete = ecl.export("provision_2025_06.zip")
```
<!-- provision-ifrs9-guiada:end -->

Cada etapa habla en palabras de provisiones —«Cartera», «Curva de PD», «Provisión IFRS 9» e
«Informe y ficha»— y `ecl.summary("survival")` suma la PD acumulada por período y cartera. Las
decisiones viajan en el config (sección `decisions`), en el registro de auditoría y en el resumen
final; la otra que la puerta admite es `ecl.rebut_backstops(stage2_days=..., reason=...)`, que
rebate las presunciones de mora y que la norma admite sólo con información razonable y
sustentable.

## La puerta completa

Lo que la puerta guiada corrió es un `BayesRiskConfig` entero: `ecl.config`, y en disco
`bayesrisk-runs/provision_2025_06/config.yaml`. Ese YAML es la puerta completa: se versiona, se
edita —todo lo que el motor admite está ahí, incluido lo que la puerta guiada no pregunta— y se
corre con `bayesrisk.run`.

<!-- provision-ifrs9-completa:start -->
```python
from pathlib import Path

import bayesrisk
from bayesrisk.core.config import load_config

config = load_config(Path("bayesrisk-runs") / "provision_2025_06" / "config.yaml")
study = bayesrisk.run(config, run_dir=Path("bayesrisk-runs") / "provision_por_yaml")
assert study.run_context.status == "done", study.run_context.error

card = study.artifacts.get("provisioning_ifrs9", "card")
print(f"ECL total: {float(card.total_ecl_reported):,.0f}")  # la misma cifra que la puerta guiada
```
<!-- provision-ifrs9-completa:end -->

El mismo config da la misma cifra y el mismo `config_hash`: la identidad de la corrida no
depende de la puerta por la que entró.

## La pantalla

```bash
bayesrisk-ui
```

El trabajo «Provisiones IFRS 9 / ECL» pregunta lo mismo que la puerta guiada y nada más: no pide
qué es un cliente malo ni cómo separar muestras —los muestra como «No aplica en una corrida de
cartera»— y sí la duración, el evento, la unidad y el horizonte de la curva. La curva abre sus
cinco campos esenciales y la provisión sus siete; el resto queda en «Avanzado». Los 12 meses del
Stage 1 se infieren de la unidad, como en la puerta guiada. Resultados pinta el mismo resumen,
con sus supuestos, la curva de PD por cartera y la ECL por cartera y etapa.

## Lo que entrega

- **El informe** (HTML; Word, PDF y fuente editable si los pides): abre con la página «Resumen de
  la corrida» —ejecución, supuestos, las cinco cifras, qué revisar, decisiones y archivos— y su
  capítulo de provisiones publica la curva de PD por período y cartera, los coeficientes del
  ajuste y la ECL por cartera y etapa.
- **El Excel**, si lo pides con `ecl.export_excel()` (extra `excel`): un libro por etapa y uno de
  decisiones.
- **La evidencia**: el config, la copia de tus datos con su huella, el registro de auditoría y la
  ficha, en `bayesrisk-runs/<nombre>/`; `ecl.export()` la empaqueta.

## Lo que la cifra supone

El resumen final dice los supuestos de cada corrida. Estos son los que más mueven la cifra en una
cartera real, medidos al correr esta misma provisión sobre dos carteras públicas además de la del
paquete —créditos de consumo de Lending Club (2013–2016) e hipotecas de Freddie Mac (2016)—:

| Supuesto | Qué significa | Cuánto movió la ECL al cambiarlo |
|---|---|---|
| PD a lo largo del ciclo (TTC), escenario único | la curva resume la historia, sin condiciones actuales ni escenarios macroeconómicos | — (IFRS 9 5.5.17 pide considerarlos) |
| Stage 3 con la PD de la curva | una operación ya en incumplimiento se provisiona como una sana; la opción «Stage 3 como EAD·LGD directo» (`provisioning_ifrs9.ecl.stage3_direct`, en «Avanzado») la provisiona con su pérdida de incumplimiento | +40 % en la cartera del paquete; +98 % en las hipotecas |
| La curva parte de la originación | no se condiciona a la antigüedad de cada operación ni se corta en su plazo remanente | +6 % en consumo de tres años; −47 % en hipotecas de diez años |
| Exposición constante | la EAD no amortiza a lo largo de la vida | −38 % en consumo de cuota fija; −4 % en hipotecas |
| El aumento significativo del riesgo, sólo por mora y marca | sin PD de origen no hay comparación con lo esperado al originar | con el FICO actual, un 2,7 % de las operaciones en Stage 1 de Lending Club pasaría a Stage 2 |

Ninguno de esos cambios está hoy en la puerta guiada: lo que se puede cambiar, se cambia en el
config (la puerta completa) y queda con su `config_hash`; lo demás está declarado como límite
conocido en el [changelog](../changelog.md).
