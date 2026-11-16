/**
 * Time zone choices. Browsers' ICU data returns some legacy canonical names (Chrome lists
 * "Asia/Calcutta", not "Asia/Kolkata"). We show modern IANA names and always include the
 * farm's current zone, so a <select> can never silently fall back to another zone.
 */
const LEGACY_TO_MODERN: Record<string, string> = {
  'Asia/Calcutta': 'Asia/Kolkata',
  'Asia/Katmandu': 'Asia/Kathmandu',
  'Asia/Saigon': 'Asia/Ho_Chi_Minh',
  'Asia/Rangoon': 'Asia/Yangon',
  'Asia/Dacca': 'Asia/Dhaka',
  'Asia/Thimbu': 'Asia/Thimphu',
  'Asia/Ulan_Bator': 'Asia/Ulaanbaatar',
  'Europe/Kiev': 'Europe/Kyiv',
  'Africa/Asmera': 'Africa/Asmara',
  'America/Godthab': 'America/Nuuk',
  'Atlantic/Faeroe': 'Atlantic/Faroe',
  'Pacific/Truk': 'Pacific/Chuuk',
  'Pacific/Ponape': 'Pacific/Pohnpei',
}

export function modernZone(tz: string): string {
  return LEGACY_TO_MODERN[tz] ?? tz
}

export function timezoneOptions(current?: string): string[] {
  let zones: string[]
  try {
    zones = Intl.supportedValuesOf('timeZone')
  } catch {
    zones = []
  }
  const set = new Set(zones.map(modernZone))
  set.add('UTC')
  if (current) set.add(current)
  return [...set].sort((a, b) => a.localeCompare(b))
}

export const LOCAL_TZ = modernZone(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
