/**
 * Pasada 1 de Codex sobre la capa B del SDD-32: dos defectos del formulario que la escala maestra
 * hace visibles, cada uno con su regla pura (el runner corre sin DOM; el recorrido vivo, aparte).
 *
 * 1. El editor JSON (`JsonField`, el de `grade_edges`) leía su valor sólo al montarse: el formulario
 *    de cada sección conserva su `key`, así que cargar un YAML dejaba a la vista los cortes viejos
 *    mientras la corrida usaba los nuevos.
 * 2. Encender un número anulable sin default sembraba `0` (`defaultForSchema`): con el puntaje de
 *    aprobación, un corte que aprueba toda la cartera sin que nadie lo escribiera (§13: el apetito
 *    de riesgo no tiene valor de fábrica). El campo lo declara con `ui_activate_blank`.
 */

import { describe, expect, it } from "vitest"

import fixtureSchema from "@/fixtures/schema.json"
import {
  ACTIVAR_EN_BLANCO,
  LARGO_DEL_DESCARTE,
  anadirFila,
  eliminarFila,
  filasDeLista,
  huellaDelValor,
  moveListItem,
  moverFila,
  removeListItem,
  salirDelEditorJson,
  semillaAlActivar,
  serializarParaEditor,
  sincronizarEditorJson,
  textoDelDescarte,
  type JsonSchema,
} from "@/lib/form-engine"

describe("el editor JSON adopta un valor que cambió desde fuera", () => {
  it("un YAML cargado con otros cortes se ve en el editor", () => {
    const antes = { texto: serializarParaEditor([500]), visto: huellaDelValor([500]) }
    const despues = sincronizarEditorJson(antes, [550])
    expect(despues.texto).toBe(serializarParaEditor([550]))
    expect(despues.visto).toBe(huellaDelValor([550]))
  })

  it("el valor que la persona acaba de escribir no le reescribe el texto", () => {
    // Escribió `[500, 550]` en una línea: el config ya trae ese valor y el editor no lo reformatea.
    const escrito = { texto: "[500, 550]", visto: huellaDelValor([500, 550]) }
    expect(sincronizarEditorJson(escrito, [500, 550])).toBe(escrito)
  })

  it("vaciar el campo desde fuera vacía el editor", () => {
    const antes = { texto: serializarParaEditor([500]), visto: huellaDelValor([500]) }
    expect(sincronizarEditorJson(antes, undefined).texto).toBe("")
    // Un campo encendido en blanco llega en `null`: el editor queda vacío, no dice «null».
    expect(sincronizarEditorJson(antes, null).texto).toBe("")
  })
})

describe("encender un número sin valor de fábrica no inventa uno", () => {
  const numero: JsonSchema = { type: "number" }

  it("con `ui_activate_blank` el campo se enciende en blanco", () => {
    const campo: JsonSchema = { anyOf: [numero, { type: "null" }], ui_activate_blank: true }
    expect(semillaAlActivar(campo, numero, undefined)).toBe(ACTIVAR_EN_BLANCO)
  })

  it("sin la marca, la regla de siempre: el default o la cota, y 0 a falta de ambos", () => {
    const campo: JsonSchema = { anyOf: [numero, { type: "null" }] }
    expect(semillaAlActivar(campo, numero, undefined)).toBe(0)
    expect(semillaAlActivar(campo, { type: "integer", minimum: 1 }, undefined)).toBe(1)
  })

  it("los dos campos de la escala maestra lo declaran en el schema publicado", () => {
    const seccion = (
      fixtureSchema as unknown as { json_schema: { properties: Record<string, JsonSchema> } }
    ).json_schema.properties.master_scale
    const rama = seccion?.anyOf?.find((r) => r.properties !== undefined)
    for (const hoja of ["approval_cutoff", "grade_edges"]) {
      const campo = rama?.properties?.[hoja] as JsonSchema | undefined
      expect(campo?.ui_activate_blank, hoja).toBe(true)
      expect(campo?.ui_null_label, hoja).toBeTruthy()
    }
  })
})

/**
 * Pasadas 3 y 4 de Codex sobre la capa B: un texto que no se puede leer no debe perderse en
 * silencio al salir de Configuración (pasada 3), pero tampoco quedar guardado aparte, donde se
 * volvía viejo —una sección apagada, una fila movida, un config reemplazado— y detenía la corrida
 * (pasada 4). La regla: al salir del campo, el texto ilegible se descarta, el editor vuelve al valor
 * del config y se avisa. Lo que se ve es lo que corre. Los recorridos con navegador viven en
 * `e2e/editor-json.spec.ts`.
 */
describe("salir del editor JSON con un texto ilegible lo descarta", () => {
  it("vuelve al valor del config y entrega el texto descartado", () => {
    const escribiendo = { texto: "[500, 550", visto: huellaDelValor(null) }
    const salida = salirDelEditorJson(escribiendo, null)
    expect(salida.descartado).toBe("[500, 550")
    expect(salida.estado).toEqual({ texto: "", visto: huellaDelValor(null) })
  })

  it("con un valor válido previo, el editor lo vuelve a mostrar", () => {
    const escribiendo = { texto: "[500, 550", visto: huellaDelValor([500]) }
    const salida = salirDelEditorJson(escribiendo, [500])
    expect(salida.descartado).toBe("[500, 550")
    expect(JSON.parse(salida.estado.texto)).toEqual([500])
  })

  it("un texto que se puede leer ya está en el config: nada cambia", () => {
    const escrito = { texto: "[500,550]", visto: huellaDelValor([500, 550]) }
    expect(salirDelEditorJson(escrito, [500, 550])).toEqual({ estado: escrito, descartado: null })
    const vacio = { texto: "  ", visto: huellaDelValor(null) }
    expect(salirDelEditorJson(vacio, null).descartado).toBeNull()
  })

  it("el aviso cita el texto en una línea y recortado si es largo", () => {
    expect(textoDelDescarte("[500,\n  550")).toBe("[500, 550")
    const largo = "[" + "1, ".repeat(100)
    const citado = textoDelDescarte(largo)
    expect(citado.endsWith("…")).toBe(true)
    expect(citado.length).toBe(LARGO_DEL_DESCARTE + 1)
  })
})

/**
 * Pasada 4 de Codex sobre la capa B: la `key` de las filas de una lista era su posición, así que
 * subir, bajar o eliminar una fila dejaba el estado propio de sus campos en la fila que pasaba a
 * ocupar su lugar. Las identidades se mueven con las filas.
 */
describe("las filas de una lista conservan su identidad", () => {
  const a = { name: "antiguedad_meses", user_splits: [24, 60] }
  const b = { name: "ingreso_mensual", user_splits: [1000, 5000] }
  const c = { name: "mora_max_12m", user_splits: [1, 3] }

  it("subir una fila mueve su identidad con ella", () => {
    const filas = filasDeLista([a, b])
    const nuevos = moveListItem([a, b], 1, -1)
    const movidas = moverFila(filas, nuevos, 1, -1)
    expect(movidas.ids).toEqual([filas.ids[1], filas.ids[0]])
    // El config vuelve con la lista movida: se reconoce como propia, no como un cambio de fuera.
    expect(filasDeLista(nuevos, movidas)).toBe(movidas)
  })

  it("con dos filas iguales, la que se mueve es la que lleva su identidad", () => {
    const filas = filasDeLista([a, a])
    const movidas = moverFila(filas, moveListItem([a, a], 1, -1), 1, -1)
    expect(movidas.ids).toEqual([filas.ids[1], filas.ids[0]])
  })

  it("eliminar una fila anterior no le pasa su identidad a la siguiente", () => {
    const filas = filasDeLista([a, b, c])
    const nuevos = removeListItem([a, b, c], 0)
    const quedan = eliminarFila(filas, nuevos, 0)
    expect(quedan.ids).toEqual([filas.ids[1], filas.ids[2]])
    expect(filasDeLista(nuevos, quedan)).toBe(quedan)
  })

  it("una fila añadida estrena una identidad que ninguna tuvo", () => {
    const filas = eliminarFila(filasDeLista([a, b]), [b], 0)
    const nuevos = [b, c]
    const conNueva = anadirFila(filas, nuevos)
    expect(conNueva.ids[1]).not.toBe(0)
    expect(new Set(conNueva.ids).size).toBe(2)
  })

  it("una lista que cambió desde fuera con otro largo recibe identidades nuevas", () => {
    const filas = filasDeLista([a, b])
    const deFuera = filasDeLista([c], filas)
    expect(deFuera.ids.some((id) => filas.ids.includes(id))).toBe(false)
    // Con el mismo largo, las conserva: los campos adoptan los valores nuevos.
    expect(filasDeLista([c, a], filas).ids).toEqual(filas.ids)
  })
})
