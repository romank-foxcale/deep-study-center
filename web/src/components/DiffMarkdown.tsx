// A prose diff rendered like the lesson (Markdown + KaTeX), in the style of suggestions in a word processor:
// deleted text red with a line through it, inserted text green, both in one block.
// Changed runs are wrapped in private-use marker characters before rendering; a small rehype plugin then turns the
// marked text into <span class="pd-del|pd-ins">. The diff keeps a formula as one token, so a changed formula is the old
// one deleted and the new one inserted; Markdown syntax at the start of a line (list, heading, quote) stays outside
// the markers.

import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

const ch = (n: number) => String.fromCharCode(n)
const MARK = { del: [ch(0xe000), ch(0xe001)], ins: [ch(0xe002), ch(0xe003)] } as const
const ALL_MARKS = new RegExp(`[${ch(0xe000)}-${ch(0xe003)}]`, 'g')
const HAS_MARK = new RegExp(`[${ch(0xe000)}-${ch(0xe003)}]`)
const LINE_SYNTAX = /^(\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)?)/
const MATH_SPLIT = /(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)/
const MATH = /\$\$[\s\S]*?\$\$|\$[^$\n]+?\$/g

type Token = [string, string]

function mark(text: string, [open, close]: readonly [string, string]): string {
  return text.split(MATH_SPLIT).map((part, i) => {
    // a whole formula; a display formula gets its own line, so a deleted and an inserted one are not on one line
    if (i % 2 === 1) return part.startsWith('$$') ? `\n${open}${part}${close}\n` : `${open}${part}${close}`
    return part.split('\n').map(line => {
      const lead = line.match(LINE_SYNTAX)?.[1] ?? ''
      const body = line.slice(lead.length)
      return body.trim() ? `${lead}${open}${body}${close}` : line
    }).join('\n')
  }).join('')
}

// A line that is only $$...$$ (maybe inside change markers) is a display formula. remark-math reads a one-line $$...$$
// as inline math, so rewrite it as a centered block; the markers go on their own lines around it (they render as
// empty paragraphs, which are hidden) and still mark the whole formula as deleted or inserted.
const ONE_LINE_DISPLAY = new RegExp(`^([ \\t]*)([${ch(0xe000)}-${ch(0xe003)}]?)\\$\\$([^\\n]+?)\\$\\$([${ch(0xe000)}-${ch(0xe003)}]?)[ \\t]*$`, 'gm')

function source(tokens: Token[]): string {
  const src = tokens.map(([op, t]) => (op === 'del' ? mark(t, MARK.del) : op === 'ins' ? mark(t, MARK.ins) : t)).join('')
  // safety net: a marker that still ended up inside a formula would break it; drop such markers
  return src.replace(MATH, m => (HAS_MARK.test(m.slice(1, -1)) ? m[0] + m.slice(1, -1).replace(ALL_MARKS, '') + m.slice(-1) : m))
    .replace(ONE_LINE_DISPLAY, (_m, indent: string, open: string, tex: string, close: string) =>
      `${open ? `${indent}${open}\n\n` : ''}${indent}$$\n${indent}${tex.trim()}\n${indent}$$${close ? `\n\n${indent}${close}` : ''}`)
}

interface HastNode { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: HastNode[] }

const wrap = (cls: string, children: HastNode[]): HastNode => ({ type: 'element', tagName: 'span', properties: { className: [cls] }, children })

function rehypeMarks() {
  const cls: Record<string, string | null> = {
    [MARK.del[0]]: 'pd-del', [MARK.del[1]]: null, [MARK.ins[0]]: 'pd-ins', [MARK.ins[1]]: null,
  }
  return (tree: HastNode) => {
    let on: string | null = null
    const walk = (node: HastNode) => {
      if (!node.children) return
      const out: HastNode[] = []
      for (const child of node.children) {
        if (child.type === 'text' && child.value !== undefined) {
          let buf = ''
          const flush = () => {
            if (!buf) return
            const text = { type: 'text', value: buf }
            out.push(on ? wrap(on, [text]) : text)
            buf = ''
          }
          for (const c of child.value) {
            if (c in cls) { flush(); on = cls[c] } else buf += c
          }
          flush()
        } else {
          const katex = Array.isArray(child.properties?.className) && (child.properties!.className as string[]).some(c => c.startsWith('katex'))
          if (katex && on) out.push(wrap(on, [child]))  // a whole changed formula
          else { walk(child); out.push(child) }
        }
      }
      node.children = out
    }
    walk(tree)
  }
}

export default function DiffMarkdown({ tokens }: { tokens: Token[] }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex, rehypeMarks]}>{source(tokens)}</ReactMarkdown>
    </div>
  )
}
