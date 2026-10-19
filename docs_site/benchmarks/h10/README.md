# Benchmark parcial de scorecards

German Credit, Taiwan como suplemento y dos carteras sintéticas, con cuatro recetas de
bayesrisk y tres referentes Python por cartera: **28 combinaciones ejecutadas**. Es evidencia
exploratoria sobre estas muestras y esta partición. No acredita superioridad universal, no
elige un modelo automáticamente y no completa el corpus previsto para H10/C6. LC, HC, PAKDD
y los referentes R permanecen pendientes.

[Paquete completo](../../downloads/h10-benchmark.tar.gz) ·
[Manifiesto externo y SHA-256](../../downloads/h10-benchmark.json) ·
[Notebook mínimo](minimo.ipynb) · [Anexo técnico](anexo.ipynb)

Los notebooks sueltos necesitan el paquete completo: auxiliares, fuentes UCI, datos preparados,
índices, grupos, configs, predicciones, tablas, intervalos, locks e informes HTML/Word/Excel.
No contiene objetos Python serializados; las fuentes públicas se identifican más abajo.

## Empezar

Usa Python **3.12.10** en un entorno nuevo. Extrae el archivo en una carpeta nueva y conserva
su manifiesto externo. El mínimo tiene cinco conceptos: `Scorecard`, `run`, `summary`,
`to_yaml`, `export_excel`; el anexo separado explica el experimento.

La medición usa el **candidato de CI de S53**, commit
`bf829d4b9f44008a46374676cf15edbc874f03d8`, con la corrección de target de A. El número de
versión sigue siendo 2.16.0, pero **el wheel publicado en PyPI no tiene esa corrección**.
No basta instalarlo por versión. Descarga `candidate-distributions-with-evidence` del
[run de CI de origen](https://github.com/nexolabs-gh/bayesrisk/actions/runs/38948141309).
Los artifacts de GitHub pueden requerir iniciar sesión; los datos no exigen cuentas.
SHA-256 del wheel medido:

`351bb71923d2f388639179cf0d190220b76a86d87f68445d3df6b59b27e4ebcc`

Instala primero el lock con hashes y **después** el candidato exacto, comprobando antes su
SHA. Desde la extracción, con el Python del entorno nuevo:

<!-- h10-entorno:start -->
```text
python -m pip install --require-hashes -r notebook-lock.txt
python -m pip install --no-deps --force-reinstall /ruta/al/candidato/bayesrisk-2.16.0-py3-none-any.whl
python -m pip check
python -m ipykernel install --sys-prefix --name python3 --display-name "Python 3 (H10)"
python -m jupyterlab
```
<!-- h10-entorno:end -->

`notebook-lock.txt` incluye Jupyter; `requirements-lock.txt` fija el benchmark sin notebook.
Los `.in` y `constraints.txt` permiten resolver con uv; los hashes `.txt` identifican esta
medición. El entorno está separado del core; no se crea un extra de bayesrisk.

Abre primero `anexo.ipynb` para verificar la extracción intacta y leer las tablas; después
`minimo.ipynb` para ejecutar un scorecard. El mínimo escribe en la carpeta hermana `h10-work`.
Si modificaste archivos entregados, usa otra extracción para verificar integridad.
El índice del Word se actualiza al abrirlo en Word.

Para repetir todo el experimento, desde otra extracción intacta:

<!-- h10-reproduccion:start -->
```text
python reproduce.py
```
<!-- h10-reproduccion:end -->

El script fija hash seed y threads antes de importar el stack, ejecuta calentamiento y tres
procesos independientes secuenciales, compara resultados y conserva fallos en el denominador.
No sobrescribe reproducciones. Una fuente alterada o una descarga fallida bloquea la ejecución.
Todo auxiliar está en `h10_benchmark/`; no se importa este repositorio.

## Fuentes y frontera anterior al ajuste

Se contrastaron fichas y APIs oficiales UCI, archivos y
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). La licencia consta en las fichas;
la API confirma metadatos/target, **no una licencia explícita**. `sources.json` conserva URLs,
fechas, estados HTTP y hashes. La licencia del software no autoriza los datos.

| Fuente | Atribución | Transformación |
|---|---|---|
| German | Hans Hofmann, UCI, [DOI](https://doi.org/10.24432/C5NC77), CC BY 4.0 | 1 bueno/2 malo → 0/1; 20 predictores; índice original |
| Taiwan | I-Cheng Yeh, UCI, [DOI](https://doi.org/10.24432/C55S3H), CC BY 4.0 | Target renombrado; SEX/EDUCATION/MARRIAGE categóricos; ID sólo procedencia; 23 predictores |
| Consumo/drift | Generadores bayesrisk, Apache-2.0 | IDs/cohortes conservados; seis predictores; OOT 2024Q2 |

Se redistribuyen las dos fuentes UCI originales con atribución y huellas, y los Parquet
derivados con estas transformaciones. No se publica el archivo local Lending Club.

German/Taiwan se agrupan por X admisible exacto, excluyendo target/ID. No hay una entidad
personal adicional acreditada. `GroupShuffleSplit` separa 25% de grupos, semilla 20261016,
con índice/orden originales. Sólo el complemento entra a `Scorecard(partition="random")`,
con Holdout/semilla de fábrica. Referentes reciben idénticos Desarrollo/evaluación/orden.

| Cartera | Desarrollo (malos) | Holdout (malos) | Evaluación (malos) |
|---|---:|---:|---:|
| German | 598 (168) | 152 (53) | 250 (79) |
| Taiwan | 18082 (3958) | 4418 (1003) | 7500 (1675) |
| Consumo | 3961 (924) | 1031 (244) | 1008 (239) |
| Drift | 3955 (1312) | 1000 (315) | 1045 (507) |

Cada muestra tiene al menos 30 malos y un bueno; no se buscaron semillas favorables.
Holdout es diagnóstico. No se eligieron recetas mirando evaluación. Los grupos X son un
proxy: no demuestran independencia de personas ni eliminan dependencias no observadas.

## Recetas y lectura de cifras

Fábrica conserva todos los defaults. Las otras tres variantes cambian uno: `stepwise=False`,
`max_bins=5` o `monotonic="auto"`. Son recetas de investigación, no nuevos presets.

Referentes: OptBinning 0.20.0 MIP, seis bins, mínimo 5% y tendencia auto asc/desc;
scorecardpy 0.1.9.7 con árbol WoE, un core y positivo 1; skorecard 1.6.9 con prebinning
árbol/categórico y OptimalBucketer MIP. Logística sin penalización, lbfgs, 1000 iteraciones,
semilla 20261016; escala PDO 20 / odds 50 / puntos 600. Detalles en `h10_benchmark/recipes.py`.
Missing/special/intercepto tienen convenciones propias; no se fabrican Studies de terceros.

PD creciente de riesgo. AUC, Gini=2AUC−1, KS, Brier, log-loss, PD media, tasa observada y PSI
con deciles únicos de Desarrollo, extremos infinitos y piso 1e-6 renormalizado. Una referencia
degenerada falla. El anexo muestra las 28 filas; `aggregate/metrics.csv` y `.json` conservan precisión.

Los 24 contrastes AUC frente a fábrica usan 1000 bootstrap pareados de grupos completos,
reemplazo y semilla 20261016. Una réplica monoclase impide publicar intervalo. Son exploratorios,
condicionados al modelo/partición; no estiman variación de entrenamiento ni corrigen multiplicidad.

Tiempos: mediana/rango de tres procesos con calentamiento separado. `fit_seconds` comprende
el pipeline bayesrisk sin informe, o el fit del referente; `apply_seconds` incluye evaluación
y referencia Desarrollo; `report_seconds` mide el render original HTML/Word, excluye
Excel, verificador y presentación posterior de tablas anchas.
Los costes no son funcionalmente equivalentes entre herramientas.

## Verificación y límites

Tres repeticiones Windows conservaron exactamente predicciones, métricas, variables, configs
y 16 proyecciones/escala maestra. Sus invocaciones acreditan procesos separados; no se registraron
PID ni pools efectivos originalmente. El runner distribuido sí exige y registra ese entorno.

Los 16 HTML/Word/Excel se reconciliaron con tablas originales; CSV/JSON con predicciones.
La descarga contiene derivados con rutas portables, hashes originales/derivados en
`provenance.json`, cifras y etiquetas intactas. Las tablas Word de más de ocho columnas
usan páginas apaisadas y fuente de nueve puntos; sobre quince columnas, A3. Es presentación
del benchmark, sin modificar el renderer del motor. Las cuatro carteras pasaron equivalencia
guiada/completa/backend de pantalla y permutación exclusiva de etiquetas Holdout: bins,
selección, coeficientes, calibración y scoring iguales; el hash de procedencia cambia.

Latencia visible: Chrome 155, Jupyter y pantalla reales, desde llamada/click hasta resumen
visible tras dos frames. Tres pares, mismo candidato y entrada, calentamientos separados:

| Puerta | Mediana base (ms) | Mediana H10 (ms) |
|---|---:|---:|
| Guiada | 677,6 | 678,8 |
| Completa | 428,1 | 466,4 |
| Pantalla | 8902,5 | 8903,5 |

Los rangos se superponen; completa aumentó 38,3 ms en esta muestra pequeña. No demuestra
igualdad estricta ni mejora. No se cambió código del motor o pantalla. Simplicidad:
37 marcas esenciales, 39 paths, 36 campos atómicos esenciales (denominadores distintos),
208 avanzados, 12 bloques, máximo 6 esenciales por sección. Cero perillas nuevas.

CI mínimo/censo/invariantes bloquea red tras instalar el candidato. Tags/despachos manuales
exigen 28 recetas secuenciales Linux; cada recibo identifica el wheel exacto. Esto no publica
una release. Los fallos CP/import históricos y el corpus pendiente se conservan separados
de las 28 recetas admitidas y ejecutadas aquí.
