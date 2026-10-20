import { describe, expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { createElement } from "react"
import { FieldRenderer } from "@/components/FieldRenderer"
import fixture from "@/fixtures/schema.json"
import { advancedLeaves, advancedSchema, essentialFields, pruneForView } from "@/lib/essentials"
import { type JsonSchema, discriminatedBranches, orderedFields, resolveRef, unwrapNullable } from "@/lib/form-engine"
import { FIXTURE_JOBS, jobForConfig } from "@/lib/jobs"

const schema = fixture.json_schema as JsonSchema
const defs = schema.$defs ?? {}
const section = resolveRef(unwrapNullable(schema.properties!.provisioning_internal).schema, defs)

describe("H3: esenciales reales de la rama LGD", () => {
  it.each(["provided", "group_historical", "fractional_response", "beta_regression", "workout"])(
    "%s: censo completo, sin pérdidas ni duplicados, por rama y objetivo activo", (method) => {
      for (const recovery_col of [null, "tasa"]) {
        const value = { lgd: { method, recovery_col } }
        // Expande la rama activa como el renderer, sin contar la unión como una hoja atómica.
        const leaves = (input: JsonSchema, prefix = "", current: unknown = value): string[] => {
          const target = resolveRef(unwrapNullable(input).schema, defs)
          const branch = discriminatedBranches(target, defs).find((b) => b.tag === method)
          if (branch) {
            const part = target.ui_essentials_view
              ? pruneForView(branch.schema, defs, target.ui_essentials_view, [], undefined, current)
              : branch.schema
            return part ? leaves(part, prefix, current) : []
          }
          if (!target.properties) return [prefix]
          return orderedFields(target).flatMap(([key, child]) => leaves(
            child, prefix ? `${prefix}.${key}` : key,
            current && typeof current === "object" ? (current as Record<string, unknown>)[key] : undefined,
          ))
        }
        const open = leaves({ properties: Object.fromEntries(essentialFields(section, defs, null, value)) })
        const folded = leaves(advancedSchema(section, defs, value)!)
        expect(open.filter((key) => folded.includes(key))).toEqual([])
        expect([...open, ...folded].sort()).toEqual(leaves(section).sort())
        expect(open.length).toBeLessThanOrEqual(method === "workout" ? 9 : 6)
        if (method === "workout") expect(open).toHaveLength(9)
      }
    },
  )
  it("el YAML nuevo se reconoce sin cambiar el recorrido histórico", () => {
    const config = { data: {}, model: {}, provisioning_internal: { type: "full_population" } }
    expect(jobForConfig(FIXTURE_JOBS.jobs, config)?.id).toBe("pd_y_lgd_h3")
    config.provisioning_internal.type = "standard"
    expect(jobForConfig(FIXTURE_JOBS.jobs, config)?.id).toBe("pd_y_lgd")
  })
  it.each(["provided", "fractional_response", "beta_regression", "workout"])(
    "%s: el selector sólo aparece abierto; piso y techo sólo en Avanzado", (method) => {
      const value = { lgd: { method, recovery_col: method === "workout" ? "recupero" : null } }
      const essential = essentialFields(section, defs, null, value).find(([name]) => name === "lgd")![1]
      const advanced = advancedSchema(section, defs, value)!.properties!.lgd
      const render = (part: JsonSchema) => renderToStaticMarkup(createElement(FieldRenderer, {
        name: "lgd", path: ["provisioning_internal", "lgd"], schema: part, value: value.lgd,
        defs, onChange: () => {},
      }))
      const open = render(essential), folded = render(advanced)
      expect(open).not.toContain("Piso de LGD")
      expect(open).not.toContain("Techo de LGD")
      expect(folded).toContain("Piso de LGD")
      expect(folded).toContain("Techo de LGD")
      expect(folded).not.toContain('id="provisioning_internal.lgd"')
      const leaves = advancedLeaves(advancedSchema(section, defs, value), defs, ["provisioning_internal"])
      expect(leaves.map((x) => x.key)).toContain("provisioning_internal.lgd.lgd_floor")
      expect(leaves.map((x) => x.key)).not.toContain("provisioning_internal.lgd.method")
    },
  )

  it.each([null, "tasa"])("regresión con recuperación %s: sólo el objetivo activo abierto", (recovery_col) => {
    const value = { lgd: { method: "fractional_response", recovery_col } }
    const part = essentialFields(section, defs, null, value).find(([n]) => n === "lgd")![1]
    const html = renderToStaticMarkup(createElement(FieldRenderer, {
      name: "lgd", path: ["provisioning_internal", "lgd"], schema: part, value: value.lgd,
      defs, onChange: () => {},
    }))
    expect(html.includes("Columna LGD")).toBe(recovery_col === null)
    expect(html.includes("Columna de tasa recuperada")).toBe(recovery_col !== null)
    expect(discriminatedBranches(part, defs)).toHaveLength(5)
  })
})
