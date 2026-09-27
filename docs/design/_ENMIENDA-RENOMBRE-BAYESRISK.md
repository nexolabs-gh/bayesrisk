# Enmienda RENOMBRE-BAYESRISK — la librería pasa a llamarse `bayesrisk` (D-REN-1…12)

> **Estado: APROBADA por Cami el 2026-09-27** (interactivamente, al cierre de S22): su prompt del
> renombre **es** la aprobación del diseño, con las precisiones del writer que este documento
> fija. Sustituye la opción C del 2026-09-03 (rebranding sólo de superficie). Revisión adversarial
> de Codex: tope de **dos pasadas** sobre este documento (§11). Todo lo irreversible —publicar en
> PyPI, activar redirecciones, renombrar el repositorio, tocar `www.nikodym.cl`— espera el **STOP
> de A7** y un OK nuevo de Cami. El detalle operativo y el estado viven en el `HANDOFF` privado.

## 0. Qué decidió Cami y qué fija el writer

**Cami (2026-09-27):** la consultora pasa a llamarse **Bayes Advisory** (dominios
`bayesadvisory.cl`, en Vercel); la librería se renombra a **`bayesrisk`**; **`nikodym`** queda como
capa de compatibilidad **congelada** —no se mantienen dos librerías: todo desarrollo nuevo va sólo
en `bayesrisk`—; permisos completos sobre el arnés H9R para lo que el renombre exija; el orden lo
fija el writer; la cuenta de PyPI se verifica en la sesión. Durante S23 añadió: los publicadores
los registra el writer en su Chrome, crea ella la cuenta de TestPyPI, el checkout se mueve a una
carpeta propia `Proyectos\bayesrisk`, y **`www.nikodym.cl` ya redirige (308) a
`riesgo.bayesadvisory.cl`** conservando ruta y query —lo hizo ella; sale de la propuesta (b) de A7—.

**El writer fija** (precisiones que el prompt no resolvía, medidas en §2): los nombres de clase con
la marca (D-REN-3), las identidades de hash congeladas (D-REN-4), la equivalencia del lock para los
bundles (D-REN-6 b), las variables de entorno (D-REN-8) y la frontera de los documentos (D-REN-11).

## 1. Propósito

Que un modelador que hoy escribe `import nikodym` pase a `import bayesrisk` cambiando **esa sola
línea**, con los mismos números bit a bit, y que todo lo que ya guardó con nikodym ≤ 1.20 siga
cargando con `bayesrisk` más `nikodym` 1.21. «Equivalente funcional a nikodym 1.20.0» es una
afirmación medible (§5), no un eslogan.

## 2. Inventario medido (A2, 2026-09-27, sobre `315ccd4`)

- **11.696** apariciones de «nikodym» (8.683 minúscula, 2.900 capitalizada, 113 mayúscula) en
  **747** archivos de texto versionados; ningún binario. **3.250** líneas de import.
- Por área: `tests/unit` 4.403 · `src/nikodym` 3.176 (253 archivos) · `docs/design` 1.879 (79) ·
  RUNBOOK 527 · `docs_site` 435 · `web/src` 292 · arnés H9R 156 · CHANGELOG 91 · workflows 80.
- **Clases con la marca**: `NikodymConfig` (1.499), `NikodymBaseConfig` (482), `NikodymError`
  (334), `BaseNikodymEstimator` (92), `NikodymClassifier` (57), `NikodymTransformer` (29),
  `NikodymValidationError` (4). Públicas en la documentación: sólo `NikodymConfig` (40 en
  `docs_site`, 5 en README, 6 en el cuaderno, 10 en `web/src`).
- **Variables de entorno**: la librería **no lee ninguna `NIKODYM_*` en tiempo de ejecución**. Las
  que existen son de herramientas: `NIKODYM_DEMO_OUT_DIR` y `NIKODYM_UI_URL` (build de la demo y
  e2e), `NIKODYM_SMOKE_PRESET` (smoke), `NIKODYM_DEMO_FIXTURE_ONLY` (marca de archivo de la demo),
  23 `NIKODYM_H9R_*`/`NIKODYM_S3_*` del arnés, y el marcador de plantilla `__NIKODYM_TOKEN__`.
- **Persistido con el nombre**: joblib de `Study.save` (39 artefactos con clases `nikodym.*` en la
  corrida F1), `library_versions.nikodym` del lineage, `nikodym_version` del lineage de
  `apply` y de `SerializationMixin.save`, tags de MLflow `nikodym.*` (inventario e idempotencia por
  `nikodym.config_hash`), el valor de config `report.theme: "nikodym"`, los defaults
  `name="nikodym-study"`, `governance.model_name="nikodym-model"`, `run_dir="nikodym-runs"` de la
  puerta guiada y `workdir=".nikodym_ui"` de la pantalla.
- **Identidades de hash que llevan la palabra** (§D-REN-4): la personalización BLAKE2b de la
  partición, el prefijo de `data_hash`, dos separadores de `forward`, el de la distribución
  instalada y la sal de los SVG.
- **El bundle público del scorecard** (`FittedScorecardBundle`, JSON + parquet, sin pickle) exige
  al cargar que el hash de `uv.lock` embebido sea el del bundle; renombrar el proyecto cambia
  `name = "nikodym"` en `uv.lock`, así que sin D-REN-6 b **todo bundle de nikodym ≤ 1.20 dejaría de
  cargar**.
- **Dominios**: `docs.nikodym.cl` y `demo.nikodym.cl` son los proyectos Vercel `nikodym-docs` y
  `nikodym-demo` (equipo NexoLabs Projects), publicados por `deploy.yml` con la CLI; el proyecto
  `nikodym-advisory` sirve `riesgo.bayesadvisory.cl` y redirige `nikodym.cl`/`www.nikodym.cl`.
- **Línea base de la equivalencia** (`privado/evidencia/s23/linea-base-antes-*.json`): preset F1
  `1063d6cf…` (AUC OOT 0,656 · Gini 0,312 · KS 0,252 · caída −0,056 · PSI 0,0132) y el YAML SBA de
  Cami `08cf3076…` (0,786 · 0,573 · 0,485 · −0,080 · 0,1612 «Revisar»).

## 3. Decisiones

### D-REN-1 — Dos distribuciones, una librería

- **`bayesrisk` 2.0.0** es la librería: el paquete `src/nikodym` pasa a `src/bayesrisk` sin tocar
  una línea de lógica, y la distribución, el `project.name`, `[tool.hatch.*]`, mypy, ruff, pytest,
  coverage y `uv.lock` pasan a `bayesrisk`. Parte **exactamente** de nikodym 1.20.0 (`main` =
  `v1.20.0`, medido en A0: nada sin publicar).
- **`nikodym` 1.21.0** es la capa de compatibilidad y **su último release**: vive en
  `compat/nikodym/` con su propio `pyproject.toml`, fuera del proyecto uv (no entra a `uv.lock`),
  depende de `bayesrisk>=2.0,<3` y no copia código de la librería (D-REN-7).
- Mayor 2.0 por el cambio de nombre de la distribución; **ninguna API cambia de comportamiento**.

### D-REN-2 — Nombres públicos

`import bayesrisk`, `from bayesrisk.scorecard import …`, `bayesrisk.run`, `bayesrisk.Scorecard`.
Console script **`bayesrisk-ui`** y `python -m bayesrisk.ui`. `nikodym-ui` sigue existiendo, pero
lo instala la distribución `nikodym` 1.21 y apunta a `bayesrisk.ui.__main__:main`. Sin extra
nuevos: los de `bayesrisk` son los de nikodym 1.20.0, con el mismo nombre.

### D-REN-3 — Clases con la marca: nombre nuevo y alias silencioso

`NikodymConfig` → **`BayesRiskConfig`**, `NikodymBaseConfig` → `BayesRiskBaseConfig`,
`NikodymError` → `BayesRiskError`, `NikodymValidationError` → `BayesRiskValidationError`,
`BaseNikodymEstimator` → `BaseBayesRiskEstimator`, `NikodymClassifier` → `BayesRiskClassifier`,
`NikodymTransformer` → `BayesRiskTransformer`. En el mismo módulo que define cada clase queda el
**nombre anterior como alias** (`NikodymConfig = BayesRiskConfig`: el mismo objeto), exportado donde
se exportaba —también en el `__all__` de los cinco módulos que lo listaban en 1.20, para que un
`from nikodym.core import *` siga definiéndolo (pasada 2 de Codex sobre el código)—, **sin aviso**. Razones: con el alias, `import bayesrisk` es el único cambio que
necesita el código de un usuario (la «guía de una línea»), y un pickle que nombra
`nikodym.core.config.schema.NikodymConfig` resuelve a la clase nueva. Sin aviso porque el aviso
lo da ya `import nikodym`, y porque cargar un pickle viejo dispararía avisos que el usuario no
puede corregir. La documentación y los ejemplos usan sólo los nombres nuevos. Los alias se retiran
en 3.0, con su enmienda. Mayúsculas: `BayesRisk` (legible, y «Bayes risk» es el concepto de teoría
de la decisión que el nombre evoca).

### D-REN-4 — Identidades congeladas (NO se renombran)

Estas constantes llevan la palabra «nikodym» pero son **identidad de un cálculo**; cambiarlas
movería números o hashes publicados. Quedan literalmente como están, con un comentario que lo
dice, y un test las fija byte a byte con su control negativo:

| Constante | Archivo | Qué movería |
|---|---|---|
| `_HASH_PERSON = b"nikodym"` | `data/partition.py` | la asignación de cada fila a su partición → todos los números |
| `_SCHEMA_HEADER_PREFIX = "nikodym.data_hash.v1"` | `data/hashing.py` | `data_hash` de todo dato |
| `b"nikodym.forward.macro_hash.v1"` | `forward/macro.py` | el hash macro de forward-looking |
| `b"nikodym.forward.step.logical_frame.v1"` | `forward/step.py` | el hash del frame lógico de forward |
| `b"nikodym.installed-distribution.v1\0"` | `core/build.py` | separador de dominio de `installed_distribution_hash` |
| `"svg.hashsalt": "nikodym"` | `report/charts.py` | los `id` de cada SVG del informe |
| `"format": "nikodym.scorecard.bundle"` (escrito y exigido al cargar) | `scorecard/bundle.py` | todo bundle guardado dejaría de cargar antes de llegar al lock |
| `"format": "nikodym.scorecard.batch"` | `scorecard/bundle.py` | el manifiesto de cada aplicación batch |
| `b"nikodym.batch.input.v1\0"`, `b"nikodym.batch.output.v1\0"` | `scorecard/bundle.py` (y su espejo en `measure_readiness_w1.py`) | `input_hash`/`output_hash` del manifiesto batch |
| `b"nikodym.scorecard.input-row.v1\0"`, `b"nikodym.scorecard.treatment-trace.v1\0"` | `scorecard/bundle.py` | los hashes por fila y de la traza de `apply` |
| `"nikodym.report.ai.prompt.v1"` | `report/ai.py` | el `prompt_hash` guardado de la narración |
| `"nikodym.stress.forward_hash.v2"` | `stress/engine.py` | el hash de forward del stress |
| `nikodym.readiness.*`, `nikodym.h9r.*`, `nikodym.wheel-tree.v1`, `nikodym.wheel-metadata.v1` | arnés H9R y `measure_readiness_*` | la versión de esquema de la evidencia ya guardada |

**Y las identidades en registros externos (MLflow)**, por la misma razón: el prefijo de tags
`nikodym.*` (`nikodym.config_hash`, `nikodym.model_card_uri`, `nikodym.estado_validacion`…) y los
nombres por defecto `name="nikodym-study"` y `governance.model_name="nikodym-model"`. La
idempotencia del registro busca por `(model_name, config_hash)` restringida al nombre recibido
(`tracking/inventory.py`): cambiar el nombre por defecto o el prefijo crearía un segundo modelo
registrado para la misma corrida y separaría sus alias. Quien no declara un nombre sigue viendo
`nikodym-model` en su MLflow; renombrar esa identidad exige una migración explícita, que no es de
esta enmienda.

El censo que sostiene esta tabla es exhaustivo por construcción: todo literal `b"nikodym…"` y todo
`nikodym…vN` de `src/` y `scripts/` (búsqueda del 2026-09-27, tras la pasada 1 de Codex).

### D-REN-5 — Claves y valores persistidos que SÍ cambian (declarados uno por uno)

Son los únicos cambios de bytes admitidos fuera de la marca y el copy:

1. `lineage.library_versions`: la clave `"nikodym"` pasa a `"bayesrisk"` (lineage de cada
   corrida, `environment.json`, `fit_lineage` del bundle). La advertencia de deriva de versiones al
   cargar un `Study` lee `"nikodym"` como la versión anterior de la misma librería.
2. `nikodym_version` → `bayesrisk_version` en el lineage de `apply` y en el payload de
   `SerializationMixin.save`.
3. (Retirado tras la pasada 1 de Codex: los tags de MLflow y los nombres por defecto que los
   registros usan como identidad **no** cambian; ver D-REN-4.)
4. `report.theme`: el valor `"nikodym"` pasa a `"bayesrisk"`; el config sigue **aceptando**
   `"nikodym"` y lo lee como `"bayesrisk"` (un YAML viejo valida igual). `report` es sección de
   infraestructura: no entra al `config_hash`.
5. Carpetas por defecto: `run_dir="bayesrisk-runs"` en la puerta guiada y `workdir=".bayesrisk_ui"`
   en la pantalla. Ninguna entra al `config_hash`. Quien quiera seguir con su carpeta la declara
   (`run_dir="nikodym-runs"`, `--workdir .nikodym_ui`); el CHANGELOG lo dice. **No** se añade una
   búsqueda automática de la carpeta vieja: sería una regla oculta.
6. Rutas de módulo que ya viajan como dato: el `source` de los eventos del trail, el título del
   schema JSON (`BayesRiskConfig`), la clase CSS `nikodym-summary` → `bayesrisk-summary`.
7. Metadatos del paquete: el `_build_manifest.json` gana el campo aditivo
   `uv_lock_sha256_nikodym` (D-REN-6 b).
8. La clave del *front matter* del informe editable (`.qmd`) que agrupa modelo, entidad y los
   cuatro hashes de la corrida pasa de `nikodym:` a `bayesrisk:`. Es un entregable que cada corrida
   reescribe y que ninguna parte de la librería vuelve a leer (medido: sólo lo lee un test); los
   `.qmd` ya entregados no cambian.

### D-REN-6 — Lo que ya existe sigue cargando

a. **Pickle/joblib** (`Study.save`, artefactos, estimadores guardados con `joblib.dump`): cargan
   con `bayesrisk` + `nikodym` 1.21 porque `import nikodym.x.y` resuelve al módulo
   `bayesrisk.x.y` (D-REN-7) y los nombres de clase viejos existen como alias (D-REN-3). `Study.load`
   sigue verificando el `config_hash`: si el config de un estudio viejo diera otro hash con la
   librería nueva, la carga falla — es la prueba de que la identidad no se movió.
b. **Bundle público del scorecard.** La regla vigente (un bundle sólo se aplica con la misma fuente
   de dependencias) se conserva, y se le reconoce una sola equivalencia: la fuente de bayesrisk
   **con el proyecto vuelto a llamar «nikodym»** es la fuente con la que se construyó nikodym
   1.20.0. Reponer sólo el nombre no basta (pasada 2 de Codex): `uv.lock` ordena sus bloques
   `[[package]]` por nombre, y el del proyecto pasa de la zona «n» a la «b». La reconstrucción
   —una función de `bayesrisk.core.build`, la misma para el script y para el tiempo de ejecución—
   renombra el proyecto en su bloque y en sus autorreferencias, **reordena los bloques como uv** y
   vuelve a unir el texto; su SHA-256 tiene que dar **exactamente** `32c611ad…`, el hash del
   `uv.lock` de `v1.20.0` (y de 1.19.0: medido el mismo), y un test lo fija con su control negativo.
   `scripts/check_build_manifest.py --write` embebe ese hash como `uv_lock_sha256_nikodym`;
   `FittedScorecardBundle.load` acepta un `fit_lineage` cuyo `uv_lock_hash` sea el actual **o**
   ese. Si una release futura cambia una dependencia, la reconstrucción deja de dar el hash viejo
   y los bundles de nikodym se rechazan, igual que hoy los rechaza cualquier cambio de dependencias
   — sin regresión y sin ampliar. La evidencia exige cargar y aplicar un bundle **real** de 1.20.0
   y de 1.19.0 y reproducir su salida guardada.
c. **YAML de configuración**: el config no contiene el nombre del paquete salvo `report.theme`
   (D-REN-5.4); todo YAML que valida con nikodym 1.20.0 valida con bayesrisk 2.0.0 y da el mismo
   `config_hash`.

### D-REN-7 — `nikodym` 1.21.0, la capa de compatibilidad

- `compat/nikodym/src/nikodym/__init__.py` es su **único** módulo: emite **una** vez por proceso
  `DeprecationWarning("nikodym ahora se llama bayesrisk: …")`, reexporta el espacio público de
  `bayesrisk` (`__all__`, y un `__getattr__` que delega el resto), declara `__version__ = "1.21.0"`
  e instala en `sys.meta_path` un *finder* que resuelve `nikodym.<ruta>` a `bayesrisk.<ruta>`
  devolviendo **el mismo objeto módulo** (`sys.modules["nikodym.binning"] is
  sys.modules["bayesrisk.binning"]`), sin reescribir su `__spec__`, y sabe dar el código para
  `python -m nikodym.ui`. Lo que no existe en bayesrisk no existe en nikodym (`nikodym.pd` falla).
- `pyproject.toml` propio: `dependencies = ["bayesrisk>=2.0,<3"]`, **los mismos extras** con el
  mismo nombre, cada uno `bayesrisk[<extra>]>=2.0,<3` (un `pip install "nikodym[scoring]"` sigue
  trayendo OptBinning), `nikodym-ui` como script, clasificador `Development Status :: 7 - Inactive`,
  README congelado que remite a `bayesrisk` y a `docs.bayesadvisory.cl`, y la misma LICENSE.
- Un gate compara los extras de los dos `pyproject.toml` y la LICENSE byte a byte.

### D-REN-8 — Variables de entorno

Medido (§2): la librería no lee ninguna `NIKODYM_*`, así que la regla del prompt —«acepta
`BAYESRISK_*` y, si sólo existe la `NIKODYM_*`, la lee con `DeprecationWarning`»— **no tiene hoy a
qué aplicarse** y se deja escrita como regla para cuando exista la primera. Las de herramientas se
renombran a `BAYESRISK_*` en los dos lados a la vez, sin respaldo (nadie fuera del repo las fija);
el marcador `__NIKODYM_TOKEN__` pasa a `__BAYESRISK_TOKEN__` en la plantilla y en quien la reemplaza.

### D-REN-9 — Marca y copy público

- La **librería** se llama `bayesrisk` (minúscula, también al empezar la frase); la **consultora**,
  **Bayes Advisory**. «Nikodym RiskLib», «Nikodym» como nombre del producto y «Nexo Labs» como
  consultora desaparecen del copy público (README, `docs_site/`, metadata de PyPI, pantalla,
  informes HTML/PDF/Word, tooltips). La palabra sólo queda donde nombra a la distribución
  `nikodym` (página «Migrar desde nikodym», CHANGELOG histórico, README congelado del paquete de
  compatibilidad).
- `project_urls`: Documentation → `https://docs.bayesadvisory.cl`, Demo →
  `https://demo.bayesadvisory.cl`, «Consultoría (Bayes Advisory)» →
  `https://www.bayesadvisory.cl/?ref=pypi#contact`; Homepage, Source y Changelog siguen en
  `github.com/nexolabs-gh/nikodym` hasta que A7 decida el nombre del repositorio.
- CHANGELOG 2.0.0: «equivalente funcional a nikodym 1.20.0», la guía de una línea y cada cambio de
  D-REN-5. Página nueva «Migrar desde nikodym» en `docs_site`.

### D-REN-10 — Dominios y redirecciones

- `docs.bayesadvisory.cl` y `demo.bayesadvisory.cl` se añaden como dominios de producción a
  `nikodym-docs` y `nikodym-demo`; los antiguos siguen sirviendo hasta el STOP.
- El sitio y la demo pasan a los dominios nuevos: `site_url`, canonical, sitemap, robots, Open
  Graph, enlaces, y en `deploy.yml` las comprobaciones en vivo.
- Redirecciones **preparadas y sin activar**: `docs.nikodym.cl` y `demo.nikodym.cl` → 308 al
  dominio nuevo con ruta y query conservadas, como redirección de dominio del proyecto Vercel (la
  misma forma que `nikodym.cl` → `www.nikodym.cl` hoy). Se activan sólo con el OK de A7 y se
  prueban con 5 URLs profundas.
- Mientras `main` no reciba el renombre, la versión renombrada del sitio y de la demo se verifica
  en un despliegue *preview* de la rama, que puede recibir un alias del dominio nuevo.

### D-REN-11 — CI, publicación y documentos

- **Publicación, un solo tag** (pasada 1 de Codex: `ci.yml` y `release.yml` sólo reaccionan a
  `v*`, y la promoción exige exactamente un wheel y un sdist). El job `build` de `ci.yml` construye
  e inspecciona **dos candidatos separados** —`candidate-distributions-with-evidence` (bayesrisk,
  como hoy) y `candidate-compat-distributions` (nikodym 1.21.0, con `twine check` y su propia
  lista de contenidos)—, cada uno con sus sha256. El tag `v2.0.0` dispara `release.yml`: `promote`
  descarga los dos artefactos del CI verde de ese SHA y exige, por distribución, exactamente un
  wheel y un sdist con el nombre y la versión esperados (`__version__` para bayesrisk, el
  `pyproject` de `compat/` para nikodym); `publish` sube bayesrisk, y `publish-compat`, que
  **depende** de él, sube nikodym después —así `pip install nikodym` nunca ve un 1.21.0 sin su
  bayesrisk—. **Por archivo, no por versión** (pasada 2 de Codex: una subida que falla a medias
  deja la versión «existente» con un archivo de menos): antes de subir, cada job consulta el JSON
  de PyPI de su versión y compara nombre y SHA-256 de cada archivo —si ya está con los mismos bytes
  se omite, si está con otros bytes se **detiene en rojo**, si falta se sube (`skip-existing`
  sube sólo los que faltan)—, y después exige que PyPI sirva los **dos** archivos de cada
  distribución con los SHA-256 promovidos. En releases posteriores de bayesrisk el candidato de
  compatibilidad sigue construyéndose e inspeccionándose y esa misma regla lo omite. En pypi.org,
  `bayesrisk` necesita el publicador `release.yml`/`pypi` (A7); `nikodym` ya lo tiene.
  `testpypi.yml` (tag `testpypi-v*`) construye desde el commit etiquetado y ensaya los dos en
  TestPyPI —es un ensayo, no la promoción—, con un entorno por paquete (`testpypi` y
  `testpypi-nikodym`): TestPyPI no admite dos publicadores pendientes con la misma configuración
  para proyectos distintos (medido al registrarlos).
  `reservar-bayesrisk.yml` publicó la 0.0.1 de reserva y queda obsoleto tras la 2.0.0.
- **CI** construye e inspecciona las dos distribuciones y corre un job de compatibilidad en un venv
  limpio con los dos wheels.
- **Arnés H9R**: `distribution` pasa a `"bayesrisk"` en contrato, supervisor, sondas y tests; sus
  umbrales y cargas no cambian.
- **Documentos**: se actualizan los vigentes (AGENTS, RUNBOOK, DECISIONES-VIGENTES, ROADMAP,
  ESPECIFICACIONES, 00-INDICE, CHANGELOG nuevo); los SDD y enmiendas históricos **no se
  reescriben**: `nikodym.<x>` en ellos se lee `bayesrisk.<x>` desde 2.0.0, y el índice lo dice.

### D-REN-12 — Fuera del paquete

La carpeta del checkout pasa a `Proyectos\bayesrisk` **al final** de la sesión (mover el
directorio de trabajo corta la sesión); `HANDOFF.md` es un symlink que sólo un administrador puede
recrear, así que Cami ejecuta una línea de PowerShell como administrador. Fuera de alcance, sólo
listados: el material de Academia Bayes que importa nikodym, el cambio de dirección en Google
Search Console y la renovación de `nikodym.cl`.

## 4. Lo que NO cambia

Ningún número, ningún `config_hash`, ningún `data_hash`, ningún umbral ni carga del arnés H9R,
ninguna decisión aprobada (D-JUR/CMF, D-SC, D-VAL, D-INF…), ninguna perilla. El motor CMF y sus
tests se renombran de paquete y siguen intactos.

## 5. Equivalencia funcional: cómo se prueba

1. **Proyección canónica bit a bit** (`tests/unit/_proyeccion_canonica.py`, ya usada por S21/S22)
   del preset F1 y del YAML SBA de Cami, antes (nikodym 1.20.0) y después (bayesrisk 2.0.0):
   `config_hash` idéntico (`1063d6cf…`, `08cf3076…`), las mismas cinco cifras, y **cero
   diferencias** salvo las de D-REN-5, listadas una por una en la evidencia. La proyección
   serializa un estimador opaco por su tipo (`módulo.clase`, pasada 2 de Codex): el `WoEBinner`
   pasa de `nikodym.binning.transformer` a `bayesrisk.binning.transformer`. La comparación separa
   esas rutas —una diferencia cuyo único cambio es el prefijo del módulo o el nombre de clase de
   D-REN-3— y exige **cero** diferencias de otra clase: tablas, hashes de datos y números idénticos.
2. **Carga real**: artefactos generados con nikodym **1.20.0 y 1.19.0 instalados desde PyPI**
   (Study guardado, estimadores en joblib, bundle) cargan con los dos wheels nuevos en un venv
   limpio y reproducen sus salidas guardadas (WoE, PD, aplicación del bundle).
3. **Compatibilidad**: `import nikodym` avisa una sola vez; `import nikodym.binning`,
   `from nikodym.scorecard import …` y `python -m nikodym.ui` funcionan; `nikodym.pd` no existe;
   `nikodym.binning is bayesrisk.binning`.
4. Suite completa sin `-W ignore` con el árbol congelado; `python -m build` y `twine check` de los
   dos; TestPyPI; los dominios nuevos en el navegador.

## 6. Controles negativos de los gates nuevos

Cada gate nuevo nace con su control negativo (RUNBOOK §6): renombrar una identidad congelada
(D-REN-4) pone rojo su test; quitar la equivalencia del lock hace que el bundle legado se rechace;
un extra que falte en `compat` pone rojo el gate de extras; un finder que copie el módulo en vez de
reusarlo rompe la prueba de identidad; un `import nikodym` que avise dos veces rompe el conteo.

## 7. STOP (A7) y publicación (A8)

Nada de lo siguiente ocurre sin el OK de Cami, pedido con la herramienta de preguntas: publicar
`bayesrisk` 2.0.0 (primero) y `nikodym` 1.21.0 (después), activar las redirecciones, integrar la
rama a `main` y ejecutar lo aprobado de las propuestas (a) renombrar el repositorio a
`nexolabs-gh/bayesrisk` —revisando CI, insignias, publicadores de confianza de PyPI y TestPyPI (que
nombran el repositorio), despliegue de Vercel y el remoto del privado— y (b) `www.nikodym.cl`, ya
resuelta por Cami. Nunca se borra ni se hace *yank* de una versión de nikodym ni se da de baja
`nikodym.cl`.

## 8. Riesgos

- **Un reemplazo mecánico que alcance una identidad**: lo cubre D-REN-4 (máscara antes del
  reemplazo y test que fija cada constante) y, en último término, la proyección bit a bit.
- **Un finder que duplique módulos** (dos clases `BinningConfig` distintas): lo cubre la prueba de
  identidad de D-REN-7.
- **Reescribir la historia**: los SDD históricos y el CHANGELOG anterior no se tocan.
- **Publicadores de confianza que nombran el repositorio**: si A7 aprueba renombrarlo, hay que
  actualizarlos antes del primer release posterior.

## 11. Revisión adversarial

Tope: **dos pasadas** de Codex sobre este documento (orden de Cami), sin esperar su veredicto para
programar; lo que encuentre se absorbe aquí o se eleva. Sobre el código, tope de **tres pasadas**.

- **Pasada 1 (2026-09-27, `needs-attention`)**: cinco hallazgos, los cinco verificados en el árbol
  y absorbidos — el marcador `format` del bundle se valida antes que el lock (D-REN-4); el censo de
  identidades omitía los hashes de fila, traza y lote del bundle y la versión del prompt de IA
  (D-REN-4, con el censo exhaustivo que ahora lo sostiene y, por extensión, las versiones de esquema
  del arnés y el hash de forward del stress); cambiar el nombre por defecto del modelo duplicaba el
  registro en MLflow (identidades de MLflow congeladas); la clave `nikodym:` del `.qmd` no estaba
  clasificada (D-REN-5.8); y la promoción de dos distribuciones no casaba con el CI (D-REN-11, un
  solo tag y dos candidatos).
- **Pasada 2 (2026-09-27, `needs-attention`, tope alcanzado)**: tres hallazgos, verificados y
  absorbidos — reponer el nombre no reconstruye el lock viejo porque uv ordena los bloques
  (D-REN-6 b: reconstrucción con reordenamiento, fijada contra `32c611ad…`); consultar por versión
  ocultaba una subida parcial (D-REN-11: por archivo y SHA-256, con verificación final de los
  cuatro); la proyección nombra el tipo de un estimador opaco (§5: esas rutas se separan, el resto
  exige cero diferencias). El diseño queda cerrado; el código lleva su propio tope de tres pasadas.
- **Código, pasada 1 (`needs-attention`)**: un hallazgo falso —leyó del disco el defecto de un
  control negativo que corría en ese momento— y uno cierto: cotejar nikodym en PyPI **antes** de
  publicar bayesrisk, para no quedar con una release a medias (`bf8c07f`).
- **Código, pasada 2 (`needs-attention`)**: dos ciertos — `import *` de nikodym perdía los nombres
  de clase viejos y `__version__` (D-REN-3: los alias vuelven al `__all__` de 1.20), y el ensayo en
  TestPyPI podía quedar verde sin subir los bytes del commit (mismo cotejo por archivo que PyPI).

## 13. Simplicidad (SDD-31)

- **Entrada mínima**: ninguna nueva. El usuario cambia una línea de import.
- **Qué NO se configura**: el nombre del tema del informe, la carpeta por defecto, el prefijo de los
  tags de MLflow y la aceptación de artefactos viejos son constantes; no hay opción para «seguir
  llamándose nikodym».
- **Esenciales y «Avanzado»**: sin cambios.
- **Presupuesto de perillas**: **cero**.
- **Resúmenes por etapa, notebook mínimo y cinco cifras**: mismos textos salvo la marca; el
  cuaderno cambia sólo su línea de import; las cinco cifras no cambian (§5).
