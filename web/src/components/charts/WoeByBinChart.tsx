import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts"
import { formatCount, formatMetric, formatPercent } from "@/lib/results-format"
import type { BinDetailRow } from "@/lib/results-format"
import { marca, porcentaje } from "@/lib/cifras"
import { AXIS_LINE, AXIS_TICK, BRAND, CURSOR_FILL, GRID_STROKE, niceBound } from "./chart-theme"

type ChartRow = Omit<BinDetailRow, "eventRate"> & { tramo: string; eventRate: number | null }

function BinTooltip({ active, payload }: {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: ChartRow }>
}) {
  const row = active ? payload?.[0]?.payload : null
  if (!row) return null
  return (
    <div className="max-w-72 rounded-lg bg-secondary px-3 py-2 text-xs shadow-card ring-1 ring-foreground/10">
      <p className="break-words font-mono">{row.tramo} · {row.binLabel}</p>
      <p>Tasa de malos: {formatPercent(row.eventRate)}</p>
      <p>WoE: {formatMetric(row.woe)}</p>
      <p>Casos: {formatCount(row.count)}</p>
    </div>
  )
}

/** D-DOC-SC: magnitudes separadas; T1…Tn remiten a la tabla contigua con los cortes exactos. */
export function WoeByBinChart({ rows }: { rows: BinDetailRow[] }) {
  if (rows.length === 0) return null
  const data = rows.map((row, index) => ({ ...row, tramo: `T${index + 1}`,
    eventRate: row.count === 0 ? null : row.eventRate,
    woe: row.count === 0 ? null : row.woe,
  }))
  const bound = niceBound(Math.max(0, ...rows.map((row) => Math.abs(row.woe ?? 0))))
  return (
    <div className="space-y-4">
      <BinPanel rows={data} measure="eventRate" label="Tasa de malos por tramo · Desarrollo" bound={bound} />
      <BinPanel rows={data} measure="woe" label="WoE por tramo · Desarrollo" bound={bound} />
      <p className="text-xs text-muted-foreground">Los tramos T1…Tn se definen en la tabla siguiente. Cada panel tiene su propia escala.</p>
    </div>
  )
}

function BinPanel({ rows, measure, label, bound }: {
  rows: ChartRow[]
  measure: "eventRate" | "woe"
  label: string
  bound: number
}) {
  return (
    <figure aria-label={label} className="min-w-0">
      <figcaption className="mb-2 text-sm font-medium">{label}</figcaption>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID_STROKE} />
            <XAxis dataKey="tramo" interval={0} tickLine={false} axisLine={AXIS_LINE} tick={AXIS_TICK} />
            <YAxis domain={measure === "woe" ? [-bound, bound] : [0, "auto"]}
              width={56} tickLine={false} axisLine={false} tick={AXIS_TICK}
              tickFormatter={measure === "woe" ? marca : (v: number) => porcentaje(v, 0)} />
            {measure === "woe" ? <ReferenceLine y={0} stroke="var(--border)" /> : null}
            <Tooltip cursor={CURSOR_FILL} content={<BinTooltip />} />
            <Line type="linear" dataKey={measure} name={label} stroke={BRAND.cyan}
              strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
