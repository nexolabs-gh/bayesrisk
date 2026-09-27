# Migrar desde nikodym

La librería que se publicaba como `nikodym` se llama **bayesrisk** desde la versión 2.0.0. Es
equivalente funcional a nikodym 1.20.0: con la misma configuración da los mismos resultados, bit
a bit, y el mismo `config_hash`.

## El cambio, en una línea

```python
import bayesrisk  # antes: import nikodym
```

Instala bayesrisk con los mismos *extras* que usabas:

```bash
pip install "bayesrisk[scoring,report,ui]"
```

## Qué cambia

- **El import**: `nikodym` pasa a `bayesrisk` en todas sus rutas (`from bayesrisk.scorecard import …`).
- **La interfaz local**: se abre con `bayesrisk-ui` (o `python -m bayesrisk.ui`). Su carpeta de
  trabajo por defecto pasa a `.bayesrisk_ui`; para seguir viendo las corridas anteriores, ábrela
  con `bayesrisk-ui --workdir .nikodym_ui`.
- **La puerta guiada**: la carpeta por defecto pasa a `bayesrisk-runs`. Para continuar un proyecto
  que empezaste con nikodym, indícala: `bayesrisk.Scorecard(..., run_dir="nikodym-runs")`.
- **Los nombres de clase**: `BayesRiskConfig` (antes `NikodymConfig`) y `BayesRiskError` (antes
  `NikodymError`). Los nombres anteriores siguen funcionando en toda la serie 2.x.
- **El tema del informe** se llama `bayesrisk`; un YAML con `theme: nikodym` sigue siendo válido.

## Qué no cambia

- **Los números.** El mismo config da el mismo `config_hash` y los mismos resultados.
- **Tus archivos de configuración.** Todo YAML que validaba con nikodym 1.20.0 valida igual.
- **Lo que ya guardaste.** Los estudios y estimadores guardados con `joblib` cargan con `bayesrisk`
  y `nikodym` 1.21.0 instalados juntos, y los *bundles* del scorecard de nikodym 1.19.0 y 1.20.0
  se aplican con bayesrisk 2.0.0 sin reentrenar.
- **Tu registro de MLflow.** Los tags `nikodym.*` y el nombre de modelo por defecto
  `nikodym-model` se mantienen, para que una corrida repetida no registre un modelo duplicado.

## Si no cambias nada

`pip install nikodym` instala nikodym 1.21.0, el último con ese nombre: depende de bayesrisk,
reexporta todo y avisa una sola vez que el paquete cambió de nombre. Sirve para migrar a tu ritmo,
pero no recibirá mejoras: todo el desarrollo sigue en bayesrisk.
