/**
 * Gate de censo del front (enmienda CIFRAS-EN-PANTALLA, D-PAN-5): ninguna cifra de la pantalla se
 * escribe por fuera del espejo de `bayesrisk.report.cifras`.
 *
 * Prohíbe los formateadores nativos —`toFixed` redondea el binario y escribe punto decimal;
 * `toLocaleString` e `Intl` dependen de ICU— fuera de `lib/cifras.ts`, y exige `tickFormatter` en
 * todo eje numérico de los gráficos (Recharts pinta `String(v)` si no lo tiene: punto decimal y sin
 * miles). **Qué NO cubre**: un número interpolado directo en una plantilla (`${n} filas`); ése lo
 * cubre el conteo en la demo viva del cierre.
 */
import { describe, expect, it } from "vitest"

const FUENTES = import.meta.glob<string>("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
})

const PROHIBIDOS: [string, RegExp][] = [
  ["toFixed", /\.toFixed\(/],
  ["toExponential", /\.toExponential\(/],
  ["toPrecision", /\.toPrecision\(/],
  ["toLocaleString", /\.toLocaleString\(/],
  ["Intl.NumberFormat", /Intl\.NumberFormat/],
]

function esProduccion(ruta: string): boolean {
  return !/\.test\.tsx?$/.test(ruta) && !ruta.includes("/__tests__/") && ruta !== "/src/lib/cifras.ts"
}

/** Los formateadores nativos que aparecen en `texto`, por nombre. */
export function formateadoresNativos(texto: string): string[] {
  return PROHIBIDOS.filter(([, patron]) => patron.test(texto)).map(([nombre]) => nombre)
}

/** Los ejes numéricos de `texto` sin `tickFormatter`: su apertura, para el mensaje. */
export function ejesSinFormato(texto: string): string[] {
  const faltan: string[] = []
  for (const match of texto.matchAll(/<(XAxis|YAxis)\b[^>]*?\/?>/gs)) {
    const [elemento, eje] = match
    const numerico =
      eje === "XAxis" ? /type="number"/.test(elemento) : !/type="category"/.test(elemento)
    if (numerico && !/tickFormatter=/.test(elemento)) faltan.push(elemento.slice(0, 80))
  }
  return faltan
}

describe("censo del front: cada cifra pasa por el espejo (D-PAN-5)", () => {
  const produccion = Object.entries(FUENTES).filter(([ruta]) => esProduccion(ruta))

  it("el censo ve el código de la pantalla", () => {
    expect(produccion.length).toBeGreaterThan(50)
    expect(produccion.some(([ruta]) => ruta === "/src/components/ResultsTab.tsx")).toBe(true)
  })

  it("ningún formateador nativo de números fuera de lib/cifras.ts", () => {
    const hallazgos = produccion
      .map(([ruta, texto]) => [ruta, formateadoresNativos(texto)] as const)
      .filter(([, nombres]) => nombres.length > 0)
    expect(hallazgos).toEqual([])
  })

  it("todo eje numérico de los gráficos declara su tickFormatter", () => {
    const graficos = produccion.filter(([ruta]) => ruta.startsWith("/src/components/charts/"))
    expect(graficos.length).toBeGreaterThan(10)
    const hallazgos = graficos
      .map(([ruta, texto]) => [ruta, ejesSinFormato(texto)] as const)
      .filter(([, ejes]) => ejes.length > 0)
    expect(hallazgos).toEqual([])
  })

  it("el gate caza lo que promete", () => {
    expect(formateadoresNativos("return v.toFixed(4)")).toEqual(["toFixed"])
    expect(formateadoresNativos('n.toLocaleString("es-CL")')).toEqual(["toLocaleString"])
    expect(formateadoresNativos("return cifra(v)")).toEqual([])
    expect(ejesSinFormato('<YAxis domain={[0, 1]} tick={AXIS_TICK} />')).toHaveLength(1)
    expect(ejesSinFormato('<YAxis type="category" dataKey="feature" />')).toEqual([])
    expect(ejesSinFormato('<XAxis type="number" tickFormatter={marca} />')).toEqual([])
    expect(ejesSinFormato('<XAxis dataKey="label" />')).toEqual([])
    expect(ejesSinFormato('<XAxis\n  type="number"\n  dataKey="beta"\n/>')).toHaveLength(1)
  })
})
