/**
 * Minimal Server-Sent Events client over fetch().
 *
 * The browser's EventSource cannot send an Authorization header, and putting the
 * access token in the URL would leak it into proxy and server logs. This reads the
 * text/event-stream body manually, following the WHATWG parsing rules.
 */

export interface SseMessage {
  event: string
  data: string
  id: string | null
}

export class SseParser {
  private buffer = ''
  private data: string[] = []
  private event = ''
  private id: string | null = null
  retryMs: number | null = null

  constructor(
    private readonly onMessage: (m: SseMessage) => void,
    private readonly onComment: (text: string) => void = () => {},
  ) {}

  push(chunk: string): void {
    this.buffer += chunk
    const lines = this.buffer.split(/\r\n|\r|\n/)
    this.buffer = lines.pop() ?? '' // keep an incomplete trailing line for the next chunk
    for (const line of lines) this.line(line)
  }

  private line(line: string): void {
    if (line === '') return this.dispatch()
    if (line.startsWith(':')) return this.onComment(line.slice(1).trim())
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') this.data.push(value)
    else if (field === 'event') this.event = value
    else if (field === 'id') this.id = value
    else if (field === 'retry' && /^\d+$/.test(value)) this.retryMs = Number(value)
  }

  private dispatch(): void {
    if (this.data.length) {
      this.onMessage({ event: this.event || 'message', data: this.data.join('\n'), id: this.id })
    }
    this.data = []
    this.event = ''
  }
}

export class SseHttpError extends Error {
  constructor(readonly status: number) {
    super(`Stream request failed with HTTP ${status}`)
  }
}

/** Open one stream and pump it until it ends or `signal` aborts. Resolves when the server closes it. */
export async function readSse(
  url: string,
  init: { headers: Record<string, string>; signal: AbortSignal },
  parser: SseParser,
): Promise<void> {
  const res = await fetch(url, {
    headers: { Accept: 'text/event-stream', ...init.headers },
    signal: init.signal,
    cache: 'no-store',
  })
  if (!res.ok || !res.body) throw new SseHttpError(res.status)
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  // Cancelling the reader ends a pending read() even where the body ignores the abort signal.
  const cancel = () => void reader.cancel().catch(() => {})
  init.signal.addEventListener('abort', cancel)
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done || init.signal.aborted) return
      parser.push(value)
    }
  } finally {
    init.signal.removeEventListener('abort', cancel)
  }
}
