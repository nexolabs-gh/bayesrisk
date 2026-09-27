# nikodym ahora se llama bayesrisk

La librería open-source de riesgo de crédito que se publicaba como `nikodym` se llama
**[bayesrisk](https://pypi.org/project/bayesrisk/)** desde su versión 2.0.0, equivalente funcional
a nikodym 1.20.0: los mismos resultados, bit a bit, con la misma configuración.

Para migrar, cambia una línea:

```python
import bayesrisk          # antes: import nikodym
```

e instala `pip install bayesrisk` (con los mismos *extras* que usabas, por ejemplo
`pip install "bayesrisk[scoring,report]"`).

## Qué es este paquete

`nikodym` 1.21.0 es el **último** release de este nombre. No trae código propio: depende de
`bayesrisk` y hace que lo escrito para nikodym ≤ 1.20 siga funcionando —`import nikodym`,
`from nikodym.scorecard import …`, `nikodym-ui`, `python -m nikodym.ui` y los estudios y
estimadores guardados con `joblib`— mientras migras. Al importarlo avisa una vez con un
`DeprecationWarning`. No recibirá mejoras: todo el desarrollo sigue en bayesrisk.

- Documentación: <https://docs.bayesadvisory.cl>
- Cómo migrar: <https://docs.bayesadvisory.cl/migrar-desde-nikodym/>
- Demo: <https://demo.bayesadvisory.cl>

Licencia Apache-2.0. Mantenido por Bayes Advisory.
