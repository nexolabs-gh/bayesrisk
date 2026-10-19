# Enmienda H10 — Benchmarks reproducibles y revisión de defaults del scorecard

| Campo | Valor |
|---|---|
| Identificador | D-H10-1…6 |
| Módulo | Documentación, evidencia y CI; contratos existentes de `bayesrisk` |
| Fase / tanda | H10, después de H2b; diseño S52 |
| Estado | **Aprobada por Cami el 2026-10-16 (S52), D-H10-1…6. S53 autorizada sólo para capa A** |
| Depende de | SDD-06…10, SDD-22, SDD-31, comparación guiada publicada en 2.16.0 |
| Lo consumen | Modelador, documentación pública, validación de cada release |
| Autor / fecha | Codex, 2026-10-16 |

**TL;DR:** La 2.16.0 completa 16 corridas en dos carteras públicas y dos sintéticas.
No hay superioridad general frente a los tres referentes ni evidencia suficiente para cambiar
defaults globales. Se propone conservarlos, corregir primero dos defectos de entrada bajo sus
contratos existentes y entregar H10 por capas verificables. German no completa las cuatro
carteras de H10; Taiwan aporta contraste adicional. Lending Club, Home Credit y PAKDD conservan
su lugar y sus impedimentos explícitos. Inglés sigue condicionado a la poda de 3.0.

**Aprobación:** Cami aceptó interactivamente las tres recomendaciones de §12: diseño por capas
(D-H10-1/4/5), conservar defaults (D-H10-2) y S53 sólo para A (D-H10-3/6).
Revisión independiente: dos pasadas, un hallazgo material de entorno corregido → **approve**
sin materiales sobre `7f37b413..d2f6b9fe`; verificación por inspección, sin recálculo Parquet
del revisor. No se abrió tercera pasada. Aprobación del diseño no equivale a entrega de H10.

## 1. Propósito y responsabilidad

H10 convierte afirmaciones de desempeño y facilidad de uso en evidencia que otra persona puede
reproducir desde una instalación publicada. Esta enmienda especifica su primera entrega de
scorecard y el tratamiento de los defaults; no crea otro motor, comparador ni interfaz.

La responsabilidad es mantener un corpus público de notebooks, recetas, manifiestos y resultados
con cobertura declarada. No certifica aptitud de un modelo para un banco, no elige su target ni
su política de crédito y no transforma pruebas exploratorias en recomendaciones universales.
No modifica CMF, IFRS 9, LGD, identidades congeladas, métodos estadísticos ni contratos de H9R.

### 1.1 Censo contra el código publicado

Base medida: commit `7f37b4135fb3ff116ba63d5bff79e23a8f94f01d`, tag `v2.16.0`, paquete PyPI
2.16.0 instalado en un entorno separado. El relevo coincide con Git y el CI verde de S51;
no se repitieron suites de release. Fecha de observación: 2026-10-16.

| Universo / promesa | Evidencia encontrada | Brecha H10 |
|---|---|---|
| Notebooks públicos versionados | 1: `docs_site/notebooks/primer-scorecard.ipynb`, 13 celdas, 6 de código, 22 líneas útiles | Ningún notebook comparativo externo |
| Docs publicadas | 21 páginas Markdown, 11 guías; 24 bloques Python delimitados, 22 nombres únicos en 10 páginas | Guías existentes no equivalen a benchmark |
| Datasets del paquete | 6 generadores: consumo, hipotecario, drift, provisiones consumo, provisión interna genérica e IFRS 9 retail | Sintéticos, no evidencia bancaria externa |
| Catálogo externo | 42 filas, 12 de scorecard; sin campos de licencia, hash o split; `data/externos` no existe aquí | «Descargado» histórico no prueba disponibilidad actual |
| Adaptadores / benchmarks externos H10 | 0 públicos identificados | Los guiones privados S52 no son capacidad entregada |
| CI | 6 workflows, 11 definiciones de jobs; 13 jobs en main, 19 en tag/night | Ningún job comparativo H10 |
| Distribución | Wheel: 329 entradas, sin notebooks/docs/scripts; sí `ui/datasets.py`, Scorecard y Comparison | La guía descargable y sus auxiliares deben publicarse completos |
| Alcance C6 | German, Lending Club, Home Credit, PAKDD y también `scorecard` de R | R permanece pendiente; no se elimina por omisión de la fila H10 |

Los seis generadores tienen 6.000 filas salvo hipotecario (4.000). Los tres notebooks privados
históricos no cuentan como entrega pública. `PKDD99` no es `PAKDD`.
El censo usa universos Git y distribución, no sólo búsqueda de nombres. La comprobación automática
bidireccional de S52 cubre la lista de notebooks; las demás categorías son un relevamiento trazado
por rutas, con su automatización exhaustiva pendiente en capa B. No se declara cerrado H10.

## 2. Contexto y ubicación en la arquitectura

Las recetas consumen `Scorecard` y su configuración completa; `Comparison` consume exclusivamente
corridas bayesrisk compatibles. Los referentes se evalúan en un arnés documental externo a las
APIs de producción. Un JSON de métricas no se convierte artificialmente en `Study` de un tercero.

Puertas existentes: guiada (`Scorecard`), completa (config declarativo/Study) y pantalla (carga de
datos y configuración del mismo scorecard). La entrega B aporta un notebook mínimo, su config
exportado y archivos admitidos por la pantalla; verifica equivalencia de las tres rutas. El
benchmark de terceros vive en el anexo técnico descargable, sin añadir botones al modelador.

### 2.1 Capas propuestas, cada una con cierre propio

| Capa | Entregable y condición de cierre |
|---|---|
| A — Integridad de entrada | Corregir los dos defectos de §8; tests nacidos rojos, matriz de dtypes/targets, proyección canónica de casos válidos sin cambios. No modificar defaults |
| B — Primer benchmark público | German + Taiwan suplementario + consumo/drift; notebooks y auxiliares descargables juntos, manifiesto, lock, tablas completas y artefactos. Ejecución desde wheel en directorio sin checkout. Gate CI y controles de §11 |
| C — Cobertura restante | Revalidar permisos/acceso de Lending Club, Home Credit y PAKDD; sólo admitir cada cartera con protocolo de observación/target/split documentado. Adaptador específico revisado antes de ejecutarlo. Incorporar referente R con entorno separado/licencia documentada |
| D — Documentación bilingüe | Sólo cuando esté podado 3.0, según decisión vigente. Esta enmienda no anticipa traducciones |

La aprobación limita S53 a A. No autoriza releases, recapturas ni workloads
H9R. B es entrega parcial explícita; C no tiene fecha prometida ni se satisface sustituyendo datos.

## 3. Conceptos y fundamentos

Unidad evaluada: una fila de la fuente; evento malo codificado `1`. AUC usa PD creciente con
riesgo; Gini = `2*AUC − 1`; KS = máximo de TPR − FPR. Brier es la media de `(p−y)²` y log-loss
la media negativa de `y*log(p)+(1−y)*log(1−p)`, con protección numérica de sklearn registrada.
No se compara AUC del score invertido con AUC de PD ni se usa exactitud dependiente del corte.

PSI común S52: límites de deciles obtenidos **sólo en Desarrollo**, únicos, extremos infinitos;
proporciones por intervalo con piso `1e−6`, renormalizadas a suma uno en cada muestra;
`sum((a−b)*log(a/b))`. Debe rechazarse una referencia degenerada sin dos límites distintos.
Es una receta comparativa declarada, no reemplaza el PSI nativo ni sus semáforos. Brier/log-loss,
PD media y tasa observada aportan diagnóstico de calibración, no demuestran calibración completa.

El bootstrap de diferencias AUC es pareado, estratificado por evento, 1.000 réplicas, percentiles
2,5/97,5 y semilla 20261016. Está condicionado a estos modelos y partición; no incorpora varianza
de entrenamiento, selección de hipótesis ni multiplicidad. No es evidencia confirmatoria global.

### 3.1 Fuentes, licencias y doble verificación

| Fuente oficial y comprobación independiente | Estado medido / tratamiento |
|---|---|
| [UCI German](https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data), API id 144 y `german.doc` dentro del ZIP oficial | 1.000 filas, 20 predictores, 300 malos; clase 1 buena/2 mala; CC BY 4.0 en ficha/API. Sin fechas: split aleatorio, nunca OOT. Dataset histórico, no representatividad actual |
| [UCI Taiwan](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients), API id 350 y XLS oficial | 30.000 filas, 23 predictores, 6.636 malos; historias abril–septiembre 2005 y target del mes siguiente; CC BY 4.0. ID retirado; SEX/EDUCATION/MARRIAGE categóricas. No inventar fechas por fila ni OOT |
| [Lending Club/Happen, términos](https://www.happen.com/legal/terms-of-use?b=lc), endpoints oficiales de descarga y estadísticas | Dos endpoints respondieron 403; `resources.lendingclub.com/LoanStats3a.csv.zip` redirigió a resources.happen.com y entregó ZIP. Disponibilidad técnica no acredita permiso de redistribución/automatización; no modelado ni publicado. La copia local no se incluye en la evidencia versionada |
| [Home Credit, reglas](https://www.kaggle.com/competitions/home-credit-default-risk/rules) y [datos](https://www.kaggle.com/competitions/home-credit-default-risk/data) oficiales | HTTP 200 entrega shell JS, sin términos verificables en la respuesta capturada; no datos descargados. Aceptación histórica del catálogo no reemplaza comprobación actual |
| [PAKDD 2009, organizador](https://pakdd.org/archive/pakdd2009/front/show/competition.html) y [booklet oficial](https://pakdd.org/archive/pakdd2009/downloads/PAKDD2009-booklet.pdf) | Existencia de competencia corroborada; host de datos Neurotech no resolvió; licencia y corpus no verificables. No modelado |

SHA256 ZIP German: `e12d9d5def6845c0622634a1cd2ab87fa470668c4298f1ec52a4e403376a435b`.
SHA256 ZIP Taiwan: `56c885f84457f6680f8438f02bfcdac9579323d8a94465ee5f26e32baa727602`.
La futura publicación atribuye autores/UCI, enlaza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
y declara transformaciones. Cada fuente exige dos comprobaciones oficiales trazadas; si no
existen, su estado queda pendiente, no se sustituye por un espejo sin licencia.
Para LC/HC/PAKDD no se afirman tamaños, fechas ni target de un corpus no inspeccionado.

## 4. API pública (contrato)

No se propone API nueva ni alias de benchmarking. Se preservan `Scorecard(...).run()`,
`summary()`, `apply()`, exportación de configuración, informes y `Comparison(...).run()`.
El notebook mínimo utiliza únicamente APIs distribuidas. Su anexo técnico importa auxiliares
del mismo archivo descargable, nunca `scripts/` de un checkout implícito.

Secuencia de usuario: instalar el extra documentado → descargar el paquete de ejemplo → abrir
notebook → verificar/obtener datos autorizados → declarar target y partición → ejecutar → leer
resúmenes → exportar configuración/informe. La descarga requiere conectividad; una copia con hash
válido permite repetir sin red. Ninguna celda pide credenciales ni acepta términos por el usuario.
La comparación bayesrisk no hace `choose()` automáticamente; una frontera no es una elección.

## 5. Configuración (schema Pydantic)

Inventario efectivo guiado de 2.16.0; no confundir defaults de una clase suelta con la receta F1.
La configuración completa y hashes por corrida se conservan como evidencia.

| Etapa | Defaults efectivos / diferencias relevantes |
|---|---|
| Semilla/partición | 20240706; aleatoria 0,8/0,2/0 sin estratificar; mínimo 30 malos por muestra. La clase raíz sola usa 42. La identidad del split depende del índice pandas, no sólo de la columna id |
| Binning | 6 bins, mínimo 5%, 20 prebins, `auto_asc_desc`, MIP/BOP, 10 s, óptimo requerido; variable no binneable puede omitirse; categoría rara 1%. Clase sola: 8 bins/100 s |
| Selección | IV ≥0,02; IV >0,50 marca; Pearson 0,75; VIF 5 con intercepto; prioridad IV/AUC/KS/nombre. Estabilidad apagada en F1, `report_only` en clase sola |
| Modelo | Statsmodels Newton, 100 iteraciones, tolerancia 1e−8; stepwise Wald bidireccional p=0,05. Signo/contribución >90% marcan en F1; clase sola excluye; no forzar signo invertido |
| Calibración | Offset de intercepto a tasa observada de Desarrollo; sólo Desarrollo, mínimo 30, tolerancia 1e−12 |
| Desempeño/estabilidad | PD calibrada, 10 deciles; mínimo 30 filas y 1 evento. PSI 10 bins, cortes 0,10/0,25, suavizado 1e−6; CSI sobre puntos |
| Validación | HL 10 grupos, mínimo 30 por grupo, alpha 0,05; contraste binomial por grado apagado en F1, encendido en clase sola |

La puerta guiada añade `master_scale={}`. Ninguna de estas diferencias se corrige por simetría.
Se propone **cero cambios** de defaults y cero campos nuevos. Las tres ablaciones usan opciones
existentes: `stepwise=False`, `max_bins=5`, `monotonic='auto'`; no son nuevos presets recomendados.
YAML/UI siguen contratos actuales; B exige round-trip y equivalencia medidos sin ocultar overrides.

## 6. Contratos de datos (I/O)

Cada caso publica manifiesto con fuente/fecha/licencia/atribución, huella del archivo y frame,
unidad de observación, predictores permitidos, target/orientación, exclusiones, índices originales,
particiones, semilla, versiones/lock, receta, config hash, métricas, advertencias y errores.
El estado es `ejecutado`, `falló` o `pendiente`, siempre con razón: ausencia no equivale a PASS.

| Caso | Universo | Desarrollo | Holdout interno | Evaluación final |
|---|---:|---:|---:|---:|
| German | 1.000 | 601 | 149 | 250 (75 malos), exterior |
| Taiwan | 30.000 | 17.962 | 4.538 | 7.500 (1.659 malos), exterior |
| Consumo sintético | 6.000 | 3.961 | 1.031 | 1.008 (239 malos), OOT 2024Q2 |
| Drift sintético | 6.000 | 3.955 | 1.000 | 1.045 (507 malos), OOT 2024Q2 |

German/Taiwan separan primero 25% estratificado con seed 20261016, conservan orden e índices y
entregan sólo el 75% a la puerta guiada. Esta genera Desarrollo/Holdout con su seed de fábrica.
Los referentes reciben exactamente Desarrollo y evaluación final de bayesrisk; no aprovechan
el Holdout para entrenar más. Los sintéticos usan su cohorte real del generador, no fechas
inventadas; OOT entra en el Study para diagnóstico, nunca en fit con esta receta.

Invariantes: IDs únicos por fila; Desarrollo/Holdout/evaluación disjuntos; unión exhaustiva;
target fuera de predictores; mismo orden/IDs/etiquetas entre recetas; todas las filas puntuadas;
ningún ajuste de bins, selección, coeficientes o calibración mira evaluación. IDs de fila no
prueban personas independientes: German carece de identificador de cliente verificable. Taiwan
aporta ID de origen pero no una historia longitudinal. No se promete eliminar toda dependencia
latente desconocida. Se revisan columnas temporales y disponibilidad a fecha de decisión al
incorporar cada corpus; especialmente recuperaciones/estado final de LC no pueden entrar como X.

Auditoría adicional de perfiles: German y ambos sintéticos tienen cero duplicados exactos de X;
Taiwan tiene 56 filas con X repetido (35 también con mismo target), con ID de origen único.
De las 7.500 filas exteriores, 17 comparten X exacto con Desarrollo. No se deduce que sean la
misma persona ni se afirma independencia completa. Sensibilidad sin refit, quitando esas 17
filas en **todas** las recetas: AUC fábrica 0,766784; sin stepwise 0,768032; OptBinning MIP
0,769121; scorecardpy 0,770945; skorecard MIP 0,769205. La conclusión no cambia.
La tabla principal conserva el universo predeclarado, no se sustituye por el resultado favorable.
Para B se predeclara una evaluación exterior sin solapamiento exacto de X. Agrupar predictores
admisibles (sin target ni ID), aplicar `GroupShuffleSplit(test_size=0.25, random_state=20261016)`
y conservar índices/orden originales: es 25% de **grupos**, no necesariamente filas. Sólo el
complemento entra a `Scorecard(partition='random')`, que conserva su Holdout/semilla de fábrica.
Así las tres puertas siguen usando el mismo config existente, sin parámetro nuevo. El Holdout
interior conserva carácter diagnóstico; se censan sus repetidos y no se usa para ajustar/elegir.
Antes de fit se requieren ≥30 malos y ≥1 bueno en Desarrollo, Holdout y test; si no, caso no
evaluable, sin búsqueda de semillas. Entidades realmente identificables se agrupan también:
grupos conexos por misma entidad o X exacto; en estas fuentes sólo se acredita el proxy X.
Esto no prueba independencia por cliente. Se publican tamaños y ambas fracciones efectivas.
Las estimaciones puntuales siguen por fila; la incertidumbre de B remuestrea grupos completos
del test con reemplazo (tantos como grupos originales, 1.000 réplicas, seed20261016), pareados
entre recetas; si alguna réplica carece de ambas clases, no se publica intervalo y se registra
el número inválido. No se usa el bootstrap por filas histórico de S52 como confirmación de B.

Salidas públicas: notebook mínimo y anexo ejecutable, config, manifest, lock, tabla de recetas,
fallos/dependencias, CSV/JSON de métricas y resúmenes HTML/Word/Excel. Predicciones fila a fila sólo
cuando la licencia lo permita. Los artefactos no contienen rutas personales ni datos institucionales.

## 7. Algoritmos, resultados y flujo

1. Verificar permiso y huella; fallar ante cambios de bytes/esquema, no adaptar silenciosamente.
2. Validar esquema, target, IDs y elegibilidad temporal; congelar particiones antes de modelar.
3. Ejecutar receta declarada sólo sobre Desarrollo; registrar convergencia y variables omitidas.
4. Aplicar sin refit y evaluar una vez por receta predeclarada; conservar predicciones y avisos.
5. Separar inferencias exploratorias de confirmatorias; publicar también resultados desfavorables.
6. Reconciliar métricas con artefactos y cobertura; publicar únicamente lo realmente ejecutado.

### 7.1 Línea base bayesrisk publicada

| Caso | AUC | Gini | KS | Brier | Log-loss | Tasa observada / PD media | PSI común |
|---|---:|---:|---:|---:|---:|---|---:|
| German | 0,747010 | 0,494019 | 0,411429 | 0,186348 | 0,561750 | 0,300000 / 0,295417 | 0,060494 |
| Taiwan | 0,766368 | 0,532736 | 0,413839 | 0,136761 | 0,436726 | 0,221200 / 0,225040 | 0,001736 |
| Consumo | 0,656096 | 0,312192 | 0,251906 | 0,171278 | 0,523386 | 0,237103 / 0,233378 | 0,006465 |
| Drift | 0,712032 | 0,424063 | 0,319651 | 0,215824 | 0,620205 | 0,485167 / 0,490611 | 0,741140 |

Variables finales: 10/9/5/5; suma de bins del resumen de **todos los predictores binneados**:
69/98/32/33, no confundir con filas de tarjeta final. Todas las variables de las cuatro bases
tuvieron estado de solver OPTIMAL; no se justifica aumentar el límite de 10 s por intuición.

German: HL del Holdout no evaluable por tamaño de grupos; no bajar el mínimo para obtener verde.
Taiwan: HL Desarrollo p≈0,021 y Holdout p≈0,0804; ajustar la media no garantiza calibración por
grupos. Drift: la alerta de estabilidad es la evidencia buscada, no un defecto del umbral.

### 7.2 Ablaciones predeclaradas

| Caso | AUC fábrica | Sin stepwise (variables) | 5 bins (variables) | Monotonía auto (variables) |
|---|---:|---:|---:|---:|
| German | 0,747010 (10) | 0,759771 (13) | 0,745714 (10) | 0,747086 (11) |
| Taiwan | 0,766368 (9) | 0,767618 (14) | 0,766718 (9) | 0,765367 (11) |
| Consumo | 0,656096 (5) | 0,656096 (5) | 0,653680 (5) | 0,656096 (5) |
| Drift | 0,712032 (5) | 0,712032 (5) | 0,709746 (5) | 0,711989 (5) |

German sin stepwise: ΔAUC +0,012762, IC bootstrap [0,004038; 0,022484], Brier 0,180694 frente a
0,186348. Taiwan: +0,001250, IC [−0,000043; 0,002520], Brier 0,136688 frente a 0,136761.
La señal German merece confirmación; no se la descarta porque contradiga una preferencia.
Pero un split exploratorio, con mayor complejidad y sin estimar variación de entrenamiento, no
justifica imponer el cambio universal. Confirmación futura requiere protocolo previo sobre
nuevas particiones/carteras y corrección de multiplicidad; no seguir optimizando este test.
`auto` empeora log-loss German (0,578634) y AUC Taiwan; cinco bins empeora ambos sintéticos.

### 7.3 Referentes: comparabilidad explícita, no recetas idénticas

| Caso | bayesrisk fábrica | OptBinning MIP | scorecardpy | skorecard MIP |
|---|---:|---:|---:|---:|
| German | 0,747010 | 0,741257 | 0,729371 | 0,741562 |
| Taiwan | 0,766368 | 0,768837 | 0,770605 | 0,768920 |
| Consumo | 0,656096 | 0,657426 | 0,641008 | 0,657355 |
| Drift | 0,712032 | 0,711423 | 0,698685 | 0,711507 |

Tabla: AUC de evaluación final común. Los referentes usan logística sklearn sin penalización,
lbfgs, máximo 1.000 iteraciones; sin selección ni calibración posterior. OptBinning usa 6 bins,
5%, auto_asc_desc y MIP. scorecardpy usa `woebin` tree de fábrica con 1 core, sin `var_filter`.
skorecard MIP usa prebins árbol (100) / ordinal (1%), binning óptimo 6 bins/5% con MIP.
Los predictores de entrada son los mismos; selección y estimadores internos difieren. Es una
comparación de pipelines declarados, no una atribución causal de ventaja a la biblioteca.

Experiencia sin ajuste de compatibilidad: scorecardpy no importó con setuptools 84
(`pkg_resources`); 80.9.0 lo hizo ejecutable. El solver CP de OptBinning falló con OR-Tools
9.14 en Taiwan/consumo y el bucketing automático de skorecard en German/Taiwan. Se conservan
esos fallos; el MIP posterior se rotula configurado. German OptBinning CP sí corrió. No se
ejecutó una matriz completa de fábrica CP en los cuatro casos ni se afirma que los fallos sean
universales. El entorno común exige NumPy 1.26.4 por skorecard y pyarrow 20 compatible.

No hay ganador general. Las métricas restantes y cardinalidades de tarjetas están en las
salidas de S52 y serán obligatorias en el anexo público de B, también cuando perjudiquen a
bayesrisk. Tiempos de las 16 corridas bayesrisk con informes: 6,03–20,37 s; bases
10,90/18,43/8,55/8,75 s. Referentes configurados: aproximadamente 1,02–8,58 s. Costes de
informes/imports y concurrencia incidental distintos impiden inferir velocidad relativa.

| Caso / referente configurado | X de entrada | Filas de tarjeta | Brier | Log-loss | PSI común | Segundos |
|---|---:|---:|---:|---:|---:|---:|
| German / OptBinning MIP | 20 | 108 | 0,187598 | 0,571467 | 0,051938 | 1,43 |
| German / scorecardpy | 20 | 70 | 0,193441 | 0,605044 | 0,027336 | 7,53 |
| German / skorecard MIP | 20 | 109 | 0,187652 | 0,572048 | 0,053506 | 2,40 |
| Taiwan / OptBinning MIP | 23 | 142 | 0,136276 | 0,435233 | 0,001598 | 1,93 |
| Taiwan / scorecardpy | 23 | 96 | 0,136224 | 0,434845 | 0,002579 | 8,58 |
| Taiwan / skorecard MIP | 23 | 143 | 0,136279 | 0,435237 | 0,001846 | 7,73 |
| Consumo / OptBinning MIP | 6 | 44 | 0,171168 | 0,522972 | 0,007418 | 1,31 |
| Consumo / scorecardpy | 6 | 28 | 0,172492 | 0,528053 | 0,005967 | 3,20 |
| Consumo / skorecard MIP | 6 | 45 | 0,171143 | 0,522880 | 0,005261 | 1,02 |
| Drift / OptBinning MIP | 6 | 45 | 0,215998 | 0,620612 | 0,744542 | 1,35 |
| Drift / scorecardpy | 6 | 26 | 0,219441 | 0,628087 | 0,741749 | 3,31 |
| Drift / skorecard MIP | 6 | 46 | 0,216002 | 0,620629 | 0,743055 | 1,60 |

Las filas de tarjeta incluyen las convenciones propias de cada biblioteca (missing/special y,
según formato, intercepto); no son el mismo denominador que bins del resumen bayesrisk.

### 7.4 Comparison y artefactos

Se ejecutaron dos Comparison (German/Taiwan, cuatro variantes cada uno), con resumen texto/HTML,
informe HTML/Word y Excel. Comparan **Holdout interno de 149/4.538 filas**, no el test exterior
de las tablas anteriores. DeLong: seis pares, sin corrección de multiplicidad; frontera sin
elección registrada. Se preservan 12 archivos finales y sus hashes. No mezclar sus p-valores,
fronteras ni PSI nativo con el bootstrap y PSI común exterior.

Verificación de contenido: 12/12 hashes, 651 celdas Excel, 593 celdas HTML y 593 Word contra
Study, sin discrepancias; alterar AUC en memoria hizo fallar el cotejo. Los resúmenes TXT/HTML
aislados no nombran Holdout: deben acompañarse de este rótulo de contexto. Los cuerpos de los
informes, cards y Excel sí lo identifican. Los gráficos y tablas de ambos HTML se inspeccionaron
renderizados en navegador; capturas conservadas. Word se verificó por contenido/estructura e
imágenes embebidas, sin certificación visual de paginación. Sus campos institucionales vacíos
son intencionales: no inventar entidad, responsable ni aprobación para un experimento.

## 8. Casos borde y manejo de errores

Dos defectos reproducidos en el paquete publicado, no introducidos por H10:

1. **Dtype inferido incompatible:** `int32`, `float32`, `uint64`, `Int32` pueden reducirse a
   schema int/float mientras `coerce=False` exige int64/float64. Int64/int64/float64 sí pasan.
   La corrección debe preservar valores, nulabilidad y rango; no se acepta activar coerción
   indiscriminada. Tests deben cubrir límites uint64, nulos y rechazo explícito de conversiones
   con pérdida. Es un defecto de inferencia/validación, no evidencia para cambiar selección.
2. **Target con nombre original `target`:** la guiada genera `target_bayesrisk`; el modelo emite
   PD con ese nombre mientras scorecard exige `target` canónico. También afecta target_col
   personalizado en ruta completa. La precisión aprobada en §8.1 corrige la frontera de consumo
   sin cambiar los artefactos válidos de model ni el archivo del usuario. Controlar colisiones
   con columna preexistente y coherencia de labels/índices, manteniendo el target de entrada.

S52 pudo medir renombrando explícitamente target a `malo` y fijando int64 en sus scripts; es una
adaptación documentada de investigación, no un arreglo distribuido. Se conservan logs fallidos.

### 8.1 Precisión de D-H10-3 aprobada por Cami (S53, 2026-10-16)

La medición encontró una discrepancia entre el nombre canónico descrito en SDD-08 y el contrato
efectivo: model publica el nombre derivado de `data.labels.target_col`. Una calibración con
`target_column=objetivo` ya funciona; renombrar su artefacto a `target` la rompe. Un alias tampoco
preserva el caso válido que llama `target` a la salida calibrada. La precisión siguiente recibió
revisión independiente sin materiales y aprobación interactiva antes de implementarse:

- Model conserva sus artefactos, nombres, valores, índices y dtypes. No añade aliases ni claves.
- Scorecard proyecta una copia a `target` sólo si falta el canónico y `data.labels.target_col`
  identifica una columna presente. Sin esa procedencia no adivina y mantiene el error explícito.
- Calibración conserva una entrada que ya trae su `target_column` declarado. Sólo proyecta con
  la misma regla cuando pide el default literal `target` y éste falta. Una columna personalizada
  inexistente sigue siendo un error. La regla también se aplica fuera del ajuste (TTD).
- `data.labels` es una dependencia opcional de ambos consumidores: una entrada inyectada ya
  canónica sigue funcionando sin ella. ML conserva su consumo del nombre derivado.
- Se rechaza `target_col=label_status` antes de sobrescribir etiquetas con estados, y
  `target_col=pd_raw` o `linear_predictor` antes de sobrescribirlas con predicciones. La colisión
  con una columna preexistente del input sigue siendo un error. No se renombra la fuente.
- Los tipos lógicos numéricos sin coerción conservan el dtype físico compatible; los controles
  de nulos, rango, unicidad e índice siguen vigentes. Una coerción numérica declarada que desborda
  o redondea valores se rechaza explícitamente.

Los casos canónicos y personalizados válidos deben conservar su proyección canónica y
`config_hash`. Esta precisión no cambia metodología, defaults ni perillas, ni autoriza B.

Otros límites: una clase sola, ausencia de eventos, IDs duplicados, predicción no finita o
no puntuada, solver no óptimo, esquema cambiado o licencia pendiente deben detener la receta
o declararla no ejecutada con razón. `done` no basta: revisar `skipped_reason` de binning.
La estabilidad usada como `exclude` en selección consulta HO/OOT según contrato existente:
está prohibida en estos benchmarks; si se usa, esas muestras son de desarrollo y se requiere
otra evaluación intacta. También cuenta el ajuste humano repetido mirando el test.

## 9. Reproducibilidad y auditoría

Evidencia privada S52: protocolo previo, censo, fuentes HTTP con UTC/status/URL final/hash,
scripts `medir`, `referentes`, `consolidar`, `controles`; manifiestos, configs/particiones,
predicciones de evaluación y Desarrollo, coeficientes/calibración, fallos y artefactos.
No es todavía el paquete público de B ni debe enlazarse desde docs públicas al repo privado.

Python 3.12.10 Windows; bayesrisk 2.16.0, scorecardpy 0.1.9.7, skorecard 1.6.9,
OptBinning 0.20.0, sklearn 1.7.2, pandas 2.3.3, NumPy 1.26.4, OR-Tools 9.14.6206;
lock completo conservado. Primeras corridas sin PYTHONHASHSEED fijado: se declara la limitación.
El entorno inicial heredaba paquetes globales: Word utilizó python-docx 1.2.0 y lxml 6.1.1,
omitidos del primer freeze. Hallazgo de revisión 1 corregido en el lock. Un segundo entorno,
sin paquetes heredados y fuera del checkout, instaló ese lock y regeneró Word de un scorecard
y ambas comparaciones desde estudios guardados: XML del documento y 10 imágenes exactamente
iguales a los originales, sin refit. La herencia inicial se conserva como limitación histórica,
no se presenta retroactivamente como instalación limpia.
Repetición German con PYTHONHASHSEED=0 y permutación exclusiva de etiquetas Holdout produjo
exactamente mismas variables, bins, coeficientes, calibración y predicciones exteriores.
No se extrapola ese resultado bit a bit a las otras tres carteras.

B fija hash seed/threads/entorno y verifica dos ejecuciones independientes. Preserva índices
originales antes de split; cambiar índice cambia partición aunque no cambien valores.
Los tiempos comparativos futuros se miden secuencialmente, mismo hardware/threads, calentamiento
separado, tres repeticiones y mediana/rango. Tiempo de ajuste/aplicación separado de informe.
No se usa el tiempo S52 como gate de superioridad.

## 10. Dependencias

Runtime por código: extras existentes `scoring,report,excel,docx`; pantalla: extra `ui`, que ya
compone esos extras y su servidor. No se crea un extra nuevo.
Entorno de benchmark separado con versiones exactas y artefactos resolubles; no contaminar
dependencias core para acomodar un referente. R sólo en C, nunca dependencia core.
Licencias de bibliotecas: bayesrisk/OptBinning Apache-2.0; scorecardpy/skorecard MIT;
sklearn BSD-3-Clause. La licencia de software no autoriza redistribuir sus datasets de ejemplo.
Fuentes: [scorecardpy oficial](https://github.com/ShichenXie/scorecardpy),
[skorecard oficial](https://github.com/ing-bank/skorecard),
[OptBinning oficial](https://github.com/guillermo-navas-palencia/optbinning).
Las recetas se verifican contra versiones instaladas; documentación upstream actual puede diferir.

## 11. Estrategia de tests, gates y controles negativos

| Gate | Oráculo / control negativo |
|---|---|
| Cobertura | Set de notebooks/datasets/recetas publicadas = set esperado, ambos sentidos; retirar una entrada y añadir otra inexistente debe fallar |
| Fuente | SHA/columnas/target/licencia concuerdan con manifiesto aprobado; cambiar byte, orientación o permiso debe bloquear, no descargar un sustituto |
| Particiones | Disjunción, unicidad, exhaustividad y mismo orden por receta; insertar ID del test en train debe fallar |
| Dependencia de filas | Censar X duplicados y entidades; B mantiene cada grupo a un lado de la frontera exterior; separar un miembro entre input y test debe fallar |
| Aislamiento | Permutar labels sólo HO no altera bins/selección/coeficientes/calibración; controles de instrumentación verifican fit sólo Desarrollo |
| Métricas | Casos manuales AUC=1/0, Gini=1/−1, Brier=0, PSI=0; invertir PD o desalinear IDs debe detectar error; no gate «AUC supera al competidor» |
| Fallos | Forzar solver no óptimo/timeout/import fallido deja fila fallida y cobertura incompleta; nunca omitir receta del denominador |
| Artefactos | CSV/JSON, HTML/Word/Excel y tablas del Study reconciliados; cambiar celda/frontera/partición debe fallar; inspección renderizada de layout |
| Instalación | Wheel publicado/candidato + descarga autocontenida, fuera del repo; retirar auxiliar requerido debe nacer rojo |
| Defectos A | Dtypes/targets válidos nacen rojos en 2.16.0 y verdes con fix; rechazos de pérdida/collision y regresión de casos válidos |

S52 ejecutó rojo/restauración exacta/verde para fuga de particiones y censo en ambos sentidos,
y la perturbación Holdout. Los demás controles son requisitos de las capas, no se declaran
ejecutados ahora. La revisión independiente de diseño tiene tope de tres pasadas y parada ante
approve o ausencia de hallazgos materiales; residual material se eleva.

Presupuesto propuesto B: main ejecuta ejemplo mínimo/censo/invariantes locales sin red; job H10
de release ejecuta German/Taiwan y sintéticos contra versiones fijadas, timeout 20 min y máximo
2 procesos de pruebas, fits comparativos secuenciales. Datos autorizados cacheados por hash;
cache miss requiere descarga verificable, no convertir red caída en verde. Cuentas LC/HC no
entran como secretos obligatorios del CI público. El reporte siempre publica cobertura parcial.
20 min es un límite operativo propuesto, no medición de Linux; se valida en el primer CI B,
con desglose, antes de declararlo suficiente. Si no cabe, se mide y revisa; no se recorta cobertura.
Cada release reejecuta todas las recetas **admitidas**; no exige ejecutar fuentes todavía pendientes.
Eso no cierra C6 hasta completar corpus/referentes acordados o aprobar explícitamente otro alcance.

## 12. Decisiones aprobadas y riesgos

Las seis decisiones siguientes fueron aprobadas por Cami el 2026-10-16, mediante tres respuestas
interactivas. Las recomendaciones quedan adoptadas con su alcance explícito:

| Decisión | Recomendación aprobada / coste y beneficio |
|---|---|
| D-H10-1 | Aprobar protocolo y capas A→B→C→D; primera entrega parcial explícita. Permite entregar evidencia útil sin fingir cobertura completa |
| D-H10-2 | Conservar todos los defaults. German sin stepwise queda hipótesis de confirmación futura, no nuevo preset. Mantiene estabilidad; no captura todavía la mejora local observada |
| D-H10-3 | Priorizar fixes de dtypes/target en A bajo contratos existentes, con preservación de valores y casos válidos. Elimina fallos alcanzables desde pip antes de documentarlos como experiencia normal |
| D-H10-4 | Admitir Taiwan como suplemento; mantener LC/HC/PAKDD pendientes hasta permisos/datos verificables. No publicar la copia local LC. Menor cobertura inicial, trazabilidad honesta |
| D-H10-5 | Aprobar entrega autocontenida/CI y cero perillas de §§4/11/13; R se conserva en C. Su implementación B requiere gates completos y revisión propia |
| D-H10-6 | S53 autorizada únicamente para A; B después del cierre revisado de A. No autoriza release ni recaptura |

Una propuesta posterior de defaults exige nueva evidencia y OK: cambio config_hash/goldens,
impacto en SemVer, notebooks, pantalla, informes, equivalencia de tres puertas y eventual
recaptura autorizada por separado. No cabe introducirla como «ajuste menor» de A o B.
Incertidumbres restantes: corpus histórico, independencia de personas no demostrable en German,
variación de entrenamiento no estimada, compatibilidad futura de terceros, cobertura de fuentes
restringidas y reproducibilidad cross-platform aún no medida.

## 13. Simplicidad (SDD-31)

Entrada mínima del modelador: datos y target; ID/cohorte cuando existan y la separación temporal
institucional cuando corresponda. El ejemplo fija y declara fuente, semilla y split; no pide al
usuario elegir solver, deciles, alpha, suavizado, threads, estimador o tolerancias para empezar.
El investigador ve recetas explícitas en el anexo, no perillas nuevas en la pantalla del banco.

Presupuesto: **0 hojas nuevas**, 0 secciones nuevas, 0 overrides nuevos del motor. Esenciales
siguen con máximo 6 por sección; los controles existentes avanzados no se duplican. Config
exportada es la misma usada por guiada/pantalla, sin defaults ocultos propios del notebook.

Resumen por etapa conserva los existentes: calidad de datos y partición; bins y variables
omitidas; selección/coeficientes; calibración; discriminación/estabilidad; validación/informe.
Las decisiones humanas son corregir datos, revisar supuestos y registrar elección de modelo;
ningún semáforo habilita cambiar metodología automáticamente. El anexo añade una tabla legible
de cobertura/receta/error, con razón verificable de cada pendiente.

| Cifra SDD-31 | Antes medido | Objetivo después |
|---|---|---|
| Líneas de usuario | 15 mínimo guiado; 22 notebook versionado | ≤25 mínimo; anexo contado aparte |
| Esenciales | 37 marcas en 13 secciones; máximo 6 | Sin aumento, máximo 6 |
| Controles visibles | 36 atómicos esenciales; 208 atómicos en 12 bloques Avanzado; catálogo total 414 nodos | Sin aumento ni confundir nodos con controles simultáneos |
| Primer resumen | Proxy run_start→data_card: German 0,333341 s, consumo 0,309271 s; no incluye constructor ni render/echo | B medirá desde llamada de usuario hasta resumen visible; sin regresión contra base en el mismo entorno |
| Conceptos mínimos | 5 | ≤5 |

Las 37 marcas esenciales y 36 controles atómicos usan denominadores distintos: el selector de
partición representa ramas con varias marcas. La cifra temporal disponible es un proxy
explícito, no una medición de latencia visible. El temporizador iniciado antes del constructor y
terminado después de informes/predicciones da cotas conservadoras del primer resumen:
German <10,903 s, consumo <8,555 s (los logs contienen el resumen), ambas inferiores a 30 s.
B debe medir la latencia exacta sin confundirla con tiempo total.
El anexo técnico no se disfraza de notebook mínimo para ocultar su complejidad: se miden ambos
y se publica su diferencia. B cierra las cifras precisas de las tres puertas antes de afirmar entrega.

## 14. Implementación B — S54

La implementación conserva el alcance aprobado: German, Taiwan suplementario y dos sintéticos,
cuatro recetas bayesrisk y tres referentes, 28 combinaciones explícitas. La entrega descargable
incluye fuentes autorizadas, auxiliares, locks, notebooks ejecutados, tablas completas, informes,
predicciones, manifiestos y controles. La evidencia comparativa local usa el wheel candidato de
S53, fuera del checkout, con calentamiento y tres repeticiones secuenciales; la cobertura de Linux
se exige al candidato nuevo en CI antes de acreditar su promoción. No hay cambios al motor.

Las cifras y límites medidos, incluida la latencia visible de cada puerta y sus fluctuaciones,
están en la [página pública del benchmark](../../docs_site/benchmarks/h10/README.md). El mínimo
tiene 15 líneas útiles y cinco conceptos; el anexo se cuenta aparte. Las tablas anchas de los Word
del benchmark se presentan en páginas apaisadas mediante un auxiliar local, conservando sus
textos y celdas; no se cambia el renderer del paquete.

La primera publicación y los cambios de esta entrega frente a producción requieren CI completo
del mismo SHA antes del deploy; main conserva el CI mínimo. Los recibos de revisión, ejecución
Linux y publicación acreditan el cierre operativo, conforme al runbook. La entrega parcial no
completa H10 ni C6, no selecciona recetas automáticamente y no autoriza C/D, release ni recaptura.
