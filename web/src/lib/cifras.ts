/**
 * Espejo de `bayesrisk.report.cifras`: cómo escribe la pantalla un número (enmienda
 * CIFRAS-EN-PANTALLA, D-PAN-1). Es la regla del informe, no una parecida:
 *
 * - coma decimal y punto de miles (es-CL);
 * - cuatro decimales entre 0,001 y 1.000; dos, con miles, desde 1.000; dos cifras significativas
 *   bajo 0,001; notación científica bajo una millonésima;
 * - p-valores `< 0,001` o tres decimales; cortes del config **exactos**;
 * - la regla del cero final: una cifra redondeada que termina en cero y no es el exacto lleva más
 *   decimales (un PSI de 0.24996 no se escribe «0,2500» junto a su corte de 0,25).
 *
 * El exacto es **decimal**: se parte de `Number.prototype.toString()`, que —como el `repr` de
 * Python— es la representación más corta que vuelve al mismo `float64`, y se redondea al par más
 * cercano en aritmética entera (`bigint`). Nada de `toFixed` (redondea el binario) ni de `Intl`
 * (depende de ICU). `porcentaje` y `monto` redondean el valor **binario** exacto, como el formato
 * `f` y `round` de Python, que es lo que el informe escribía.
 *
 * Lo ata a Python el golden `@/fixtures/cifras-golden.json`, que genera `scripts/cifras_golden.py`.
 * Sólo presentación: ningún número de `results` se toca.
 */

/** Marcador de un valor ausente o no finito: el em-dash de toda la pantalla y el informe. */
export const VACIO = "—"

/** Un decimal exacto: `(-1)^neg · coef · 10^exp`. */
interface Dec {
  neg: boolean
  coef: bigint
  exp: number
}

const DIEZ = 10n

function pot10(n: number): bigint {
  return DIEZ ** BigInt(n)
}

/** El decimal más corto que vuelve a `x` (el `repr` de Python). `x` finito. */
function exactoCorto(x: number): Dec {
  return decimalDeTexto(String(x))
}

/** Un decimal escrito con punto y, quizá, exponente (`-1.5e-7`), exacto. */
function decimalDeTexto(texto: string): Dec {
  const neg = texto.startsWith("-")
  const cuerpo = neg ? texto.slice(1) : texto
  const [mantisa, expTexto] = cuerpo.split("e")
  const exp10 = expTexto === undefined ? 0 : Number(expTexto)
  const [entero, fraccion = ""] = mantisa.split(".")
  return { neg, coef: BigInt(entero + fraccion), exp: exp10 - fraccion.length }
}

/** El valor binario exacto de `x` (finito), sin redondeo. */
function exactoBinario(x: number): Dec {
  const vista = new DataView(new ArrayBuffer(8))
  vista.setFloat64(0, x)
  const alto = vista.getUint32(0)
  const bajo = vista.getUint32(4)
  const neg = alto >>> 31 === 1
  const bitsExp = (alto >>> 20) & 0x7ff
  let mantisa = (BigInt(alto & 0xfffff) << 32n) | BigInt(bajo)
  let exp2: number
  if (bitsExp === 0) {
    exp2 = -1074
  } else {
    mantisa |= 1n << 52n
    exp2 = bitsExp - 1075
  }
  if (exp2 >= 0) return { neg, coef: mantisa << BigInt(exp2), exp: 0 }
  // m · 2^e = m · 5^(-e) · 10^e
  return { neg, coef: mantisa * 5n ** BigInt(-exp2), exp: exp2 }
}

function digitos(n: bigint): number {
  return n === 0n ? 1 : n.toString().length
}

/** Exponente de la primera cifra significativa (`Decimal.adjusted()`). `d` distinto de cero. */
function ajustado(d: Dec): number {
  return d.exp + digitos(d.coef) - 1
}

/** `d` redondeado al par más cercano con `decimales` decimales (`quantize` ROUND_HALF_EVEN). */
function redondeado(d: Dec, decimales: number): Dec {
  const objetivo = -decimales
  if (d.exp >= objetivo) return { neg: d.neg, coef: d.coef * pot10(d.exp - objetivo), exp: objetivo }
  const divisor = pot10(objetivo - d.exp)
  let cociente = d.coef / divisor
  const doble = (d.coef % divisor) * 2n
  if (doble > divisor || (doble === divisor && cociente % 2n === 1n)) cociente += 1n
  return { neg: d.neg, coef: cociente, exp: objetivo }
}

/** Compara `a` con `b` (con signo): -1, 0 o 1. */
function comparar(a: Dec, b: Dec): number {
  const exp = Math.min(a.exp, b.exp)
  const va = (a.neg ? -1n : 1n) * a.coef * pot10(a.exp - exp)
  const vb = (b.neg ? -1n : 1n) * b.coef * pot10(b.exp - exp)
  return va === vb ? 0 : va > vb ? 1 : -1
}

/** El número que dice un texto de `cifra` o `pvalor` (`1.234,5`, `2,3e-07`); `null` si no dice uno. */
function leer(texto: string): Dec | null {
  const limpio = texto.replace(/\./g, "").replace(",", ".")
  return /^-?\d+(\.\d+)?(e[+-]?\d+)?$/.test(limpio) ? decimalDeTexto(limpio) : null
}

/** Compara `|d|` con `10^k`: -1, 0 o 1. */
function compararPot10(d: Dec, k: number): number {
  const izquierda = d.exp >= k ? d.coef * pot10(d.exp - k) : d.coef
  const derecha = d.exp >= k ? 1n : pot10(k - d.exp)
  return izquierda === derecha ? 0 : izquierda > derecha ? 1 : -1
}

function igual(a: Dec, b: Dec): boolean {
  if (a.coef === 0n && b.coef === 0n) return true
  if (a.neg !== b.neg) return false
  const exp = Math.min(a.exp, b.exp)
  return a.coef * pot10(a.exp - exp) === b.coef * pot10(b.exp - exp)
}

/** Cuántos decimales tiene el exacto sin sus ceros a la derecha (0 si es entero). */
function decimalesDelExacto(d: Dec): number {
  if (d.coef === 0n) return 0
  let ceros = 0
  let coef = d.coef
  while (coef % DIEZ === 0n) {
    coef /= DIEZ
    ceros += 1
  }
  return Math.max(0, -(d.exp + ceros))
}

function agrupar(entero: string): string {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
}

/** `numero` ya redondeado a `decimales` (exp = -decimales), escrito en es-CL. */
function posicional(numero: Dec, decimales: number, miles: boolean): string {
  const signo = numero.neg && numero.coef !== 0n ? "-" : ""
  const texto = numero.coef.toString().padStart(decimales + 1, "0")
  let entero = decimales > 0 ? texto.slice(0, -decimales) : texto
  const fraccion = decimales > 0 ? texto.slice(-decimales) : ""
  if (miles) entero = agrupar(entero)
  return decimales > 0 ? `${signo}${entero},${fraccion}` : `${signo}${entero}`
}

function conCeroFinal(exacto: Dec, decimalesBase: number, miles: boolean): string {
  let decimales = decimalesBase
  const limite = Math.max(decimales, decimalesDelExacto(exacto))
  for (;;) {
    const r = redondeado(exacto, decimales)
    const texto = posicional(r, decimales, miles)
    if (decimales >= limite || igual(r, exacto) || !texto.endsWith("0")) return texto
    decimales += 1
  }
}

function cientifica(exacto: Dec): string {
  const exponente = ajustado(exacto)
  const signoExp = exponente < 0 ? "-" : "+"
  const mantisa = conCeroFinal({ ...exacto, exp: exacto.exp - exponente }, 1, false)
  return `${mantisa}e${signoExp}${String(Math.abs(exponente)).padStart(2, "0")}`
}

function noFinito(x: number): string {
  if (Number.isNaN(x)) return VACIO
  return x > 0 ? "inf" : "-inf"
}

/** Un número real como lo lee una persona (reglas del encabezado). `decimales`: la base. */
export function cifra(x: number | null | undefined, decimales = 4): string {
  if (x === null || x === undefined) return VACIO
  if (!Number.isFinite(x)) return noFinito(x)
  const exacto = exactoCorto(x)
  if (exacto.coef === 0n) return posicional({ neg: false, coef: 0n, exp: -decimales }, decimales, false)
  if (compararPot10(redondeado(exacto, decimales), 3) >= 0) return conCeroFinal(exacto, 2, true)
  if (compararPot10(exacto, -3) >= 0) return conCeroFinal(exacto, decimales, false)
  if (compararPot10(exacto, -6) >= 0) return conCeroFinal(exacto, 1 - ajustado(exacto), false)
  return cientifica(exacto)
}

/** Un p-valor: `< 0,001` bajo ese corte; si no, tres decimales con la regla del cero final. */
export function pvalor(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return VACIO
  if (!Number.isFinite(x)) return cifra(x)
  const exacto = exactoCorto(x)
  if (exacto.neg || exacto.coef === 0n || compararPot10(exacto, -3) < 0) return "< 0,001"
  return conCeroFinal(exacto, 3, false)
}

/** Un corte del config escrito **exacto**, con al menos `minimo` decimales: `0,125`. */
export function corte(x: number, minimo = 2): string {
  const exacto = exactoCorto(x)
  const signo = exacto.neg && exacto.coef !== 0n ? "-" : ""
  let entero: string
  let fraccion: string
  if (exacto.exp >= 0) {
    entero = (exacto.coef * pot10(exacto.exp)).toString()
    fraccion = ""
  } else {
    const texto = exacto.coef.toString().padStart(-exacto.exp + 1, "0")
    entero = texto.slice(0, exacto.exp)
    fraccion = texto.slice(exacto.exp)
  }
  fraccion = fraccion.replace(/0+$/, "").padEnd(minimo, "0")
  return fraccion ? `${signo}${entero},${fraccion}` : `${signo}${entero}`
}

/**
 * `texto` —la cifra de `valor`— con los decimales que la dejan del lado correcto de `umbral`: el
 * espejo de `cifras.frente_al_corte`. Junto a su corte, una observación redondeada puede escribirse
 * igual a él o cruzarlo (`0.249962` frente a `0,24996` se leía «0,24996»); se extiende hasta que el
 * texto conserve el orden —en la igualdad, hasta decir el corte—, como máximo hasta el exacto.
 */
export function frenteAlCorte(texto: string, valor: number, umbral: number): string {
  if (!Number.isFinite(valor) || !Number.isFinite(umbral)) return texto
  const exacto = exactoCorto(valor)
  const frontera = exactoCorto(umbral)
  const lado = comparar(exacto, frontera)
  // «< 0,001» ya dice su lado cuando la cota no pasa del corte.
  if (texto.startsWith("< ")) {
    const cota = leer(texto.slice(2))
    if (lado < 0 && cota !== null && comparar(cota, frontera) <= 0) return texto
  }
  const leido = leer(texto)
  if (leido !== null && comparar(leido, frontera) === lado) return texto
  const miles = compararPot10(exacto, 3) >= 0
  const fraccion = texto.includes(",") ? texto.slice(texto.indexOf(",") + 1) : ""
  let decimales = /^\d+$/.test(fraccion) ? fraccion.length : 0
  const limite = decimalesDelExacto(exacto)
  while (decimales < limite) {
    decimales += 1
    const r = redondeado(exacto, decimales)
    if (comparar(r, frontera) === lado) return posicional(r, decimales, miles)
  }
  return posicional(redondeado(exacto, limite), limite, miles)
}

/**
 * Un conteo con punto de miles: `30.316`. Su dominio son los enteros seguros de JavaScript: fuera
 * de él (una cartera no cuenta 9 · 10^15 operaciones) se devuelve el entero sin agrupar.
 */
export function conteo(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return VACIO
  if (!Number.isSafeInteger(n)) return String(n)
  const signo = n < 0 ? "-" : ""
  return `${signo}${agrupar(String(Math.abs(n)))}`
}

/** Una proporción como porcentaje, con coma y espacio: `0.238` → `23,80 %`. Decimales fijos. */
export function porcentaje(x: number | null | undefined, decimales = 2): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return VACIO
  const producto = x * 100
  // Python escribe `inf %` cuando el producto desborda: el espejo también.
  if (!Number.isFinite(producto)) return `${noFinito(producto)} %`
  const r = redondeado(exactoBinario(producto), decimales)
  return `${posicional(r, decimales, false)} %`
}

/**
 * Un número que YA está en puntos porcentuales (0–100) como `8,63 %`: decimales fijos, redondeo al
 * par sobre el binario exacto, como `porcentaje` sin multiplicar por 100.
 */
export function puntosPorcentuales(x: number | null | undefined, decimales = 2): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return VACIO
  return `${posicional(redondeado(exactoBinario(x), decimales), decimales, false)} %`
}

/** Un monto redondeado a la unidad, con punto de miles y su símbolo: `$697.376.974`, `-$1.200`. */
export function monto(x: number | null | undefined, simbolo: string): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return VACIO
  const r = redondeado(exactoBinario(x), 0)
  const signo = r.neg && r.coef !== 0n ? "-" : ""
  return `${signo}${simbolo}${agrupar(r.coef.toString())}`
}

/**
 * Un rótulo redondeado a la unidad, con punto de miles (`523`, `1.200`): un puntaje o una
 * cantidad en millones en un eje. Redondeo fijo al par: es un rótulo, no una cifra que se compare
 * con un corte.
 */
export function entero(x: number | null | undefined): string {
  return monto(x, "")
}

/**
 * La marca de un eje numérico: el valor **exacto** del tick —los de Recharts son decimales
 * redondos, y un tick redondeado describiría otro punto—, con punto de miles desde 1.000 y en
 * notación científica bajo una millonésima. Un cero no lleva signo.
 */
export function marca(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return VACIO
  const exacto = exactoCorto(x)
  if (exacto.coef === 0n) return "0"
  if (compararPot10(exacto, -6) < 0) return cientifica(exacto)
  const texto = corte(x, 0)
  const [entero, fraccion] = texto.split(",")
  const signo = entero.startsWith("-") ? "-" : ""
  const conMiles = agrupar(entero.replace("-", ""))
  return fraccion === undefined ? `${signo}${conMiles}` : `${signo}${conMiles},${fraccion}`
}

/**
 * Un monto compacto para etiquetas y ejes: millones (`$114 M`, `$2,3 M`, un decimal bajo 10 M),
 * miles (`$80 k`) o la unidad. Redondeo fijo al par: es una etiqueta; la cifra exacta va en el
 * tooltip con `monto`.
 */
export function montoCompacto(x: number | null | undefined, simbolo: string): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return VACIO
  const abs = Math.abs(x)
  const signo = x < 0 ? "-" : ""
  const fijo = (valor: number, decimales: number): string =>
    posicional(redondeado(exactoCorto(valor), decimales), decimales, true)
  if (abs >= 1e6) {
    const millones = abs / 1e6
    return `${signo}${simbolo}${fijo(millones, millones < 10 ? 1 : 0)} M`
  }
  if (abs >= 1e3) return `${signo}${simbolo}${fijo(abs / 1e3, 0)} k`
  return `${signo}${simbolo}${fijo(abs, 0)}`
}
