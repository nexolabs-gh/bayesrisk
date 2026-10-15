/**
 * La última ejecución de ESTA sesión puede publicar resultados. Una siembra (trabajo, YAML o
 * ejemplo) también invalida la anterior, aunque las rutas excluidas del config_hash sean iguales.
 * Vive en el provider: salir de Ejecutar y volver no reinicia este orden.
 */
export function crearControlDeCorridas(getGeneracion: () => number): () => () => boolean {
  let ultimoIntento = 0
  return () => {
    const intento = ++ultimoIntento
    const generacion = getGeneracion()
    return () => intento === ultimoIntento && generacion === getGeneracion()
  }
}
