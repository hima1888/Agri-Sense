import { describe, expect, it } from 'vitest'
import { SseParser, type SseMessage } from './sse'

function collect() {
  const messages: SseMessage[] = []
  const comments: string[] = []
  const parser = new SseParser((m) => messages.push(m), (c) => comments.push(c))
  return { parser, messages, comments }
}

describe('SseParser', () => {
  it('parses events split across arbitrary chunk boundaries', () => {
    const { parser, messages } = collect()
    const raw = 'retry: 5000\n\nevent: snapshot\ndata: {"a":1}\n\nid: 7\nevent: readings\ndata: {"b":2}\n\n'
    for (const ch of raw) parser.push(ch) // worst case: one character at a time
    expect(messages).toEqual([
      { event: 'snapshot', data: '{"a":1}', id: null },
      { event: 'readings', data: '{"b":2}', id: '7' },
    ])
    expect(parser.retryMs).toBe(5000)
  })

  it('handles CRLF, multi-line data, default event name and comments', () => {
    const { parser, messages, comments } = collect()
    parser.push(': ping\r\n\r\ndata: line1\r\ndata: line2\r\n\r\ndata:no-space\n\n')
    expect(comments).toEqual(['ping'])
    expect(messages).toEqual([
      { event: 'message', data: 'line1\nline2', id: null },
      { event: 'message', data: 'no-space', id: null },
    ])
  })

  it('does not dispatch an event until its blank line arrives', () => {
    const { parser, messages } = collect()
    parser.push('event: readings\ndata: {}\n')
    expect(messages).toHaveLength(0)
    parser.push('\n')
    expect(messages).toHaveLength(1)
  })
})
