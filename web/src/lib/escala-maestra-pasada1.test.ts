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
  borradoresVigentes,
  huellaDelValor,
  semillaAlActivar,
  serializarParaEditor,
  sincronizarEditorJson,
  type JsonSchema,
} from "@/lib/form-engine"
import { canRun } from "@/lib/validation"

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
 * Pasada 3 de Codex sobre la capa B: con un campo JSON encendido en blanco, pegar `[500, 550` sólo
 * marcaba un error local del editor; al ir a «Ejecutar» el editor se desmontaba, el aviso se
 * perdía y la corrida formaba tramos automáticos con el campo vacío. El texto ilegible vive ahora en
 * el estado compartido, con la huella del valor sobre el que se escribió, y bloquea la corrida
 * mientras siga vigente.
 */
describe("un JSON a medio escribir bloquea la corrida", () => {
  const config = { master_scale: { grade_edges: null, approval_cutoff: null } }
  const borrador = {
    ruta: ["master_scale", "grade_edges"],
    texto: "[500, 550",
    base: huellaDelValor(null),
    rotulo: "Cortes de los tramos",
  }

  it("el borrador vigente detiene el gate, también después de navegar", () => {
    const pendientes = borradoresVigentes({ "master_scale.grade_edges": borrador }, config)
    expect(pendientes).toEqual([borrador])
    const gate = canRun({ kind: "valid", hash: "abc", pipeline: null }, "ds", pendientes)
    expect(gate.ok).toBe(false)
    expect(gate.reason).toContain("Cortes de los tramos")
  })

  it("un valor que cambió desde fuera deja el borrador sin vigencia", () => {
    const otro = { master_scale: { grade_edges: [520], approval_cutoff: null } }
    expect(borradoresVigentes({ "master_scale.grade_edges": borrador }, otro)).toEqual([])
  })

  it("sin borradores, el gate de siempre", () => {
    const gate = canRun({ kind: "valid", hash: "abc", pipeline: null }, "ds", [])
    expect(gate.ok).toBe(true)
  })
})
