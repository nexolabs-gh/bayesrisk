# Provisión interna paso a paso

!!! note "Requiere bayesrisk 2.17.0 o posterior"
    Las puertas `Provision` y `Lgd` no forman parte de PyPI 2.16.0. Confirma la disponibilidad
    de `2.17.0` en [PyPI](https://pypi.org/project/bayesrisk/#history) antes de instalarla.
    Los cuadernos conservan las salidas de su
    [candidato de verificación original](https://github.com/nexolabs-gh/bayesrisk/actions/runs/39523257538);
    CI vuelve a ejecutarlos contra el código documentado y coteja sus resultados.

Este recorrido experimental calcula la provisión por grupos con una PD y una LGD ya
declaradas. No estima ni valida esas probabilidades. La PD del ejemplo es ilustrativa;
para una cartera real debes aportar la de tu modelo.

[Descargar el cuaderno ejecutado](../notebooks/primera-provision-interna.ipynb).

<!-- provision-guiada:start -->
```python
from pathlib import Path

import pandas as pd

from bayesrisk import Provision
from bayesrisk.ui.datasets import materialize

cartera = pd.read_parquet(materialize("provision_interna_generica", workdir=Path("datos")))
cartera["pd_declarada"] = 0.02  # Sólo ilustración: no es una PD estimada.
provision = Provision(cartera, as_of="as_of_date", portfolio="portfolio",
                      exposure="exposure_amount", pd="pd_declarada", lgd="lgd", formats=["csv"])
provision.run(until="provisioning_internal")
provision.summary()
provision.resume()
provision.export_excel()
provision.export("provision.zip")
```
<!-- provision-guiada:end -->

El cálculo conserva la fórmula de grupos del motor: exposición del grupo por PD media
ponderada por exposición por LGD media ponderada por exposición. El detalle reparte esa
provisión entre operaciones según exposición; no equivale a sumar productos individuales.
El informe, las tablas completas y la evidencia quedan en el proyecto exportado.

La PD y la LGD provistas son entradas externas: un config aislado no reproduce la corrida.
Sin un identificador de operación declarado, sólo se verifica el índice técnico del archivo.

## Entrenar una LGD y aplicarla a otra cartera

La ruta experimental `Lgd` conserva un predictor fraccional con intercepto y covariables
numéricas crudas. No usa WoE, no imputa, no elige variables ni cambia de algoritmo ante un fallo.
Entrena sólo con la muestra declarada `train`; `evaluation` conserva sus resultados observados
para un diagnóstico descriptivo. La media de referencia también se calcula sólo con train.

[Descargar el cuaderno de LGD ejecutado](../notebooks/primera-lgd.ipynb).

<!-- lgd-guiada:start -->
```python
from pathlib import Path

import pandas as pd

from bayesrisk import Lgd, Provision
from bayesrisk.ui.datasets import materialize

historia = materialize("lgd_historia_sintetica", workdir=Path("datos"))
lgd = Lgd(historia, target="lgd_observada", features=["deuda_ingreso", "antiguedad_meses"],
          entity="deudor", sample="muestra", default="incumplio", resolved="resuelto",
          id="loan_id", purpose="Demostrar el flujo con datos inventados",
          assumptions=["Historia sintética con muestras y resultado declarados"],
          limitations=["No valida calidad ni transportabilidad"], formats=["csv", "xlsx"])
lgd.run(raise_on_error=True)
lgd.summary("lgd_training")
cartera = pd.read_parquet(materialize("provision_interna_generica", workdir=Path("datos")))
cartera = cartera.drop(columns="lgd")
cartera["pd_declarada"] = 0.02  # Sólo ilustración; no es una PD estimada.
provision = Provision(cartera, as_of="as_of_date", portfolio="portfolio",
                      exposure="exposure_amount", pd="pd_declarada", lgd=lgd.model_,
                      id="loan_id", formats=["csv"])
provision.run(raise_on_error=True)
lgd.export_excel()
lgd.export("historia-lgd.zip")
provision.export("aplicacion-lgd.zip")
provision.summary()
```
<!-- lgd-guiada:end -->

La preparación importa tanto como el ajuste. En el ejemplo, las 400 operaciones son inventadas:
300 de entrenamiento, 80 de evaluación y 20 abiertas excluidas, cuyo objetivo permanece vacío.
Un deudor tiene dos operaciones dentro de la misma muestra; ninguna entidad cruza las muestras
elegibles. El identificador de operación es único. La severidad sintética incluye 0 y 1. La
cartera de aplicación tiene 6.000 filas y no lleva objetivo observado. Los datos vienen con el
paquete; no representan recuperaciones de una institución ni prueban desempeño futuro.

Para tu historia, declara **seis roles**: objetivo, covariables, entidad de separación, muestra,
incumplimiento y resultado disponible. El ID de operación se declara por separado. Usa
`train`, `evaluation` o `excluded`, y flags booleanos o 0/1 sin nulos. Sólo incumplimientos con
resultado disponible y muestra elegible participan; toda exclusión queda contada. Los objetivos
elegibles deben estar en [0,1] y las covariables ser finitas; no se exige objetivo a procesos abiertos
excluidos. Debe haber ambas muestras y suficientes operaciones para un ajuste de rango completo.

Declara en propósito, supuestos y limitaciones qué significa el objetivo, cuándo está disponible,
cómo se definieron las muestras y qué población queda fuera. El motor conserva esas declaraciones;
no verifica su suficiencia, temporalidad ni representatividad. Sin ellas lo advierte. Separar
entidades declaradas no certifica independencia del pipeline completo ni elimina sesgo de selección.
La comparación con la media es descriptiva, sin umbral de aprobación ni promesa de superioridad.

En pantalla, **Ajustar LGD con historia separada** ofrece los mismos seis campos. También hay un
acceso desde **Severidad modelada o calculada**. Para aplicar, elige **Aplicar un modelo de historia separada** y carga el
archivo `modelo_lgd.parquet` del botón **Proyecto, modelo y entradas (ZIP)** en Reporte.
El ZIP incluye el estudio conservado, entradas y una receta de reproducción. Si se pidieron
CSV/Excel, también incluye `lgd_report__lgd_training_model_table.csv` y
`lgd_report__modelo_lgd.xlsx`.
Es una tabla global de coeficientes: no lleva llave para alinearla con las filas de cartera.
Las tablas PD conservan su exigencia de cobertura y alineación. Study y joblib no se cargan por HTTP.

Por código completo, `lgd.to_yaml()` conserva los seis roles en `lgd_training`; usa `bayesrisk.run`
con ese config para entrenar. Para aplicar, `provisioning_internal.lgd.method="fitted"` consume
el artefacto externo `("lgd_training", "model_table")`. Puedes recuperar la tabla con
`bayesrisk.lgd_training.model.read_model_table` y validar su predictor con
`bayesrisk.LgdModel.from_frame`. CSV y Parquet conservan float64 con lectura round-trip; Excel
admite diferencias de representación de hasta `atol=1e-12, rtol=1e-10` en predicción. No edites
manualmente los textos codificados de la tabla ni la sustituyas por la tabla legible del informe.

El HTML, Word y PDF, cuando sus extras están disponibles, muestran población, diagnóstico,
coeficientes, procedencia y límites; CSV/Excel entregan las tablas completas. Guarda ambos ZIP:
uno conserva la historia y el ajuste, el otro la cartera y sus entradas externas. `Study.load`
exige confianza explícita y conserva la comprobación de config; no autentica individualmente
archivos joblib. La procedencia declarada del modelo tampoco autentica a su autor.
