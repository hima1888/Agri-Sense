export function timeFormatter(tz: string, withDay = false) {
  const fmt = new Intl.DateTimeFormat(undefined, {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    ...(withDay ? { weekday: 'short' } : {}),
  })
  return (t: number) => fmt.format(new Date(t))
}
