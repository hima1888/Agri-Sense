/** Local calendar date as YYYY-MM-DD. (Date.toISOString() gives the UTC date, which in India is the
 * previous day until 05:30.) */
export function localDate(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function localDateDaysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return localDate(d)
}
