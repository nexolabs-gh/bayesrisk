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

import { FieldRenderer, NO_APLICA } from "@/components/FieldRenderer"
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

describe("una corrida de cartera los declara «no aplica» (FLUJO-GUIADO-IFRS9 §3.12)", () => {
  // El trabajo «Provisiones IFRS 9» siembra los dos en `null`: el formulario dice que no aplican en
  // vez de pintar un grupo vacío que invitaría a llenarlo a medias (regla de malo sin partición).
  it.each(["target", "partition"])("data.%s en null: «No aplica», sin editor", (nombre) => {
    const html = pintar(nombre, true, null)
    expect(html).toContain(NO_APLICA)
    expect(html).not.toContain("<fieldset")
    expect(html).not.toContain("<input")
  })

  it("contracara: con su objeto declarado se edita como siempre", () => {
    const html = pintar("partition", true, {})
    expect(html).not.toContain(NO_APLICA)
    expect(html).toContain("<fieldset")
  })
})

describe("un campo cuyo null no es «desactivado» lo dice (FLUJO-GUIADO-IFRS9 §3.12)", () => {
  // Los 12 meses del Stage 1 en blanco los infiere el motor de la unidad de la curva: rotularlos
  // «desactivado» diría que no se usan, que es lo contrario.
  function horizonte12m(value: unknown): string {
    const entrada = configSectionSchema(PAYLOAD, "provisioning_ifrs9")
    if (!entrada) throw new Error("el fixture no trae la sección provisioning_ifrs9")
    const pd = resolveRef(
      (resolveRef(entrada.schema, DEFS).properties ?? {}).pd as JsonSchema,
      DEFS,
    )
    return renderToStaticMarkup(
      createElement(FieldRenderer, {
        name: "horizon_12m_periods",
        schema: (pd.properties ?? {}).horizon_12m_periods as JsonSchema,
        path: ["provisioning_ifrs9", "pd", "horizon_12m_periods"],
        value,
        defs: DEFS,
        onChange: () => undefined,
        required: false,
      }),
    )
  }

  it("en blanco: «inferido de la unidad de la curva», no «desactivado»", () => {
    const html = horizonte12m(null)
    expect(html).toContain("(inferido de la unidad de la curva)")
    expect(html).not.toContain("(desactivado)")
  })

  it("contracara: un anulable cualquiera sigue diciendo «desactivado»", () => {
    expect(pintar("target", false, null)).toContain("(desactivado)")
  })
})
