/**
 * Pure geometry helpers for the digital twin (no three.js imports, unit-testable).
 * World units are metres: x = east, z = south, y = up (the API's coordinate system).
 */
import type { TwinZone } from './schemas'

export type XZ = readonly [number, number]

/** Ray-casting point-in-polygon test in the x/z plane. */
export function pointInPolygon([x, z]: XZ, polygon: readonly XZ[]): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, zi] = polygon[i]!
    const [xj, zj] = polygon[j]!
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside
  }
  return inside
}

export function bbox(polygon: readonly XZ[]) {
  const xs = polygon.map((p) => p[0])
  const zs = polygon.map((p) => p[1])
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minZ: Math.min(...zs), maxZ: Math.max(...zs) }
}

/** Deterministic pseudo-random in [0, 1) so the scene is identical on every render. */
export function hash01(a: number, b: number, seed = 0): number {
  const s = Math.sin(a * 127.1 + b * 311.7 + seed * 74.7) * 43758.5453
  return s - Math.floor(s)
}

export interface PlantInstance {
  x: number
  z: number
  scale: number
  rotation: number
}

/**
 * Plants in rows along the zone's long axis, inside its polygon. Real row spacing is
 * honoured until the instance budget is reached; beyond that spacing widens uniformly
 * (each mark then represents several plants) to keep the scene fast.
 */
export function cropInstances(zone: TwinZone, maxInstances = 1800): PlantInstance[] {
  if (!zone.crop) return []
  const poly = zone.polygon as XZ[]
  const { minX, maxX, minZ, maxZ } = bbox(poly)
  const w = maxX - minX
  const d = maxZ - minZ
  const along = w >= d ? 'x' : 'z'
  const inRow = zone.crop.form === 'tree' ? zone.crop.row_spacing_m : Math.max(zone.crop.row_spacing_m * 0.6, 0.3)
  const between = zone.crop.row_spacing_m
  const estimate = (w * d) / (inRow * between)
  const k = estimate > maxInstances ? Math.sqrt(estimate / maxInstances) : 1
  const stepA = inRow * k
  const stepB = between * k
  const margin = Math.min(2, Math.min(w, d) * 0.05)
  const growth = zone.crop.growth_fraction ?? (zone.crop.status === 'planned' ? 0 : 0.6)
  const baseScale = zone.crop.status === 'planned' ? 0.12 : 0.25 + 0.75 * growth
  const out: PlantInstance[] = []
  const [a0, a1, b0, b1] = along === 'x' ? [minX, maxX, minZ, maxZ] : [minZ, maxZ, minX, maxX]
  for (let b = b0 + margin; b <= b1 - margin && out.length < maxInstances; b += stepB) {
    for (let a = a0 + margin; a <= a1 - margin && out.length < maxInstances; a += stepA) {
      const x = along === 'x' ? a : b
      const z = along === 'x' ? b : a
      if (!pointInPolygon([x, z], poly)) continue
      const r = hash01(x, z, zone.id)
      out.push({ x, z, scale: baseScale * (0.85 + 0.3 * r), rotation: r * Math.PI * 2 })
    }
  }
  return out
}

export interface RowSegment {
  x: number
  z: number
  length: number
  alongX: boolean
}

/** Growth-dependent canopy size (m) for row crops: width across the row and height. */
export function canopySize(zone: TwinZone): { width: number; height: number; cover: number } {
  const crop = zone.crop
  if (!crop) return { width: 0, height: 0, cover: 0 }
  const g = crop.status === 'planned' ? 0.03 : (crop.growth_fraction ?? 0.6)
  if (crop.form === 'grass') return { width: Math.min(crop.row_spacing_m, 0.08 + 0.35 * g), height: 0.1 + 2.0 * g, cover: Math.min(0.95, 0.15 + 0.9 * g) }
  if (crop.form === 'bush') return { width: Math.min(crop.row_spacing_m * 0.95, 0.12 + 0.7 * g), height: 0.08 + 0.9 * g, cover: Math.min(0.9, 0.1 + 0.9 * g) }
  return { width: 0, height: 0, cover: Math.min(0.6, 0.1 + 0.5 * g) } // trees: individual canopies
}

/**
 * Crop rows as stripes (how row crops actually look from a distance), along the zone's
 * long axis at the real row spacing, clipped to the zone polygon in short segments.
 * Above `maxRows`, rows are thinned uniformly and each stripe stands for several rows.
 */
export function cropRows(zone: TwinZone, maxRows = 160, segment = 12): RowSegment[] {
  if (!zone.crop || zone.crop.form === 'tree') return []
  const poly = zone.polygon as XZ[]
  const { minX, maxX, minZ, maxZ } = bbox(poly)
  const alongX = maxX - minX >= maxZ - minZ
  const [a0, a1, b0, b1] = alongX ? [minX, maxX, minZ, maxZ] : [minZ, maxZ, minX, maxX]
  const margin = Math.min(1.5, (b1 - b0) * 0.03)
  const rows = Math.floor((b1 - b0 - 2 * margin) / zone.crop.row_spacing_m) + 1
  const step = rows > maxRows ? (b1 - b0 - 2 * margin) / (maxRows - 1) : zone.crop.row_spacing_m
  const out: RowSegment[] = []
  for (let b = b0 + margin; b <= b1 - margin + 1e-6; b += step) {
    for (let a = a0 + margin; a < a1 - margin; a += segment) {
      const len = Math.min(segment, a1 - margin - a)
      const mid = a + len / 2
      const pt: XZ = alongX ? [mid, b] : [b, mid]
      if (len > 0.5 && pointInPolygon(pt, poly)) out.push({ x: pt[0], z: pt[1], length: len, alongX })
    }
  }
  return out
}

/** Zone surface colour: bare soil blended toward crop green by canopy cover. */
export function canopyTint(soilHex: string, cover: number, greenHex = '#4f7f3a'): string {
  const a = hexToRgb(soilHex)
  const b = hexToRgb(greenHex)
  const c = a.map((v, k) => Math.round(v + (b[k]! - v) * Math.max(0, Math.min(1, cover))))
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`
}

/**
 * Sequential single-hue (blue) scale for volumetric soil moisture, light = dry, dark = wet.
 * Domain 10–40 % covers wilting point to saturation for most mineral soils.
 */
export const MOISTURE_DOMAIN = [10, 40] as const
const MOISTURE_STOPS = ['#cfe1f2', '#93bde6', '#4f8fd6', '#2a66b3', '#184f95'] as const

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export function moistureColor(value: number | null): string {
  if (value == null) return '#4a4a42' // no data: neutral, never a guessed colour
  const [lo, hi] = MOISTURE_DOMAIN
  const t = Math.min(1, Math.max(0, (value - lo) / (hi - lo))) * (MOISTURE_STOPS.length - 1)
  const i = Math.min(MOISTURE_STOPS.length - 2, Math.floor(t))
  const f = t - i
  const a = hexToRgb(MOISTURE_STOPS[i]!)
  const b = hexToRgb(MOISTURE_STOPS[i + 1]!)
  const c = a.map((v, k) => Math.round(v + (b[k]! - v) * f))
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`
}

export const MOISTURE_LEGEND_STOPS = MOISTURE_STOPS

/** Sensor status colour: reading quality first, then freshness. Text labels accompany it in the UI. */
export function sensorStatus(
  latest: { quality: string; recorded_at: string } | null,
  now: number,
  staleAfterMs = 10 * 60_000,
): { key: 'good' | 'suspect' | 'stale' | 'none'; color: string; label: string } {
  if (!latest) return { key: 'none', color: '#6f7a6a', label: 'No readings' }
  if (latest.quality !== 'good') return { key: 'suspect', color: '#e2b35c', label: 'Suspect reading' }
  if (now - Date.parse(latest.recorded_at) > staleAfterMs) return { key: 'stale', color: '#8e9e86', label: 'Stale' }
  return { key: 'good', color: '#8fbf7a', label: 'Reporting' }
}

/** Unit vector toward the sun in world space (x east, y up, z south) from elevation/azimuth (° from north). */
export function sunDirection(elevationDeg: number, azimuthDeg: number): [number, number, number] {
  const el = (elevationDeg * Math.PI) / 180
  const az = (azimuthDeg * Math.PI) / 180
  return [Math.cos(el) * Math.sin(az), Math.sin(el), -Math.cos(el) * Math.cos(az)]
}

/** Camera distance that frames the farm extent. */
export function frameDistance(extent: { min: XZ; max: XZ }): number {
  const w = extent.max[0] - extent.min[0]
  const d = extent.max[1] - extent.min[1]
  return Math.max(120, Math.hypot(w, d) * 0.95)
}


/** Crop colour and outline from the zone's latest saved disease check (API state, not decoration). */
export function healthStyle(zone: TwinZone): { leaf: string | null; outline: string | null; label: string } {
  const h = zone.health
  if (!h) return { leaf: null, outline: null, label: '' }
  if (h.state === 'disease') return { leaf: '#a8862f', outline: '#e0663f', label: ' · possible disease' }
  if (h.state === 'uncertain') return { leaf: null, outline: '#d9b45a', label: ' · check uncertain' }
  return { leaf: null, outline: null, label: '' }
}
