# Provisión interna paso a paso

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
