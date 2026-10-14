/**
 * La secuencia «subir una tarjeta y elegirla» del monitoreo (SDD-33 §4.3, capa B), sin React.
 *
 * Vive aquí, y no en `MonitoringCardPicker`, para poder probarla con promesas diferidas: una
 * subida tarda, y mientras tanto la persona puede elegir otra tarjeta, escribir la ruta a mano o
 * salir de la sección y volver. La respuesta de una subida vieja **no** puede pisar lo que la
 * persona eligió después (pasada 1 de Codex sobre la capa B: subir A, salir, volver y elegir B, y
 * al terminar A la elección volvía a A).
 */

import type { MonitorableCard } from "@/lib/api"

/** Lo que la secuencia necesita del store y de la API. */
export interface PuertoDeLaTarjeta {
  /** El `monitoring.bundle` vigente del config (del store, no de un render viejo). */
  getBundle: () => string | null
  /** Escribe la ruta elegida en `monitoring.bundle`. */
  setBundle: (ruta: string) => void
  /** Sube el `.zip` (`POST /api/cards/upload`). */
  subir: (archivo: File) => Promise<MonitorableCard>
}

/**
 * Sube la tarjeta y la elige **sólo si nada cambió entre tanto**: `vigente()` dice si este gesto
 * sigue siendo el último del componente que lo lanzó (otro gesto o el desmontaje lo anulan), y el
 * `monitoring.bundle` del store tiene que ser el mismo que había al empezar (una elección por otra
 * vía —la lista, el campo de texto, otro montaje— también lo anula). Devuelve la tarjeta subida, o
 * `null` si la respuesta llegó tarde y no se escribió nada. Los errores de la subida se propagan.
 */
export async function subirYElegir(
  puerto: PuertoDeLaTarjeta,
  archivo: File,
  vigente: () => boolean,
): Promise<MonitorableCard | null> {
  const inicial = puerto.getBundle()
  const tarjeta = await puerto.subir(archivo)
  if (!vigente() || puerto.getBundle() !== inicial) return null
  puerto.setBundle(tarjeta.path)
  return tarjeta
}
