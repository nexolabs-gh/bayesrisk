import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react"
import { CircleAlert, CircleCheck, FileUp, Loader2, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError, listCards, uploadCard, type MonitorableCard } from "@/lib/api"
import { subirYElegir } from "@/lib/monitoring-card"
import { describeApiError } from "@/lib/validation"

interface MonitoringCardPickerProps {
  /** La ruta que dice hoy `monitoring.bundle` (null si no hay tarjeta elegida). */
  bundlePath: string | null
  /** Escribe la ruta de la tarjeta elegida en `monitoring.bundle`. */
  onElegir: (ruta: string) => void
  /** El `monitoring.bundle` vigente del store: una subida sólo escribe si no cambió entre tanto. */
  getBundle: () => string | null
}

/**
 * La tarjeta que se monitorea (SDD-33 §4.3, capa B).
 *
 * Llega por dos caminos y los dos terminan en una ruta que se escribe en `monitoring.bundle`: la
 * tarjeta de una corrida del scorecard hecha en esta pantalla (la guarda el servidor con cada
 * corrida que se puede monitorear) o una tarjeta guardada que se sube como `.zip`. El servidor la
 * valida con la misma lectura que `bayesrisk.Monitor`: una tarjeta que la puerta guiada rechaza, la
 * pantalla también, con el mismo motivo. Aquí no se interpreta nada (SDD-23 §11).
 *
 * Un gesto vigente por vez: una respuesta que llega después de otro gesto (otra elección, otra
 * subida), de desmontar la sección o de un cambio de `monitoring.bundle` por otra vía no escribe
 * nada, para que una subida lenta no pise la tarjeta que la persona ya eligió (`subirYElegir`;
 * pasada 1 de Codex sobre la capa B).
 */
export function MonitoringCardPicker({
  bundlePath,
  onElegir,
  getBundle,
}: MonitoringCardPickerProps) {
  const [tarjetas, setTarjetas] = useState<MonitorableCard[] | null>(null)
  const [cargando, setCargando] = useState(false)
  const [subiendo, setSubiendo] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  // Dos turnos distintos: actualizar la lista no anula una subida en vuelo, y elegir o subir otra
  // tarjeta sí anula la respuesta de la anterior.
  const gesto = useRef(0)
  const lectura = useRef(0)
  const archivo = useRef<HTMLInputElement | null>(null)

  const actualizar = useCallback(async () => {
    const mio = ++lectura.current
    setCargando(true)
    try {
      const { cards } = await listCards()
      if (mio === lectura.current) setTarjetas(cards)
    } catch (error) {
      if (mio === lectura.current) {
        setAviso(
          error instanceof ApiError
            ? describeApiError(error.body, "No se pudo leer la lista de tarjetas.")
            : "No se pudo leer la lista de tarjetas.",
        )
      }
    } finally {
      if (mio === lectura.current) setCargando(false)
    }
  }, [])

  // La lista se lee al mostrar la sección: es lo único que este componente trae por su cuenta. Al
  // desmontarse, todo gesto en vuelo queda anulado: su respuesta ya no escribe en el config.
  useEffect(() => {
    void actualizar()
    const turnos = { gesto, lectura }
    return () => {
      turnos.gesto.current += 1
      turnos.lectura.current += 1
    }
  }, [actualizar])

  const elegir = (ruta: string) => {
    gesto.current += 1 // una subida o una lista en vuelo ya no escriben
    setAviso(null)
    onElegir(ruta)
  }

  const subir = async (evento: ChangeEvent<HTMLInputElement>) => {
    const elegido = evento.target.files?.[0]
    evento.target.value = ""
    if (!elegido) return
    const mio = ++gesto.current
    setSubiendo(true)
    setAviso(null)
    try {
      const tarjeta = await subirYElegir(
        { getBundle, setBundle: onElegir, subir: uploadCard },
        elegido,
        () => mio === gesto.current,
      )
      if (tarjeta === null) return
      setTarjetas((actual) => [
        ...(actual ?? []).filter((t) => t.path !== tarjeta.path),
        tarjeta,
      ])
    } catch (error) {
      if (mio === gesto.current) {
        setAviso(
          error instanceof ApiError
            ? describeApiError(error.body, error.message)
            : "No se pudo subir la tarjeta.",
        )
      }
    } finally {
      if (mio === gesto.current) setSubiendo(false)
    }
  }

  const lista = tarjetas ?? []
  return (
    <Card className="shadow-card">
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">La tarjeta que se monitorea</p>
          <p className="text-xs text-muted-foreground">
            Elige la tarjeta de una corrida del scorecard hecha en esta pantalla, o sube una
            tarjeta guardada como .zip (la carpeta de la tarjeta, comprimida). Sólo se monitorean
            tarjetas guardadas desde la 2.13.0, con su escala maestra.
          </p>
        </div>
        {lista.length > 0 ? (
          <ul className="space-y-1.5" aria-label="Tarjetas disponibles">
            {lista.map((tarjeta) => {
              const elegida = tarjeta.path === bundlePath
              return (
                <li
                  key={tarjeta.path}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/70 bg-background/30 px-3 py-2"
                >
                  <div className="text-sm text-foreground/90">
                    <span className="font-medium">
                      {tarjeta.origin === "run" ? tarjeta.name : "Tarjeta subida"}
                    </span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {tarjeta.n_grades} tramos · huella {tarjeta.bundle_hash.slice(0, 12)}
                      {tarjeta.created_at ? ` · ${tarjeta.created_at.slice(0, 16).replace("T", " ")}` : ""}
                    </span>
                  </div>
                  {elegida ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-300/90">
                      <CircleCheck className="size-4" aria-hidden="true" />
                      En uso
                    </span>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => elegir(tarjeta.path)}>
                      Usar esta tarjeta
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        ) : tarjetas !== null ? (
          <p className="text-xs text-muted-foreground">
            Aún no hay tarjetas: corre un scorecard en esta pantalla (con su escala maestra, que
            corre por defecto) o sube una tarjeta guardada.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={archivo}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(evento) => void subir(evento)}
            aria-label="Subir una tarjeta (.zip)"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={subiendo}
            onClick={() => archivo.current?.click()}
          >
            {subiendo ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileUp className="size-4" aria-hidden="true" />
            )}
            Subir una tarjeta (.zip)
          </Button>
          <Button size="sm" variant="ghost" disabled={cargando} onClick={() => void actualizar()}>
            <RefreshCw className={cargando ? "size-4 animate-spin" : "size-4"} aria-hidden="true" />
            Actualizar la lista
          </Button>
        </div>
        {aviso ? (
          <p role="alert" className="inline-flex items-start gap-1.5 text-xs text-amber-200/90">
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            {aviso}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
