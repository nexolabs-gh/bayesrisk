/**
 * D-ECL-2: `data.target` y `data.partition` son OBLIGATORIOS y admiten `null` (corrida de cartera).
 *
 * El formulario pinta con un interruptor «Activar …» todo campo opcional `X | None`. Uno obligatorio
 * no lleva interruptor: no tiene default, quien modela lo declara entero, y su `null` es una
 * declaración de la corrida de cartera, no un estado apagado. Sin esta regla el formulario del
 * scorecard ganaba dos interruptores sobre sus decisiones institucionales.
 *
 * Mismo patrón que `ResultsTab.test.ts`: el componente REAL a HTML estático con `react-dom/server`,
 * sobre el schema real del fixture.
 */

import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { FieldRenderer } from "@/components/FieldRenderer"
import fixtureSchema from "@/fixtures/schema.json"
import { type Defs, type JsonSchema, resolveRef } from "@/lib/form-engine"
import { type SchemaPayload, configSectionSchema } from "@/lib/schema"

const PAYLOAD = fixtureSchema as unknown as SchemaPayload
const DEFS: Defs = PAYLOAD.json_schema.$defs ?? {}

function campoDeDatos(nombre: string): JsonSchema {
  const entrada = configSectionSchema(PAYLOAD, "data")
  if (!entrada) throw new Error("el fixture no trae la sección data")
  return (resolveRef(entrada.schema, DEFS).properties ?? {})[nombre] as JsonSchema
}

function pintar(nombre: string, required: boolean, value: unknown): string {
  return renderToStaticMarkup(
    createElement(FieldRenderer, {
      name: nombre,
      schema: campoDeDatos(nombre),
      path: ["data", nombre],
      value,
      defs: DEFS,
      onChange: () => undefined,
      required,
    }),
  )
}

describe("un campo obligatorio que admite null no lleva interruptor (D-ECL-2)", () => {
  // Sólo el interruptor del PROPIO campo: los subcampos opcionales de `target` (`good_rule`,
  // `window`…) siguen llevando el suyo, y ésos sí son interruptores.
  it.each([
    ["target", "Activar Definición de target"],
    ["partition", "Activar Particiones"],
  ])("data.%s obligatorio: sin «%s»", (nombre, rotulo) => {
    const campo = campoDeDatos(nombre)
    expect((campo.anyOf ?? []).some((rama) => rama.type === "null")).toBe(true)
    expect(pintar(nombre, true, {})).not.toContain(rotulo)
  })

  it("contracara: el mismo campo, si fuera opcional, sí lo lleva", () => {
    expect(pintar("target", false, {})).toContain("Activar Definición de target")
  })
})
