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
  huellaDelValor,
  semillaAlActivar,
  serializarParaEditor,
  sincronizarEditorJson,
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

  it("el puntaje de aprobación de la escala maestra lo declara en el schema publicado", () => {
    const seccion = (
      fixtureSchema as unknown as { json_schema: { properties: Record<string, JsonSchema> } }
    ).json_schema.properties.master_scale
    const rama = seccion?.anyOf?.find((r) => r.properties !== undefined)
    const campo = rama?.properties?.approval_cutoff as JsonSchema | undefined
    expect(campo?.ui_activate_blank).toBe(true)
  })
})
