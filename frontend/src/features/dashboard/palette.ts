/**
 * Chart colours.
 *
 * ZONE_COLORS is a categorical palette assigned to zones in fixed order (by zone id, so a
 * zone keeps its colour when filters change). Validated with the dataviz skill's
 * validate_palette.js against our dark chart surfaces (#14221a and #0d1712):
 * lightness band, chroma floor, adjacent CVD separation (worst ΔE 8.4), normal-vision
 * floor (worst ΔE 19.3) and >= 3:1 contrast all PASS. A 7th+ zone folds into "Other".
 */
export const ZONE_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9'] as const
export const OTHER_COLOR = '#8e9e86' // sage-400, neutral

/** Single-series charts: temperature (warm ochre) and precipitation (water blue). */
export const TEMP_COLOR = '#c98500'
export const RAIN_COLOR = '#3987e5'

export const CHART = {
  grid: 'rgb(255 255 255 / 0.06)',
  axis: '#8e9e86',
  tooltipBg: '#14221a',
  tooltipBorder: 'rgb(255 255 255 / 0.1)',
} as const

export function zoneColor(index: number): string {
  return ZONE_COLORS[index] ?? OTHER_COLOR
}
