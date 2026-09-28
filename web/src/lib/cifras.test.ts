/**
 * El espejo de las cifras da exactamente lo que escribe `bayesrisk.report.cifras` (D-PAN-1).
 *
 * Es la mitad TypeScript del golden bidireccional: `scripts/cifras_golden.py` genera el golden
 * desde Python y `tests/unit/test_cifras_golden.py` exige que esté al día; aquí se exige que el
 * espejo dé cada texto. Las entradas llegan tipadas porque JSON no representa `-0`, `NaN`, `±inf`
 * ni enteros grandes.
 */
import { describe, expect, it } from "vitest"

import golden from "@/fixtures/cifras-golden.json"
import {
  VACIO,
  cifra,
  conteo,
  corte,
  marca,
  monto,
  montoCompacto,
  porcentaje,
  pvalor,
} from "@/lib/cifras"

type Entrada = { float: string } | { especial: "nan" | "inf" | "-inf" } | { entero: string } | null
type Caso = [string, number | null, Entrada, string]

function leer(entrada: Entrada): number | null {
  if (entrada === null) return null
  if ("float" in entrada) return Number(entrada.float)
  if ("entero" in entrada) return Number(entrada.entero)
  if (entrada.especial === "nan") return Number.NaN
  return entrada.especial === "inf" ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY
}

function llamar(funcion: string, argumento: number | null, valor: number | null): string {
  switch (funcion) {
    case "cifra":
      return cifra(valor, argumento ?? 0)
    case "pvalor":
      return pvalor(valor)
    case "corte":
      return corte(valor as number, argumento ?? 0)
    case "porcentaje":
      return porcentaje(valor, argumento ?? 0)
    case "monto":
      return monto(valor, "$")
    case "conteo":
      return conteo(valor)
    default:
      throw new Error(`función desconocida en el golden: ${funcion}`)
  }
}

const CASOS = (golden as { version: number; casos: Caso[] }).casos

describe("golden Python → TypeScript de las cifras (D-PAN-1)", () => {
  it("el golden trae las seis funciones y miles de casos", () => {
    expect(new Set(CASOS.map((c) => c[0]))).toEqual(
      new Set(["cifra", "pvalor", "corte", "porcentaje", "monto", "conteo"]),
    )
    expect(CASOS.length).toBeGreaterThan(4000)
  })

  it("el espejo escribe cada caso exactamente como Python", () => {
    const distintos = CASOS.filter(
      ([funcion, argumento, entrada, salida]) => llamar(funcion, argumento, leer(entrada)) !== salida,
    ).map(([funcion, argumento, entrada, salida]) => ({
      funcion,
      argumento,
      entrada,
      python: salida,
      espejo: llamar(funcion, argumento, leer(entrada)),
    }))
    expect(distintos.slice(0, 20)).toEqual([])
  })
})

describe("lo que el golden no puede decir", () => {
  it("un -0 se lee como -0 y se escribe sin signo", () => {
    expect(Object.is(leer({ float: "-0.0" }), -0)).toBe(true)
    expect(cifra(-0)).toBe("0,0000")
    expect(corte(-0)).toBe("0,00")
  })

  it("conteo fuera de los enteros seguros devuelve el entero sin agrupar", () => {
    expect(conteo(2 ** 53 - 1)).toBe("9.007.199.254.740.991")
    expect(conteo(2 ** 53)).toBe("9007199254740992")
    expect(conteo(null)).toBe(VACIO)
  })

  it("las marcas de eje escriben el tick exacto, con miles y sin signo en el cero", () => {
    expect(marca(0.25)).toBe("0,25")
    expect(marca(0.5)).toBe("0,5")
    expect(marca(1200)).toBe("1.200")
    expect(marca(-0)).toBe("0")
    expect(marca(3e-9)).toBe("3,0e-09")
    expect(marca(-1500.5)).toBe("-1.500,5")
  })

  it("el monto compacto usa coma decimal y punto de miles", () => {
    expect(montoCompacto(2_345_678, "$")).toBe("$2,3 M")
    expect(montoCompacto(114_325_315, "$")).toBe("$114 M")
    expect(montoCompacto(8_079_000_000, "$")).toBe("$8.079 M")
    expect(montoCompacto(80_400, "$")).toBe("$80 k")
    expect(montoCompacto(-950, "$")).toBe("-$950")
  })
})
