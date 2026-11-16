/** Probability as a percentage, floored (never rounded up): 0.9987 shows as 99.8 %, not 100 %. */
export const pct = (v: number) => (v > 0 && v < 0.001 ? '<0.1 %' : `${(Math.floor(v * 1000) / 10).toFixed(1)} %`)
